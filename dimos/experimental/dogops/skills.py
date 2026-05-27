from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from dimos.experimental.dogops.config_loader import (
    DEFAULT_MANIFEST,
    DEFAULT_MISSION,
    DEFAULT_POLICY,
    DEFAULT_SITE,
    load_manifest as read_manifest,
    load_mission as read_mission,
    load_site_config as read_site_config,
)
from dimos.experimental.dogops.mission_engine import run_offline_simulation
from dimos.experimental.dogops.mapping import (
    add_point_of_interest,
    add_waypoint,
    build_simulated_site_map,
    map_summary,
    simulate_poi_captures,
)
from dimos.experimental.dogops.models import (
    Incident,
    IncidentState,
    IncidentType,
    MissionState,
    NavAction,
    NavEvent,
    RoutePlan,
    Severity,
    WorkOrder,
    WorkOrderState,
)
from dimos.experimental.dogops.nav_eval import summarize_nav_events
from dimos.experimental.dogops.report import build_report_data
from dimos.experimental.dogops.store import DogOpsStore

try:  # pragma: no cover - exercised only inside a full DimOS checkout.
    from dimos.agents.annotation import skill
except ModuleNotFoundError:  # pragma: no cover - fallback behavior is tested through methods.
    F = TypeVar("F", bound=Callable[..., Any])

    def skill(func: F | None = None, **metadata: object) -> F | Callable[[F], F]:
        def decorate(inner: F) -> F:
            setattr(inner, "__dogops_skill__", True)
            setattr(inner, "__dogops_skill_metadata__", metadata)
            return inner

        if func is None:
            return decorate
        return decorate(func)


try:  # pragma: no cover - exercised only inside a full DimOS checkout.
    from dimos.core.module import Module
except ModuleNotFoundError:

    class Module:
        @classmethod
        def blueprint(cls, **kwargs: object) -> dict[str, object]:
            return {"module": cls.__name__, "kwargs": kwargs}


class DogOpsSkillContainer(Module):
    """Deterministic SiteOps skills exposed through DimOS MCP or direct tests."""

    def __init__(
        self,
        *,
        site_path: str | Path = DEFAULT_SITE,
        manifest_path: str | Path = DEFAULT_MANIFEST,
        mission_path: str | Path = DEFAULT_MISSION,
        policy_path: str | Path = DEFAULT_POLICY,
        run_dir: str | Path = ".dogops/runs/latest",
        **_: object,
    ) -> None:
        self.site_path = Path(site_path)
        self.manifest_path = Path(manifest_path)
        self.mission_path = Path(mission_path)
        self.policy_path = Path(policy_path)
        self.run_dir = Path(run_dir)

    @skill
    def load_site_config(self, path: str = str(DEFAULT_SITE)) -> str:
        self.site_path = Path(path)
        site = read_site_config(self.site_path)
        return _json(
            ok=True,
            skill="load_site_config",
            site_id=site.site_id,
            zones=len(site.zones),
            assets=len(site.assets),
            packages=len(site.packages),
        )

    @skill
    def load_manifest(self, path: str = str(DEFAULT_MANIFEST)) -> str:
        self.manifest_path = Path(path)
        manifest = read_manifest(self.manifest_path)
        return _json(
            ok=True,
            skill="load_manifest",
            manifest_id=manifest.manifest_id,
            packages=len(manifest.items),
        )

    @skill
    def load_mission(self, path: str = str(DEFAULT_MISSION)) -> str:
        self.mission_path = Path(path)
        mission = read_mission(self.mission_path)
        return _json(
            ok=True,
            skill="load_mission",
            mission_id=mission.mission_id,
            steps=len(mission.steps),
        )

    @skill
    def run_mission(self, mission_id: str = "receiving_sre_demo") -> str:
        mission = read_mission(self.mission_path)
        if mission.mission_id != mission_id:
            return _json(
                ok=False,
                skill="run_mission",
                error="unknown_mission",
                mission_id=mission_id,
                configured_mission_id=mission.mission_id,
            )
        state = run_offline_simulation(
            site=self.site_path,
            manifest=self.manifest_path,
            mission=self.mission_path,
            policy=self.policy_path,
            out=self.run_dir,
        )
        return _json(
            ok=True,
            skill="run_mission",
            run_id=state.run.id,
            mission_id=state.run.mission_id,
            state=state.run.state,
            report=str(self.run_dir / "report.md"),
            summary=state.run.summary,
        )

    @skill
    def scan_zone(self, zone_id: str) -> str:
        mission = read_mission(self.mission_path)
        observations = [
            obs for obs in mission.simulation_observations.values() if obs.zone_id == zone_id
        ]
        if not observations:
            return _json(ok=False, skill="scan_zone", error="unknown_zone", zone_id=zone_id)
        visible_tag_ids = sorted({tag for obs in observations for tag in obs.visible_tag_ids})
        package_ids = sorted(
            key.removesuffix(".zone_id")
            for obs in observations
            for key in obs.facts
            if key.startswith("PKG-") and key.endswith(".zone_id")
        )
        return _json(
            ok=True,
            skill="scan_zone",
            zone_id=zone_id,
            visible_tag_ids=visible_tag_ids,
            package_ids=package_ids,
        )

    @skill
    def inspect_asset(self, asset_id: str) -> str:
        site = read_site_config(self.site_path)
        asset = site.asset_by_id().get(asset_id)
        if asset is None:
            return _json(ok=False, skill="inspect_asset", error="unknown_asset", asset_id=asset_id)
        incidents = []
        if self._state_file().exists():
            state = DogOpsStore.load_existing(self.run_dir).state
            assert state is not None
            incidents = [
                incident.model_dump(mode="json")
                for incident in state.incidents
                if incident.entity_id == asset_id
            ]
        return _json(
            ok=True,
            skill="inspect_asset",
            asset_id=asset.id,
            display_name=asset.display_name,
            expected_clear=asset.expected_clear,
            incidents=incidents,
        )

    @skill
    def reconcile_manifest(self) -> str:
        store = self._require_store("reconcile_manifest")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        report = build_report_data(state)
        return _json(
            ok=True,
            skill="reconcile_manifest",
            run_id=state.run.id,
            packages_expected=report["packages_expected"],
            packages_observed=report["packages_observed"],
            manifest_exceptions=report["manifest_exceptions"],
            open_issues=report["open_issues"],
        )

    @skill
    def open_work_order(self, entity_id: str, issue_type: str) -> str:
        store = self._require_store("open_work_order")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        for incident in state.incidents:
            if incident.entity_id == entity_id and incident.type == issue_type:
                work_order = _work_order_for_incident(state.work_orders, incident.id)
                return _json(
                    ok=True,
                    skill="open_work_order",
                    incident_id=incident.id,
                    work_order_id=work_order.id if work_order else None,
                    state=incident.state,
                    summary="Existing work order returned.",
                )

        incident_type = IncidentType(issue_type)
        rule = state.policy.rule_for_type(incident_type)
        incident = Incident(
            id=f"INC-{len(state.incidents) + 1:03d}",
            run_id=state.run.id,
            ts_open=time.time(),
            severity=Severity(rule.severity) if rule else Severity.P2,
            type=incident_type,
            entity_id=entity_id,
            related_package_id=entity_id if entity_id.startswith("PKG-") else None,
            state=IncidentState.open,
            title=f"{entity_id} {issue_type}",
            recommended_action=rule.recommended_action if rule else "Review and remediate.",
        )
        work_order = WorkOrder(
            id=f"WO-{len(state.work_orders) + 1:03d}",
            incident_id=incident.id,
            requested_action=incident.recommended_action,
            state=WorkOrderState.assigned,
        )
        store.append_incident(incident)
        store.append_work_order(work_order)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        return _json(
            ok=True,
            skill="open_work_order",
            incident_id=incident.id,
            work_order_id=work_order.id,
            state=incident.state,
        )

    @skill
    def mark_ready_to_verify(self, work_order_id: str) -> str:
        store = self._require_store("mark_ready_to_verify")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        work_order = _find_work_order(state.work_orders, work_order_id)
        if work_order is None:
            return _json(
                ok=False,
                skill="mark_ready_to_verify",
                error="unknown_work_order",
                work_order_id=work_order_id,
            )
        if work_order.state != WorkOrderState.verified_closed:
            work_order.state = WorkOrderState.ready_to_verify
            incident = _find_incident(state.incidents, work_order.incident_id)
            if incident is not None and incident.state != IncidentState.resolved:
                incident.state = IncidentState.ready_to_verify
                store.update_incident(incident)
            store.update_work_order(work_order)
            store.write_state(state.run.id)
            store.write_report(state.run.id)
        return _json(
            ok=True,
            skill="mark_ready_to_verify",
            work_order_id=work_order.id,
            state=work_order.state,
        )

    @skill
    def verify_work_order(self, work_order_id: str) -> str:
        store = self._require_store("verify_work_order")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        work_order = _find_work_order(state.work_orders, work_order_id)
        if work_order is None:
            return _json(
                ok=False,
                skill="verify_work_order",
                error="unknown_work_order",
                work_order_id=work_order_id,
            )
        incident = _find_incident(state.incidents, work_order.incident_id)
        if work_order.state != WorkOrderState.verified_closed:
            work_order.state = WorkOrderState.verified_closed
            if incident is not None:
                incident.state = IncidentState.resolved
                incident.ts_closed = time.time()
                store.update_incident(incident)
            store.update_work_order(work_order)
            store.write_state(state.run.id)
            store.write_report(state.run.id)
        return _json(
            ok=True,
            skill="verify_work_order",
            work_order_id=work_order.id,
            state=work_order.state,
            summary=f"{incident.entity_id if incident else work_order.id} verified closed.",
        )

    @skill
    def what_changed(self, since_run_id: str | None = None) -> str:
        store = self._require_store("what_changed")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        if since_run_id is not None and since_run_id != state.run.id:
            return _json(
                ok=False,
                skill="what_changed",
                error="unknown_run",
                since_run_id=since_run_id,
                current_run_id=state.run.id,
            )
        return _json(ok=True, skill="what_changed", run_id=state.run.id, changes=state.what_changed)

    @skill
    def nav_eval_report(self, run_id: str | None = None) -> str:
        store = self._require_store("nav_eval_report")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        if run_id is not None and run_id != state.run.id:
            return _json(
                ok=False,
                skill="nav_eval_report",
                error="unknown_run",
                run_id=run_id,
                current_run_id=state.run.id,
            )
        return _json(
            ok=True,
            skill="nav_eval_report",
            run_id=state.run.id,
            nav_summary=state.nav_summary.model_dump(mode="json") if state.nav_summary else None,
        )

    @skill
    def map_open_space(self) -> str:
        store = self._require_store("map_open_space")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        site_map = build_simulated_site_map(state.site, state.nav_events)
        store.set_site_map(site_map)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        return _json(
            ok=True,
            skill="map_open_space",
            run_id=state.run.id,
            map=map_summary(site_map),
        )

    @skill
    def set_route_plan(self, plan_json: str) -> str:
        store = self._require_store("set_route_plan")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        try:
            route_plan = RoutePlan.model_validate_json(plan_json)
        except ValueError as exc:
            return _json(ok=False, skill="set_route_plan", error="invalid_plan", message=str(exc))
        store.set_route_plan(route_plan)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        return _json(
            ok=True,
            skill="set_route_plan",
            waypoints=len(route_plan.waypoints),
            points_of_interest=len(route_plan.points_of_interest),
        )

    @skill
    def add_route_waypoint(self, target_id: str) -> str:
        store = self._require_store("add_route_waypoint")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        try:
            add_waypoint(state.route_plan, state.site, target_id)
        except KeyError:
            return _json(
                ok=False,
                skill="add_route_waypoint",
                error="unknown_target",
                target_id=target_id,
            )
        store.set_route_plan(state.route_plan)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        return _json(
            ok=True,
            skill="add_route_waypoint",
            target_id=target_id,
            waypoints=len(state.route_plan.waypoints),
        )

    @skill
    def add_point_of_interest(self, target_id: str, reading_keys_json: str = "[]") -> str:
        store = self._require_store("add_point_of_interest")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        try:
            reading_keys = json.loads(reading_keys_json)
        except json.JSONDecodeError:
            reading_keys = []
        if not isinstance(reading_keys, list):
            reading_keys = []
        try:
            add_point_of_interest(
                state.route_plan,
                state.site,
                target_id,
                reading_keys=[str(item) for item in reading_keys],
            )
        except KeyError:
            return _json(
                ok=False,
                skill="add_point_of_interest",
                error="unknown_target",
                target_id=target_id,
            )
        store.set_route_plan(state.route_plan)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        return _json(
            ok=True,
            skill="add_point_of_interest",
            target_id=target_id,
            points_of_interest=len(state.route_plan.points_of_interest),
        )

    @skill
    def run_route_plan(self) -> str:
        store = self._require_store("run_route_plan")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        next_nav_index = len(state.nav_events) + 1
        for offset, waypoint in enumerate(state.route_plan.waypoints):
            store.append_nav_event(
                NavEvent(
                    id=f"NAV-{next_nav_index + offset:03d}",
                    run_id=state.run.id,
                    ts=time.time(),
                    action=NavAction.goto,
                    target_id=waypoint.target_id,
                    success=True,
                    elapsed_s=3.0 + (offset * 0.5),
                    note="operator route simulation",
                )
            )
        state.nav_summary = summarize_nav_events(state.run.id, state.nav_events)
        site_map = build_simulated_site_map(state.site, state.nav_events)
        store.set_site_map(site_map)
        captures, readings = simulate_poi_captures(
            run_id=state.run.id,
            plan=state.route_plan,
            evidence_dir=self.run_dir / "evidence",
        )
        store.replace_poi_results(captures, readings)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        return _json(
            ok=True,
            skill="run_route_plan",
            run_id=state.run.id,
            waypoints_run=len(state.route_plan.waypoints),
            captures=len(captures),
            readings=len(readings),
        )

    @skill
    def poi_report(self) -> str:
        store = self._require_store("poi_report")
        if isinstance(store, str):
            return store
        state = store.state
        assert state is not None
        return _json(
            ok=True,
            skill="poi_report",
            run_id=state.run.id,
            captures=[capture.model_dump(mode="json") for capture in state.poi_captures],
            readings=[reading.model_dump(mode="json") for reading in state.sensor_readings],
        )

    @skill
    def dock_align(self, dock_id: str = "DOCK_1") -> str:
        site = read_site_config(self.site_path)
        if not any(entity.id == dock_id for entity in site.special_entities.values()):
            return _json(ok=False, skill="dock_align", error="unknown_dock", dock_id=dock_id)
        return _json(
            ok=True,
            skill="dock_align",
            dock_id=dock_id,
            simulated=True,
            aligned=True,
            guided=False,
        )

    @skill
    def portal_entry(self, portal_id: str = "PORTAL_1") -> str:
        site = read_site_config(self.site_path)
        if not any(entity.id == portal_id for entity in site.special_entities.values()):
            return _json(ok=False, skill="portal_entry", error="unknown_portal", portal_id=portal_id)
        return _json(
            ok=True,
            skill="portal_entry",
            portal_id=portal_id,
            simulated=True,
            door_open=True,
            entered=True,
            guided=False,
        )

    @skill
    def stop_mission(self) -> str:
        if not self._state_file().exists():
            return _json(ok=True, skill="stop_mission", state="not_started")
        store = DogOpsStore.load_existing(self.run_dir)
        state = store.state
        assert state is not None
        if state.run.state not in {MissionState.done, MissionState.failed, MissionState.stopped}:
            store.finish_run(
                state.run.id,
                MissionState.stopped,
                "Mission stopped by DogOpsSkillContainer.",
                ended_at=time.time(),
            )
        return _json(ok=True, skill="stop_mission", run_id=state.run.id, state=state.run.state)

    def _state_file(self) -> Path:
        return self.run_dir / "state.json"

    def _require_store(self, skill_name: str) -> DogOpsStore | str:
        if not self._state_file().exists():
            return _json(ok=False, skill=skill_name, error="missing_run", run_dir=str(self.run_dir))
        return DogOpsStore.load_existing(self.run_dir)


def _find_incident(incidents: list[Incident], incident_id: str) -> Incident | None:
    for incident in incidents:
        if incident.id == incident_id:
            return incident
    return None


def _find_work_order(work_orders: list[WorkOrder], work_order_id: str) -> WorkOrder | None:
    for work_order in work_orders:
        if work_order.id == work_order_id:
            return work_order
    return None


def _work_order_for_incident(work_orders: list[WorkOrder], incident_id: str) -> WorkOrder | None:
    for work_order in work_orders:
        if work_order.incident_id == incident_id:
            return work_order
    return None


def _json(**payload: object) -> str:
    return json.dumps(payload, sort_keys=True)
