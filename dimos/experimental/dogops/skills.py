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
from dimos.experimental.dogops.models import (
    Asset,
    AssetKind,
    Incident,
    IncidentState,
    IncidentType,
    MissionState,
    Severity,
    WorkOrder,
    WorkOrderState,
)
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
    def read_gauge(self, asset_id: str) -> str:
        site = read_site_config(self.site_path)
        asset = site.asset_by_id().get(asset_id)
        if asset is None:
            return _json(ok=False, skill="read_gauge", error="unknown_asset", asset_id=asset_id)

        max_celsius = asset.expected_state.get("max_celsius")
        if max_celsius is not None:
            reading = self._latest_fact(f"{asset.id}.temperature_c")
            if reading is None:
                reading = asset.expected_state.get("current_celsius", float(max_celsius) - 2.0)
            reading_c = float(reading)
            max_c = float(max_celsius)
            return _json(
                ok=True,
                skill="read_gauge",
                asset_id=asset.id,
                gauge_type="temperature",
                reading=reading_c,
                unit="celsius",
                max_celsius=max_c,
                status="normal" if reading_c <= max_c else "high_temperature",
            )

        status = self._asset_status(asset)
        return _json(
            ok=True,
            skill="read_gauge",
            asset_id=asset.id,
            gauge_type="status_card",
            reading=status,
            unit="status",
            expected_status=asset.expected_status,
            status=status,
        )

    @skill
    def check_clearance(self, asset_id: str) -> str:
        site = read_site_config(self.site_path)
        asset = site.asset_by_id().get(asset_id)
        if asset is None:
            return _json(ok=False, skill="check_clearance", error="unknown_asset", asset_id=asset_id)

        clearance_clear = self._clearance_for_asset(asset)
        if clearance_clear is None:
            return _json(
                ok=False,
                skill="check_clearance",
                error="no_clearance_expectation",
                asset_id=asset.id,
            )

        blockers = [] if clearance_clear else self._blocking_packages_for_asset(asset)
        return _json(
            ok=True,
            skill="check_clearance",
            asset_id=asset.id,
            clear=clearance_clear,
            status="clear" if clearance_clear else "blocked",
            blocking_package_ids=blockers,
        )

    @skill
    def detect_blocked_aisle(self, zone_id: str) -> str:
        site = read_site_config(self.site_path)
        if zone_id not in site.zone_by_id():
            return _json(
                ok=False, skill="detect_blocked_aisle", error="unknown_zone", zone_id=zone_id
            )

        aisle_assets = [
            asset
            for asset in site.assets
            if asset.zone_id == zone_id and asset.asset_kind == AssetKind.aisle_clearance
        ]
        blocked_assets = [
            {
                "asset_id": asset.id,
                "blocking_package_ids": self._blocking_packages_for_asset(asset),
            }
            for asset in aisle_assets
            if self._clearance_for_asset(asset) is False
        ]
        return _json(
            ok=True,
            skill="detect_blocked_aisle",
            zone_id=zone_id,
            blocked=bool(blocked_assets),
            blocked_assets=blocked_assets,
        )

    @skill
    def scan_receiving_manifest(self, zone_id: str) -> str:
        site = read_site_config(self.site_path)
        if zone_id not in site.zone_by_id():
            return _json(
                ok=False, skill="scan_receiving_manifest", error="unknown_zone", zone_id=zone_id
            )

        manifest = read_manifest(self.manifest_path)
        expected = sorted(
            item.package_id for item in manifest.items if item.expected_zone_id == zone_id
        )
        detected = sorted(self._detected_packages_for_zone(zone_id))
        missing = sorted(set(expected) - set(detected))
        unexpected = sorted(set(detected) - set(expected))
        return _json(
            ok=True,
            skill="scan_receiving_manifest",
            zone_id=zone_id,
            expected_packages=expected,
            detected_packages=detected,
            missing_packages=missing,
            unexpected_packages=unexpected,
            status="matched" if not missing and not unexpected else "mismatch",
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

    def _latest_fact(self, key: str) -> bool | str | int | float | None:
        mission = read_mission(self.mission_path)
        for observation in reversed(list(mission.simulation_observations.values())):
            if key in observation.facts:
                return observation.facts[key]
        return None

    def _clearance_for_asset(self, asset: Asset) -> bool | None:
        if self._state_file().exists():
            state = DogOpsStore.load_existing(self.run_dir).state
            assert state is not None
            active_blocker_types = {IncidentType.blocked_aisle, IncidentType.blocked_cooling}
            has_active_blocker = any(
                incident.entity_id == asset.id
                and incident.type in active_blocker_types
                and incident.state not in {IncidentState.resolved, IncidentState.false_positive}
                for incident in state.incidents
            )
            if has_active_blocker:
                return False

        fact = self._latest_fact(f"{asset.id}.clearance_clear")
        if isinstance(fact, bool):
            return fact
        return asset.expected_clear

    def _blocking_packages_for_asset(self, asset: Asset) -> list[str]:
        blockers = set(asset.blocking_package_ids)
        mission = read_mission(self.mission_path)
        for observation in mission.simulation_observations.values():
            for key, value in observation.facts.items():
                if key.endswith(".blocks_asset_id") and value == asset.id:
                    blockers.add(key.removesuffix(".blocks_asset_id"))
        return sorted(blockers)

    def _detected_packages_for_zone(self, zone_id: str) -> set[str]:
        detected: set[str] = set()
        mission = read_mission(self.mission_path)
        for observation in mission.simulation_observations.values():
            if observation.zone_id != zone_id:
                continue
            for key, value in observation.facts.items():
                if key.startswith("PKG-") and key.endswith(".zone_id") and value == zone_id:
                    detected.add(key.removesuffix(".zone_id"))
        return detected

    def _asset_status(self, asset: Asset) -> str:
        clearance = self._clearance_for_asset(asset)
        if clearance is False:
            return "blocked"
        if clearance is True and asset.expected_status is not None:
            return asset.expected_status
        return asset.expected_status or "unknown"


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
