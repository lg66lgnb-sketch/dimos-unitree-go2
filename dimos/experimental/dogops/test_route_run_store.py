from __future__ import annotations

from dimos.experimental.dogops.map_authoring import (
    EditableMapPoint,
    EditableRoute,
    EditableRouteWaypoint,
    MapAuthoringState,
    save_map_authoring,
)
from dimos.experimental.dogops.route_executor import DogOpsRouteExecutor
from dimos.experimental.dogops.route_run_store import RouteRunStore, route_run_db_path


def _save_route(run_dir, route_id: str) -> None:
    save_map_authoring(
        run_dir,
        MapAuthoringState(
            selected_route_id=route_id,
            routes=[
                EditableRoute(
                    id=route_id,
                    label=route_id,
                    waypoints=[
                        EditableRouteWaypoint(
                            id=f"{route_id}-WP-1",
                            label="Waypoint",
                            pose=EditableMapPoint(x=1.0, y=2.0),
                        )
                    ],
                )
            ],
        ),
    )


def test_route_run_history_is_global_across_run_dirs(tmp_path) -> None:
    first = tmp_path / ".dogops" / "runs" / "first"
    second = tmp_path / ".dogops" / "runs" / "second"
    _save_route(first, "ROUTE_A")
    _save_route(second, "ROUTE_B")

    DogOpsRouteExecutor(first).follow_route(dry_run=True)
    DogOpsRouteExecutor(second).follow_route(dry_run=True)

    assert route_run_db_path(first) == tmp_path / ".dogops" / "dogops.sqlite"
    runs = RouteRunStore(first).list_route_runs()
    assert {run["dogops_run_id"] for run in runs} == {"first", "second"}
    assert {run["route_id"] for run in runs} == {"ROUTE_A", "ROUTE_B"}


def test_every_route_run_gets_distinct_history_record(tmp_path) -> None:
    run_dir = tmp_path / ".dogops" / "runs" / "latest"
    _save_route(run_dir, "ROUTE_A")

    first = DogOpsRouteExecutor(run_dir).follow_route(dry_run=True)
    second = DogOpsRouteExecutor(run_dir).follow_route(dry_run=True)

    assert first.route_run_id
    assert second.route_run_id
    assert first.route_run_id != second.route_run_id
    runs = RouteRunStore(run_dir).list_route_runs()
    assert [run["route_run_id"] for run in runs] == [second.route_run_id, first.route_run_id]
    assert (run_dir / "route_runs" / first.route_run_id / "events.jsonl").exists()
    assert (run_dir / "route_runs" / second.route_run_id / "route_run.json").exists()


def test_mission_steps_provide_default_route_actions(tmp_path) -> None:
    run_dir = tmp_path / ".dogops" / "runs" / "latest"
    from dimos.experimental.dogops.mission_engine import run_offline_simulation

    run_offline_simulation(out=run_dir)
    save_map_authoring(
        run_dir,
        MapAuthoringState(
            selected_route_id="ROUTE_DEFAULTS",
            routes=[
                EditableRoute(
                    id="ROUTE_DEFAULTS",
                    label="Route Defaults",
                    waypoints=[
                        EditableRouteWaypoint(
                            id="WP-COOLING",
                            label="Cooling",
                            target_id="COOLING_1",
                            pose=EditableMapPoint(x=1.0, y=2.0),
                        )
                    ],
                )
            ],
        ),
    )

    state = DogOpsRouteExecutor(run_dir).follow_route(dry_run=True)
    route_run = RouteRunStore(run_dir).route_run_detail(state.route_run_id or "")

    assert route_run is not None
    assert route_run["actions_total"] >= 2
    action_ids = [
        action["id"]
        for waypoint in route_run["selected_route_snapshot"]["waypoints"]
        for action in waypoint["actions"]
    ]
    assert {"inspect_cooling", "wait_for_human_fix", "verify_cooling"} & set(action_ids)
