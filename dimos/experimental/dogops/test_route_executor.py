import math

import pytest

from dimos.experimental.dogops.mapping import build_default_route_plan
from dimos.experimental.dogops.models import Pose2D
from dimos.experimental.dogops.route_executor import execute_route_plan, pose_to_dimos_goal
from dimos.experimental.dogops.config_loader import load_dogops_config


def test_route_executor_publishes_waypoint_goals_and_records_nav_events() -> None:
    config = load_dogops_config()
    route_plan = build_default_route_plan(config.site)
    published = []

    events = execute_route_plan(
        route_plan,
        publish_goal=published.append,
        wait_for_goal_reached=lambda _timeout_s: True,
        run_id="run-1",
        timeout_s=0.01,
    )

    assert len(published) == len(route_plan.waypoints)
    assert len(events) == len(route_plan.waypoints)
    assert all(event.success for event in events)
    assert events[0].target_id == route_plan.waypoints[0].target_id


def test_route_executor_stops_on_required_goal_timeout() -> None:
    config = load_dogops_config()
    route_plan = build_default_route_plan(config.site)
    published = []

    events = execute_route_plan(
        route_plan,
        publish_goal=published.append,
        wait_for_goal_reached=lambda _timeout_s: False,
        run_id="run-1",
        timeout_s=0.01,
    )

    assert len(published) == 1
    assert len(events) == 1
    assert events[0].success is False
    assert "timeout" in events[0].note


def test_pose_to_dimos_goal_preserves_heading() -> None:
    goal = pose_to_dimos_goal(Pose2D(x=1.0, y=2.0, theta_deg=90.0, frame="world"))
    orientation = getattr(goal, "orientation", None)
    if isinstance(goal, dict):
        orientation = goal["orientation"]
    z = orientation["z"] if isinstance(orientation, dict) else getattr(orientation, "z")
    w = orientation["w"] if isinstance(orientation, dict) else getattr(orientation, "w")

    assert z == pytest.approx(math.sqrt(0.5))
    assert w == pytest.approx(math.sqrt(0.5))
