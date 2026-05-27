from __future__ import annotations

import math
from pathlib import Path
import time
from typing import Any, Callable

from dimos.experimental.dogops.mapping import simulate_poi_captures
from dimos.experimental.dogops.models import NavAction, NavEvent, Pose2D, RoutePlan, RouteWaypoint
from dimos.experimental.dogops.nav_eval import summarize_nav_events
from dimos.experimental.dogops.store import DogOpsStore

try:  # pragma: no cover - exercised inside the full DimOS checkout.
    from dimos.core.core import rpc
    from dimos.core.module import Module
    from dimos.core.stream import In, Out
    from dimos.msgs.geometry_msgs.PoseStamped import PoseStamped
    from dimos_lcm.std_msgs import Bool
    from reactivex.disposable import Disposable
except ModuleNotFoundError:  # pragma: no cover - local package fallback.

    def rpc(fn: Any) -> Any:
        return fn

    class Module:
        @classmethod
        def blueprint(cls, **kwargs: object) -> dict[str, object]:
            return {"module": cls.__name__, "kwargs": kwargs}

    class In:  # type: ignore[no-redef]
        def __class_getitem__(cls, _item: object) -> type["In"]:
            return cls

    class Out:  # type: ignore[no-redef]
        def __class_getitem__(cls, _item: object) -> type["Out"]:
            return cls

    class Disposable:  # type: ignore[no-redef]
        def __init__(self, _unsubscribe: object) -> None:
            pass

    class Bool:  # type: ignore[no-redef]
        def __init__(self, data: bool = False) -> None:
            self.data = data

    PoseStamped = Any  # type: ignore[assignment,misc]


class DogOpsRouteExecutorModule(Module):
    """Send DogOps route waypoints to the DimOS planner goal stream."""

    goal_request: Out[PoseStamped]
    goal_reached: In[Bool]

    def __init__(self, *, run_dir: str | Path = ".dogops/runs/latest", **kwargs: object) -> None:
        try:
            super().__init__(**kwargs)
        except TypeError:
            pass
        self.run_dir = Path(run_dir)
        self._last_goal_reached = False

    @rpc
    def start(self) -> None:
        if hasattr(super(), "start"):
            super().start()  # type: ignore[misc]
        stream = getattr(self, "goal_reached", None)
        subscribe = getattr(stream, "subscribe", None)
        if subscribe is None:
            return
        unsubscribe = subscribe(self._on_goal_reached)
        register = getattr(self, "register_disposable", None)
        if callable(register):
            register(Disposable(unsubscribe))

    @rpc
    def run_route_plan(self, run_dir: str | Path | None = None, timeout_s: float = 30.0) -> dict[str, Any]:
        root = Path(run_dir) if run_dir is not None else self.run_dir
        store = DogOpsStore.load_existing(root)
        state = store.state
        assert state is not None
        events = execute_route_plan(
            state.route_plan,
            publish_goal=self._publish_goal,
            wait_for_goal_reached=self._wait_for_goal_reached,
            run_id=state.run.id,
            timeout_s=timeout_s,
            start_index=len(state.nav_events) + 1,
        )
        for event in events:
            store.append_nav_event(event)
        state.nav_summary = summarize_nav_events(state.run.id, state.nav_events)
        captures, readings = simulate_poi_captures(
            run_id=state.run.id,
            plan=state.route_plan,
            evidence_dir=root / "evidence",
        )
        store.replace_poi_results(captures, readings)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        return {
            "ok": True,
            "waypoints": len(state.route_plan.waypoints),
            "nav_events": len(events),
            "captures": len(captures),
            "readings": len(readings),
        }

    def _on_goal_reached(self, msg: Bool) -> None:
        self._last_goal_reached = bool(getattr(msg, "data", msg))

    def _publish_goal(self, waypoint: RouteWaypoint) -> None:
        goal = pose_to_dimos_goal(waypoint.pose)
        publisher = getattr(getattr(self, "goal_request", None), "publish", None)
        if not callable(publisher):
            raise RuntimeError("DogOpsRouteExecutorModule.goal_request is not connected")
        self._last_goal_reached = False
        publisher(goal)

    def _wait_for_goal_reached(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._last_goal_reached:
                return True
            time.sleep(0.05)
        return False


def execute_route_plan(
    route_plan: RoutePlan,
    *,
    publish_goal: Callable[[RouteWaypoint], None],
    wait_for_goal_reached: Callable[[float], bool],
    run_id: str,
    timeout_s: float,
    start_index: int = 1,
) -> list[NavEvent]:
    events: list[NavEvent] = []
    for offset, waypoint in enumerate(sorted(route_plan.waypoints, key=lambda item: item.order)):
        started = time.monotonic()
        publish_goal(waypoint)
        reached = wait_for_goal_reached(timeout_s)
        events.append(
            NavEvent(
                id=f"NAV-{start_index + offset:03d}",
                run_id=run_id,
                ts=time.time(),
                action=NavAction.goto,
                target_id=waypoint.target_id,
                success=reached,
                elapsed_s=time.monotonic() - started,
                guided=False,
                note=(
                    "DimOS planner goal reached"
                    if reached
                    else "DimOS planner goal timeout; operator intervention required"
                ),
            )
        )
        if not reached and waypoint.required:
            break
    return events


def pose_to_dimos_goal(pose: Pose2D) -> Any:
    orientation = _yaw_quaternion(pose.theta_deg or 0.0)
    try:
        return PoseStamped(
            frame_id=pose.frame,
            position=[pose.x or 0.0, pose.y or 0.0, 0.0],
            orientation=orientation,
        )
    except TypeError:
        return {
            "frame_id": pose.frame,
            "position": {"x": pose.x or 0.0, "y": pose.y or 0.0, "z": 0.0},
            "orientation": {
                "x": orientation[0],
                "y": orientation[1],
                "z": orientation[2],
                "w": orientation[3],
            },
        }


def _yaw_quaternion(theta_deg: float) -> list[float]:
    half_yaw = math.radians(theta_deg) / 2.0
    return [0.0, 0.0, math.sin(half_yaw), math.cos(half_yaw)]
