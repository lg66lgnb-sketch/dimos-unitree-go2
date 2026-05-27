from __future__ import annotations

import math
from pathlib import Path
import threading
from typing import Any

from dimos.experimental.dogops.mapping import (
    build_dimos_path_payload,
    encode_dimos_costmap_full,
    DIMOS_OPTIMIZED_COSTMAP,
)
from dimos.experimental.dogops.models import MapCell, Pose2D, SiteMap
from dimos.experimental.dogops.store import DogOpsStore

try:  # pragma: no cover - exercised inside the full DimOS checkout.
    from dimos.core.core import rpc
    from dimos.core.module import Module
    from dimos.core.stream import In
    from dimos.msgs.geometry_msgs.PoseStamped import PoseStamped
    from dimos.msgs.nav_msgs.OccupancyGrid import OccupancyGrid
    from dimos.msgs.nav_msgs.Path import Path as DimosPath
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

    class Disposable:  # type: ignore[no-redef]
        def __init__(self, _unsubscribe: object) -> None:
            pass

    PoseStamped = Any  # type: ignore[assignment,misc]
    OccupancyGrid = Any  # type: ignore[assignment,misc]
    DimosPath = Any  # type: ignore[assignment,misc]


class DogOpsLiveMapModule(Module):
    """Persist live DimOS map/nav streams into DogOps dashboard artifacts.

    This is intentionally a bridge, not a DogOps mapping stack. The source of
    truth remains DimOS `global_costmap`, planner `path`, and `odom`.
    """

    global_costmap: In[OccupancyGrid]
    path: In[DimosPath]
    odom: In[PoseStamped]

    def __init__(self, *, run_dir: str | Path = ".dogops/runs/latest", **kwargs: object) -> None:
        try:
            super().__init__(**kwargs)
        except TypeError:
            pass
        self.run_dir = Path(run_dir)
        self._latest_costmap: Any | None = None
        self._latest_path: Any | None = None
        self._latest_odom: Any | None = None
        self._lock = threading.Lock()

    @rpc
    def start(self) -> None:
        if hasattr(super(), "start"):
            super().start()  # type: ignore[misc]
        self._subscribe_if_available("global_costmap", self._on_global_costmap)
        self._subscribe_if_available("path", self._on_path)
        self._subscribe_if_available("odom", self._on_odom)

    def ingest_snapshot(
        self,
        *,
        global_costmap: Any | None = None,
        path: Any | None = None,
        odom: Any | None = None,
    ) -> SiteMap:
        with self._lock:
            if global_costmap is not None:
                self._latest_costmap = global_costmap
            if path is not None:
                self._latest_path = path
            if odom is not None:
                self._latest_odom = odom
            return self._persist_locked()

    def _subscribe_if_available(self, attr: str, handler: Any) -> None:
        stream = getattr(self, attr, None)
        subscribe = getattr(stream, "subscribe", None)
        if subscribe is None:
            return
        unsubscribe = subscribe(handler)
        register = getattr(self, "register_disposable", None)
        if callable(register):
            register(Disposable(unsubscribe))

    def _on_global_costmap(self, msg: Any) -> None:
        self.ingest_snapshot(global_costmap=msg)

    def _on_path(self, msg: Any) -> None:
        self.ingest_snapshot(path=msg)

    def _on_odom(self, msg: Any) -> None:
        self.ingest_snapshot(odom=msg)

    def _persist_locked(self) -> SiteMap:
        store = DogOpsStore.load_existing(self.run_dir)
        state = store.state
        assert state is not None
        site_map = update_site_map_from_dimos_streams(
            state.site_map,
            global_costmap=self._latest_costmap,
            path=self._latest_path,
            odom=self._latest_odom,
        )
        store.set_site_map(site_map)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        return site_map


def update_site_map_from_dimos_streams(
    site_map: SiteMap,
    *,
    global_costmap: Any | None = None,
    path: Any | None = None,
    odom: Any | None = None,
) -> SiteMap:
    updated = site_map.model_copy(deep=True)
    updated.source = "dimos_live"
    if global_costmap is not None:
        _apply_global_costmap(updated, global_costmap)
    if path is not None:
        updated.explored_path = _poses_from_path(path)
        updated.dimos_path = _path_payload_from_dimos_path(updated.explored_path)
    if odom is not None:
        updated.robot_pose = _pose_from_pose_stamped(odom)
    updated.notes = [
        "Map geometry is sourced from DimOS global_costmap/path/odom streams.",
        "DogOps overlays add semantic zones, assets, route waypoints, POIs, and incidents.",
    ]
    return updated


def _apply_global_costmap(site_map: SiteMap, costmap: Any) -> None:
    grid = _grid_values(costmap)
    height = len(grid)
    width = len(grid[0]) if grid else 0
    resolution = float(getattr(costmap, "resolution", 0.5) or 0.5)
    origin_pose = _costmap_origin(costmap)
    site_map.frame = str(getattr(costmap, "frame_id", site_map.frame) or site_map.frame)
    site_map.resolution_m = resolution
    site_map.width_m = width * resolution
    site_map.height_m = height * resolution
    site_map.origin = origin_pose
    site_map.cells = [
        MapCell(
            x_index=x_index,
            y_index=y_index,
            state=_cell_state_from_cost(value),
            confidence=1.0,
        )
        for y_index, row in enumerate(grid)
        for x_index, value in enumerate(row)
    ]
    site_map.coverage_ratio = _coverage_ratio(grid)
    site_map.cell_stats = _grid_stats(grid)
    site_map.dimos_costmap = _costmap_payload_from_dimos_costmap(site_map, grid)
    site_map.status = "mapped"


def _grid_values(costmap: Any) -> list[list[int]]:
    grid = getattr(costmap, "grid", costmap)
    if hasattr(grid, "tolist"):
        grid = grid.tolist()
    return [[int(value) for value in row] for row in grid]


def _costmap_origin(costmap: Any) -> Pose2D:
    origin = getattr(costmap, "origin", None)
    position = getattr(origin, "position", None)
    if position is None and isinstance(origin, dict):
        position = origin.get("position") or origin
    x = _field(position, "x", 0.0)
    y = _field(position, "y", 0.0)
    return Pose2D(x=x, y=y, theta_deg=0.0, frame="world", source="dimos_global_costmap")


def _poses_from_path(path: Any) -> list[Pose2D]:
    poses = getattr(path, "poses", path)
    result: list[Pose2D] = []
    for pose in poses or []:
        result.append(_pose_from_pose_stamped(pose, source="dimos_path"))
    return result


def _pose_from_pose_stamped(pose: Any, *, source: str = "dimos_odom") -> Pose2D:
    position = getattr(pose, "position", None)
    orientation = getattr(pose, "orientation", None)
    if position is None and hasattr(pose, "pose"):
        position = getattr(pose.pose, "position", None)
        orientation = getattr(pose.pose, "orientation", None)
    if isinstance(pose, dict):
        position = pose.get("position") or pose.get("pose", {}).get("position")
        orientation = pose.get("orientation") or pose.get("pose", {}).get("orientation")
    return Pose2D(
        x=_field(position, "x", 0.0),
        y=_field(position, "y", 0.0),
        theta_deg=_yaw_degrees(orientation),
        frame=str(getattr(pose, "frame_id", "world") or "world"),
        source=source,
    )


def _path_payload_from_dimos_path(points: list[Pose2D]) -> dict[str, Any]:
    payload = build_dimos_path_payload(points)
    payload["source_module"] = "dimos.navigation.replanning_a_star.module.ReplanningAStarPlanner.path"
    return payload


def _costmap_payload_from_dimos_costmap(site_map: SiteMap, grid: list[list[int]]) -> dict[str, Any]:
    return {
        "type": "costmap",
        "grid": encode_dimos_costmap_full(grid),
        "origin": {
            "type": "vector",
            "c": [site_map.origin.x or 0.0, site_map.origin.y or 0.0, 0],
        },
        "resolution": site_map.resolution_m,
        "origin_theta": 0,
        "source_module": "dimos.mapping.costmapper.CostMapper.global_costmap",
        "encoder": DIMOS_OPTIMIZED_COSTMAP,
    }


def _coverage_ratio(grid: list[list[int]]) -> float:
    stats = _grid_stats(grid)
    total = int(stats["total"])
    return (int(stats["known"]) / total) if total else 0.0


def _grid_stats(grid: list[list[int]]) -> dict[str, int | float]:
    values = [value for row in grid for value in row]
    total = len(values)
    unknown = len([value for value in values if value == -1])
    free = len([value for value in values if value == 0])
    occupied = len([value for value in values if value > 0])
    known = total - unknown
    return {
        "total": total,
        "known": known,
        "unknown": unknown,
        "free": free,
        "occupied": occupied,
        "coverage_ratio": (known / total) if total else 0.0,
    }


def _cell_state_from_cost(value: int) -> str:
    if value == -1:
        return "unknown"
    if value > 0:
        return "occupied"
    return "free"


def _field(value: Any, field: str, default: float) -> float:
    if isinstance(value, (list, tuple)):
        index = {"x": 0, "y": 1, "z": 2, "w": 3}.get(field)
        if index is not None and len(value) > index:
            raw = value[index]
        else:
            raw = default
        return float(default if raw is None else raw)
    if isinstance(value, dict):
        raw = value.get(field, default)
    else:
        raw = getattr(value, field, default)
    return float(default if raw is None else raw)


def _yaw_degrees(orientation: Any) -> float:
    if orientation is None:
        return 0.0
    x = _field(orientation, "x", 0.0)
    y = _field(orientation, "y", 0.0)
    z = _field(orientation, "z", 0.0)
    w = _field(orientation, "w", 1.0)
    siny_cosp = 2.0 * ((w * z) + (x * y))
    cosy_cosp = 1.0 - (2.0 * ((y * y) + (z * z)))
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))
