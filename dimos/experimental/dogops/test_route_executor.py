from __future__ import annotations

import pytest

from dimos.experimental.dogops.map_authoring import (
    EditableMapPoint,
    EditableRoute,
    EditableRouteWaypoint,
    MapAuthoringState,
    save_map_authoring,
)
from dimos.experimental.dogops.mission_engine import run_offline_simulation
from dimos.experimental.dogops.route_actions import EditableRouteAction
from dimos.experimental.dogops.route_executor import (
    CallableGoalPublisher,
    DogOpsRouteExecutor,
    RouteExecutionError,
    load_route_execution,
    request_route_stop,
    route_feedback_from_snapshot,
    route_execution_lock,
    save_route_execution,
)
from dimos.experimental.dogops.route_run_store import RouteRunStore


def _route(route_id: str = "ROUTE_A") -> EditableRoute:
    return EditableRoute(
        id=route_id,
        label="Route A",
        waypoints=[
            EditableRouteWaypoint(
                id="WP-1",
                label="One",
                target_id="CHECKPOINT_1",
                pose=EditableMapPoint(x=1.0, y=2.0),
            ),
            EditableRouteWaypoint(
                id="WP-2",
                label="Two",
                target_id="CHECKPOINT_2",
                pose=EditableMapPoint(x=2.0, y=2.5),
            ),
        ],
    )


def _save_authoring(tmp_path, *, selected_route_id: str | None = "ROUTE_A") -> None:
    save_map_authoring(
        tmp_path,
        MapAuthoringState(
            selected_route_id=selected_route_id,
            routes=[_route("ROUTE_A"), _route("ROUTE_B")],
        ),
    )


def test_dry_run_resolves_selected_route_without_publishing(tmp_path) -> None:
    _save_authoring(tmp_path, selected_route_id="ROUTE_A")
    published: list[tuple[float, float]] = []
    executor = DogOpsRouteExecutor(
        tmp_path,
        goal_publisher=CallableGoalPublisher(
            lambda x, y, z, frame: published.append((x, y))
        ),
    )

    state = executor.follow_route(dry_run=True)

    assert state.state == "completed"
    assert state.route_id == "ROUTE_A"
    assert state.transport == "dry_run"
    assert [event.waypoint_id for event in state.events] == ["WP-1", "WP-2"]
    assert [event.state for event in state.events] == ["queued", "queued"]
    assert published == []
    assert load_route_execution(tmp_path).route_id == "ROUTE_A"


def test_explicit_route_id_overrides_selected_route(tmp_path) -> None:
    _save_authoring(tmp_path, selected_route_id="ROUTE_A")

    state = DogOpsRouteExecutor(tmp_path).follow_route("ROUTE_B", dry_run=True)

    assert state.route_id == "ROUTE_B"


def test_missing_and_empty_routes_are_rejected(tmp_path) -> None:
    save_map_authoring(tmp_path, MapAuthoringState(routes=[]))
    executor = DogOpsRouteExecutor(tmp_path)

    with pytest.raises(RouteExecutionError, match="no route_id"):
        executor.follow_route(dry_run=True)

    save_map_authoring(
        tmp_path,
        MapAuthoringState(
            selected_route_id="EMPTY",
            routes=[EditableRoute(id="EMPTY", label="Empty")],
        ),
    )
    with pytest.raises(RouteExecutionError, match="no waypoints"):
        executor.follow_route(dry_run=True)

    save_map_authoring(
        tmp_path,
        MapAuthoringState(selected_route_id=None, routes=[_route("ROUTE_A")]),
    )
    with pytest.raises(RouteExecutionError, match="no route_id"):
        executor.follow_route(dry_run=True)


def test_fake_publisher_receives_goals_in_order_and_waits_for_odom(tmp_path) -> None:
    _save_authoring(tmp_path)
    published: list[tuple[float, float, str]] = []
    current_goal = {"x": 0.0, "y": 0.0}

    def publish(x: float, y: float, z: float, frame: str) -> dict[str, object]:
        published.append((x, y, frame))
        current_goal.update({"x": x, "y": y})
        return {"accepted": True}

    def snapshot() -> dict[str, object]:
        return {
            "robot_pose": {"x": current_goal["x"], "y": current_goal["y"]},
            "target": {"x": current_goal["x"], "y": current_goal["y"]},
            "topics": {"odom": {"age_s": 0.1}},
        }

    executor = DogOpsRouteExecutor(
        tmp_path,
        goal_publisher=CallableGoalPublisher(publish, transport_name="fake_nav"),
        live_snapshot_reader=snapshot,
        waypoint_timeout_s=0.1,
        sleep_fn=lambda _: None,
    )

    state = executor.follow_route()

    assert state.state == "completed"
    assert state.waypoints_reached == 2
    assert published == [(1.0, 2.0, "world"), (2.0, 2.5, "world")]
    assert [event.state for event in state.events] == [
        "queued",
        "sent",
        "reached",
        "queued",
        "sent",
        "reached",
    ]


def test_route_actions_record_timeline_and_placeholder_evidence(tmp_path) -> None:
    route = EditableRoute(
        id="ROUTE_ACTIONS",
        label="Route Actions",
        waypoints=[
            EditableRouteWaypoint(
                id="WP-ACTION",
                label="Waypoint",
                target_id="COOLING_1",
                pose=EditableMapPoint(x=1.0, y=2.0),
                actions=[
                    EditableRouteAction(
                        id="SCAN-TAGS",
                        kind="scan_tags",
                        args={"expected": [41]},
                    ),
                    EditableRouteAction(
                        id="CAPTURE",
                        kind="capture_image",
                        args={"target": "COOLING_1"},
                    ),
                ],
            )
        ],
    )
    save_map_authoring(
        tmp_path,
        MapAuthoringState(selected_route_id="ROUTE_ACTIONS", routes=[route]),
    )
    current_goal = {"x": 0.0, "y": 0.0}

    def publish(x: float, y: float, z: float, frame: str) -> dict[str, object]:
        current_goal.update({"x": x, "y": y})
        return {"accepted": True}

    executor = DogOpsRouteExecutor(
        tmp_path,
        goal_publisher=CallableGoalPublisher(publish, transport_name="fake_nav"),
        live_snapshot_reader=lambda: {
            "robot_pose": {"x": current_goal["x"], "y": current_goal["y"]},
            "target": {"x": current_goal["x"], "y": current_goal["y"]},
            "topics": {"odom": {"age_s": 0.1}},
        },
        sleep_fn=lambda _: None,
    )

    state = executor.follow_route()

    assert state.state == "completed"
    assert state.route_run_id
    action_events = [event for event in state.events if event.kind == "action"]
    assert [event.action_id for event in action_events] == [
        "SCAN-TAGS",
        "SCAN-TAGS",
        "CAPTURE",
        "CAPTURE",
    ]
    assert action_events[-1].payload["source"] == "demo_placeholder"
    evidence = RouteRunStore(tmp_path).route_run_evidence(state.route_run_id)
    assert evidence[0]["kind"] == "image"
    assert evidence[0]["metadata"]["source"] == "demo_placeholder"
    assert (tmp_path / "route_runs" / state.route_run_id / "evidence" / "WP-ACTION-CAPTURE.svg").exists()


def test_route_action_exception_marks_route_failed(tmp_path) -> None:
    route = EditableRoute(
        id="ROUTE_BAD_ACTION",
        label="Route Bad Action",
        waypoints=[
            EditableRouteWaypoint(
                id="WP-BAD",
                label="Waypoint",
                pose=EditableMapPoint(x=1.0, y=2.0),
                actions=[
                    EditableRouteAction(
                        id="BAD-SCAN",
                        kind="scan_tags",
                        args={"expected": ["not-an-int"]},
                    ),
                ],
            )
        ],
    )
    save_map_authoring(
        tmp_path,
        MapAuthoringState(selected_route_id="ROUTE_BAD_ACTION", routes=[route]),
    )
    current_goal = {"x": 0.0, "y": 0.0}

    def publish(x: float, y: float, z: float, frame: str) -> dict[str, object]:
        current_goal.update({"x": x, "y": y})
        return {"accepted": True}

    executor = DogOpsRouteExecutor(
        tmp_path,
        goal_publisher=CallableGoalPublisher(publish, transport_name="fake_nav"),
        live_snapshot_reader=lambda: {
            "robot_pose": {"x": current_goal["x"], "y": current_goal["y"]},
            "target": {"x": current_goal["x"], "y": current_goal["y"]},
            "topics": {"odom": {"age_s": 0.1}},
        },
        sleep_fn=lambda _: None,
    )

    state = executor.follow_route()

    assert state.state == "failed"
    assert state.route_run_id
    assert "invalid literal" in (state.last_error or "")
    assert load_route_execution(tmp_path).state == "failed"
    failed_action = [event for event in state.events if event.action_id == "BAD-SCAN"][-1]
    assert failed_action.state == "failed"
    assert failed_action.payload["error"] == "ValueError"
    route_run = RouteRunStore(tmp_path).route_run_detail(state.route_run_id)
    assert route_run is not None
    assert route_run["state"] == "failed"


def test_stale_odom_causes_timeout_failure(tmp_path) -> None:
    _save_authoring(tmp_path)
    now = 0.0

    def time_fn() -> float:
        return now

    def sleep_fn(seconds: float) -> None:
        nonlocal now
        now += seconds

    executor = DogOpsRouteExecutor(
        tmp_path,
        goal_publisher=CallableGoalPublisher(lambda *_: {"accepted": True}),
        live_snapshot_reader=lambda: {
            "robot_pose": {"x": 0.0, "y": 0.0},
            "target": {"x": 1.0, "y": 2.0},
            "topics": {"odom": {"age_s": 99.0}},
        },
        waypoint_timeout_s=0.25,
        poll_interval_s=0.1,
        time_fn=time_fn,
        sleep_fn=sleep_fn,
    )

    state = executor.follow_route()

    assert state.state == "failed"
    assert state.last_error == "odom stale: 99.0s"
    assert state.events[-1].state == "timeout"


def test_stop_request_interrupts_execution(tmp_path) -> None:
    _save_authoring(tmp_path)
    now = 0.0
    stopped = False

    def time_fn() -> float:
        return now

    def sleep_fn(seconds: float) -> None:
        nonlocal now, stopped
        now += seconds
        if not stopped:
            stopped = True
            state = load_route_execution(tmp_path)
            state.stop_requested = True
            save_route_execution(tmp_path, state)

    executor = DogOpsRouteExecutor(
        tmp_path,
        goal_publisher=CallableGoalPublisher(lambda *_: {"accepted": True}),
        live_snapshot_reader=lambda: {
            "robot_pose": {"x": -10.0, "y": -10.0},
            "target": {"x": 1.0, "y": 2.0},
            "topics": {"odom": {"age_s": 0.1}},
        },
        waypoint_timeout_s=2.0,
        poll_interval_s=0.1,
        time_fn=time_fn,
        sleep_fn=sleep_fn,
    )

    state = executor.follow_route()

    assert state.state == "stopped"
    assert state.stop_requested is True
    assert state.events[-1].state == "stopped"


def test_completed_route_appends_nav_events_and_report(tmp_path) -> None:
    run_offline_simulation(out=tmp_path)
    _save_authoring(tmp_path)
    current_goal = {"x": 0.0, "y": 0.0}

    def publish(x: float, y: float, z: float, frame: str) -> dict[str, object]:
        current_goal.update({"x": x, "y": y})
        return {"accepted": True}

    executor = DogOpsRouteExecutor(
        tmp_path,
        goal_publisher=CallableGoalPublisher(publish, transport_name="fake_nav"),
        live_snapshot_reader=lambda: {
            "robot_pose": {"x": current_goal["x"], "y": current_goal["y"]},
            "target": {"x": current_goal["x"], "y": current_goal["y"]},
            "topics": {"odom": {"age_s": 0.1}},
        },
        sleep_fn=lambda _: None,
    )

    state = executor.follow_route()

    assert state.state == "completed"
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "live route ROUTE_A: reached CHECKPOINT_1 via fake_nav" in report
    stored = (tmp_path / "nav_events.jsonl").read_text(encoding="utf-8")
    assert "CHECKPOINT_1" in stored
    assert "CHECKPOINT_2" in stored
    assert '"error_m": 0.0' in stored
    assert '"guided": false' in stored
    assert '"retries": 0' in stored


def test_repeated_route_runs_append_distinct_nav_evidence(tmp_path) -> None:
    run_offline_simulation(out=tmp_path)
    _save_authoring(tmp_path)
    current_goal = {"x": 0.0, "y": 0.0}

    def publish(x: float, y: float, z: float, frame: str) -> dict[str, object]:
        current_goal.update({"x": x, "y": y})
        return {"accepted": True}

    executor = DogOpsRouteExecutor(
        tmp_path,
        goal_publisher=CallableGoalPublisher(publish, transport_name="fake_nav"),
        live_snapshot_reader=lambda: {
            "robot_pose": {"x": current_goal["x"], "y": current_goal["y"]},
            "target": {"x": current_goal["x"], "y": current_goal["y"]},
            "topics": {"odom": {"age_s": 0.1}},
        },
        sleep_fn=lambda _: None,
    )

    first = executor.follow_route()
    second = executor.follow_route()

    assert first.state == "completed"
    assert second.state == "completed"
    stored = (tmp_path / "nav_events.jsonl").read_text(encoding="utf-8")
    assert stored.count("live route ROUTE_A: reached CHECKPOINT_1 via fake_nav") == 2


def test_no_progress_is_recorded_before_timeout(tmp_path) -> None:
    _save_authoring(tmp_path)
    now = 0.0

    def sleep_fn(seconds: float) -> None:
        nonlocal now
        now += seconds

    executor = DogOpsRouteExecutor(
        tmp_path,
        goal_publisher=CallableGoalPublisher(lambda *_: {"accepted": True}),
        live_snapshot_reader=lambda: {
            "robot_pose": {"x": -10.0, "y": -10.0},
            "target": {"x": 1.0, "y": 2.0},
            "topics": {"odom": {"age_s": 0.1}},
        },
        waypoint_timeout_s=5.0,
        no_progress_timeout_s=0.3,
        poll_interval_s=0.1,
        time_fn=lambda: now,
        sleep_fn=sleep_fn,
    )

    state = executor.follow_route()

    assert state.state == "failed"
    assert state.last_error == "no progress toward waypoint"
    assert state.events[-1].note == "no progress toward waypoint"


def test_unconfirmed_goal_does_not_mark_waypoint_reached(tmp_path) -> None:
    _save_authoring(tmp_path)

    executor = DogOpsRouteExecutor(
        tmp_path,
        goal_publisher=CallableGoalPublisher(lambda *_: {"accepted": True}),
        live_snapshot_reader=lambda: {
            "robot_pose": {"x": 1.0, "y": 2.0},
            "topics": {"odom": {"age_s": 0.1}},
        },
        waypoint_timeout_s=0.1,
        sleep_fn=lambda _: None,
    )

    state = executor.follow_route()

    assert state.state == "failed"
    assert "unconfirmed" in state.last_error


def test_concurrent_route_start_is_rejected(tmp_path) -> None:
    _save_authoring(tmp_path)
    state = DogOpsRouteExecutor(tmp_path).follow_route(dry_run=True)
    state.state = "running"
    save_route_execution(tmp_path, state)

    with route_execution_lock(tmp_path):
        with pytest.raises(RouteExecutionError, match="already running"):
            DogOpsRouteExecutor(tmp_path).follow_route(dry_run=True)

    # The failed attempt must not leave behind a stale lock.
    state.state = "completed"
    save_route_execution(tmp_path, state)
    state = DogOpsRouteExecutor(tmp_path).follow_route(dry_run=True)
    assert state.state == "completed"


def test_route_feedback_from_snapshot_handles_odom_age() -> None:
    odom, age_s = route_feedback_from_snapshot(
        {"robot_pose": {"x": "1.5", "y": 2}, "topics": {"odom": {"age_s": 0.4}}}
    )

    assert odom == {"x": 1.5, "y": 2.0}
    assert age_s == 0.4


def test_request_route_stop_sets_server_side_stop_flag(tmp_path) -> None:
    _save_authoring(tmp_path)
    state = DogOpsRouteExecutor(tmp_path).follow_route(dry_run=True)
    state.state = "running"
    state.stop_requested = False
    save_route_execution(tmp_path, state)

    stopped = request_route_stop(tmp_path, now=lambda: 123.0)

    assert stopped.state == "stopped"
    assert stopped.stop_requested is True
    assert stopped.completed_at == 123.0
    assert load_route_execution(tmp_path).stop_requested is True


def test_stop_route_invokes_transport_stop_handler(tmp_path) -> None:
    _save_authoring(tmp_path)
    calls: list[str] = []
    state = DogOpsRouteExecutor(tmp_path).follow_route(dry_run=True)
    state.state = "running"
    save_route_execution(tmp_path, state)

    stopped = DogOpsRouteExecutor(tmp_path, stop_handler=lambda: calls.append("stop")).stop_route()

    assert stopped.state == "stopped"
    assert calls == ["stop"]
