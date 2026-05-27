from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import socket
import time
from typing import Any, Literal
from urllib.parse import urlparse

from dimos.experimental.dogops.mapping import decode_dimos_costmap_full
from dimos.experimental.dogops.store import DogOpsStore

DEFAULT_RERUN_SOURCE_URL = "rerun+http://127.0.0.1:9877/proxy"
NATIVE_3D_START_HINT = (
    "native-3d mode requires an existing DimOS Go2 Rerun stream. Start the native "
    "simulator first, for example from the full DimOS checkout: "
    "uv run dimos --simulation --viewer rerun --rerun-open none --rerun-web run unitree-go2"
)
IMAGE_WIDTH_PX = 720
IMAGE_HEIGHT_PX = 420
IMAGE_PAD_PX = 34
RERUN_COMMAND_FILENAME = "rerun_command.json"
RERUN_MAPPING_REPLAY_FRAMES = 72
RERUN_MAPPING_REPLAY_DELAY_S = 0.12
RerunViewMode = Literal["dogops-2d", "native-3d"]


@dataclass(frozen=True)
class MapProjection:
    width_px: int
    height_px: int
    pad_px: int
    origin_x: float
    origin_y: float
    map_width_m: float
    map_height_m: float
    resolution_m: float

    def pixel(self, x: float, y: float) -> list[float]:
        usable_w = self.width_px - (2 * self.pad_px)
        usable_h = self.height_px - (2 * self.pad_px)
        px = self.pad_px + ((x - self.origin_x) / self.map_width_m) * usable_w
        py = self.height_px - self.pad_px - ((y - self.origin_y) / self.map_height_m) * usable_h
        return [px, py]


@dataclass(frozen=True)
class RerunScene:
    width_px: int
    height_px: int
    image_rgb: bytes
    path_points: list[list[float]]
    route_points: list[list[float]]
    target_points: list[list[float]]
    target_labels: list[str]
    poi_points: list[list[float]]
    poi_labels: list[str]
    robot_point: list[float] | None
    robot_heading: list[list[float]]


@dataclass(frozen=True)
class SimObstacle:
    kind: str
    label: str
    point: list[float]


@dataclass(frozen=True)
class SimFrame:
    sequence: int
    robot_point: list[float]
    robot_heading: list[list[float]]
    robot_path: list[list[float]]
    mapped_free_points: list[list[float]]
    mapped_occupied_points: list[list[float]]
    mapped_object_points: list[list[float]]
    mapped_object_labels: list[str]
    current_object_points: list[list[float]]
    current_object_labels: list[str]
    lidar_rays: list[list[list[float]]]
    lidar_hits: list[list[float]]


@dataclass(frozen=True)
class WorldOverlayScene:
    path_points: list[list[float]]
    route_points: list[list[float]]
    target_points: list[list[float]]
    target_labels: list[str]
    poi_points: list[list[float]]
    poi_labels: list[str]
    robot_point: list[float] | None
    robot_heading: list[list[float]]
    obstacles: list[SimObstacle]


def build_rerun_scene(state: Any) -> RerunScene:
    payload = state.model_dump(mode="json") if hasattr(state, "model_dump") else state
    site_map = payload.get("site_map") or {}
    route_plan = payload.get("route_plan") or {}
    projection = projection_from_site_map(site_map)
    image_rgb = costmap_rgb(site_map, projection)

    path = _dimos_path_points(site_map) or [
        [float(point.get("x") or 0.0), float(point.get("y") or 0.0)]
        for point in site_map.get("explored_path") or []
    ]
    path_points = [projection.pixel(x, y) for x, y in path]

    waypoints = route_plan.get("waypoints") or []
    route_points = [
        projection.pixel(
            float((waypoint.get("pose") or {}).get("x") or 0.0),
            float((waypoint.get("pose") or {}).get("y") or 0.0),
        )
        for waypoint in waypoints
    ]

    features = site_map.get("features") or []
    target_points: list[list[float]] = []
    target_labels: list[str] = []
    for feature in features:
        pose = feature.get("pose") or {}
        if pose.get("x") is None or pose.get("y") is None:
            continue
        target_points.append(projection.pixel(float(pose["x"]), float(pose["y"])))
        target_labels.append(str(feature.get("id") or feature.get("display_name") or "target"))

    pois = route_plan.get("points_of_interest") or []
    poi_points = []
    poi_labels = []
    for poi in pois:
        pose = poi.get("pose") or {}
        if pose.get("x") is None or pose.get("y") is None:
            continue
        poi_points.append(projection.pixel(float(pose["x"]), float(pose["y"])))
        poi_labels.append(f"{poi.get('id', 'POI')} {poi.get('target_id', '')}".strip())

    robot_point = None
    robot_heading: list[list[float]] = []
    robot_pose = site_map.get("robot_pose") or {}
    if robot_pose.get("x") is not None and robot_pose.get("y") is not None:
        robot_x = float(robot_pose["x"])
        robot_y = float(robot_pose["y"])
        robot_point = projection.pixel(robot_x, robot_y)
        theta = float(robot_pose.get("theta_deg") or 0.0)
        heading_x = robot_x + (0.35 * math.cos(math.radians(theta)))
        heading_y = robot_y + (0.35 * math.sin(math.radians(theta)))
        robot_heading = [robot_point, projection.pixel(heading_x, heading_y)]

    return RerunScene(
        width_px=projection.width_px,
        height_px=projection.height_px,
        image_rgb=image_rgb,
        path_points=path_points,
        route_points=route_points,
        target_points=target_points,
        target_labels=target_labels,
        poi_points=poi_points,
        poi_labels=poi_labels,
        robot_point=robot_point,
        robot_heading=robot_heading,
    )


def build_mapping_frames(
    state: Any,
    *,
    max_frames: int = 36,
    prefer_route: bool = True,
) -> list[SimFrame]:
    payload = state.model_dump(mode="json") if hasattr(state, "model_dump") else state
    site_map = payload.get("site_map") or {}
    route_plan = payload.get("route_plan") or {}
    projection = projection_from_site_map(site_map)
    path_world = _route_or_map_path(site_map, route_plan, prefer_route=prefer_route)
    if len(path_world) < 2:
        return []

    samples = _sample_path(path_world, max_frames=max_frames)
    known_cells = _known_cell_points(site_map, projection)
    obstacles = demo_obstacles(state)
    obstacle_points = [obstacle.point for obstacle in obstacles]
    obstacle_labels = [obstacle.label for obstacle in obstacles]
    frames: list[SimFrame] = []
    for index, robot_world in enumerate(samples):
        prefix_world = samples[: index + 1]
        prefix_px = [projection.pixel(point[0], point[1]) for point in prefix_world]
        robot_point = projection.pixel(robot_world[0], robot_world[1])
        mapped_free = _visible_points(prefix_px, known_cells["free"], radius_px=150.0)
        mapped_occupied = _visible_points(prefix_px, known_cells["occupied"], radius_px=150.0)
        mapped_object_indexes = _visible_point_indexes(
            prefix_px,
            obstacle_points,
            radius_px=150.0,
        )
        current_object_indexes = _visible_point_indexes(
            [robot_point],
            obstacle_points,
            radius_px=170.0,
        )
        mapped_object_points = [obstacle_points[item] for item in mapped_object_indexes]
        mapped_object_labels = [obstacle_labels[item] for item in mapped_object_indexes]
        current_object_points = [obstacle_points[item] for item in current_object_indexes]
        current_object_labels = [obstacle_labels[item] for item in current_object_indexes]
        lidar_hits = _visible_points([robot_point], known_cells["occupied"], radius_px=170.0)[:24]
        lidar_hits = current_object_points + lidar_hits
        if len(lidar_hits) < 8:
            lidar_hits.extend(
                _visible_points([robot_point], known_cells["free"], radius_px=150.0)[
                    : 16 - len(lidar_hits)
                ]
            )
        lidar_rays = [[robot_point, hit] for hit in lidar_hits[:18]]
        heading_world = _heading_target(samples, index)
        heading_px = projection.pixel(heading_world[0], heading_world[1])
        frames.append(
            SimFrame(
                sequence=index,
                robot_point=robot_point,
                robot_heading=[robot_point, heading_px],
                robot_path=prefix_px,
                mapped_free_points=mapped_free,
                mapped_occupied_points=mapped_occupied,
                mapped_object_points=mapped_object_points,
                mapped_object_labels=mapped_object_labels,
                current_object_points=current_object_points,
                current_object_labels=current_object_labels,
                lidar_rays=lidar_rays,
                lidar_hits=lidar_hits,
            )
        )
    return frames


def demo_obstacles(state: Any) -> list[SimObstacle]:
    payload = state.model_dump(mode="json") if hasattr(state, "model_dump") else state
    site_map = payload.get("site_map") or {}
    projection = projection_from_site_map(site_map)
    feature_by_id = {feature.get("id"): feature for feature in site_map.get("features") or []}
    if not feature_by_id:
        return []

    def point_near(target_id: str, dx: float = 0.0, dy: float = 0.0) -> list[float]:
        pose = (feature_by_id.get(target_id) or {}).get("pose") or {}
        return projection.pixel(float(pose.get("x") or 0.0) + dx, float(pose.get("y") or 0.0) + dy)

    obstacles: list[SimObstacle] = [
        SimObstacle("box", "PKG-101", point_near("INBOUND_DOCK", -0.25, 0.25)),
        SimObstacle("box", "PKG-102", point_near("INBOUND_DOCK", 0.20, -0.20)),
        SimObstacle("box", "PKG-104 blocks COOLING_1", point_near("COOLING_1", -0.18, -0.18)),
        SimObstacle("thermometer", "TEMP_1 sign 27.4 C", point_near("TEMP_1", 0.0, 0.0)),
    ]
    cone_offsets = [
        (-0.55, 0.25),
        (-0.30, -0.15),
        (0.0, 0.22),
        (0.28, -0.12),
        (0.55, 0.18),
    ]
    for index, offset in enumerate(cone_offsets):
        obstacles.append(
            SimObstacle("cone", f"CONE-{index + 1}", point_near("NO_GO_1", offset[0], offset[1]))
        )
    return obstacles


def build_world_overlay_scene(state: Any) -> WorldOverlayScene:
    payload = state.model_dump(mode="json") if hasattr(state, "model_dump") else state
    site_map = payload.get("site_map") or {}
    route_plan = payload.get("route_plan") or {}
    path_points = _world_path_points(site_map)
    route_points = _route_world_points(route_plan)

    target_points: list[list[float]] = []
    target_labels: list[str] = []
    for feature in site_map.get("features") or []:
        pose = feature.get("pose") or {}
        if pose.get("x") is None or pose.get("y") is None:
            continue
        target_points.append(_point3(float(pose["x"]), float(pose["y"]), 0.05))
        target_labels.append(str(feature.get("id") or feature.get("display_name") or "target"))

    poi_points: list[list[float]] = []
    poi_labels: list[str] = []
    for poi in route_plan.get("points_of_interest") or []:
        pose = poi.get("pose") or {}
        if pose.get("x") is None or pose.get("y") is None:
            continue
        poi_points.append(_point3(float(pose["x"]), float(pose["y"]), 0.12))
        poi_labels.append(f"{poi.get('id', 'POI')} {poi.get('target_id', '')}".strip())

    robot_point = None
    robot_heading: list[list[float]] = []
    robot_pose = site_map.get("robot_pose") or {}
    if robot_pose.get("x") is not None and robot_pose.get("y") is not None:
        robot_x = float(robot_pose["x"])
        robot_y = float(robot_pose["y"])
        theta = float(robot_pose.get("theta_deg") or 0.0)
        robot_point = _point3(robot_x, robot_y, 0.18)
        robot_heading = [
            robot_point,
            _point3(
                robot_x + (0.45 * math.cos(math.radians(theta))),
                robot_y + (0.45 * math.sin(math.radians(theta))),
                0.18,
            ),
        ]

    return WorldOverlayScene(
        path_points=path_points,
        route_points=route_points,
        target_points=target_points,
        target_labels=target_labels,
        poi_points=poi_points,
        poi_labels=poi_labels,
        robot_point=robot_point,
        robot_heading=robot_heading,
        obstacles=demo_obstacles_world(state),
    )


def demo_obstacles_world(state: Any) -> list[SimObstacle]:
    payload = state.model_dump(mode="json") if hasattr(state, "model_dump") else state
    site_map = payload.get("site_map") or {}
    feature_by_id = {feature.get("id"): feature for feature in site_map.get("features") or []}
    if not feature_by_id:
        return []

    def point_near(
        target_id: str,
        dx: float = 0.0,
        dy: float = 0.0,
        z: float = 0.10,
    ) -> list[float]:
        pose = (feature_by_id.get(target_id) or {}).get("pose") or {}
        return _point3(float(pose.get("x") or 0.0) + dx, float(pose.get("y") or 0.0) + dy, z)

    obstacles: list[SimObstacle] = [
        SimObstacle("box", "PKG-101", point_near("INBOUND_DOCK", -0.25, 0.25, 0.16)),
        SimObstacle("box", "PKG-102", point_near("INBOUND_DOCK", 0.20, -0.20, 0.16)),
        SimObstacle("box", "PKG-104 blocks COOLING_1", point_near("COOLING_1", -0.18, -0.18, 0.16)),
        SimObstacle("thermometer", "TEMP_1 sign 27.4 C", point_near("TEMP_1", 0.0, 0.0, 0.30)),
    ]
    cone_offsets = [
        (-0.55, 0.25),
        (-0.30, -0.15),
        (0.0, 0.22),
        (0.28, -0.12),
        (0.55, 0.18),
    ]
    for index, offset in enumerate(cone_offsets):
        obstacles.append(
            SimObstacle(
                "cone",
                f"CONE-{index + 1}",
                point_near("NO_GO_1", offset[0], offset[1], 0.18),
            )
        )
    return obstacles


def projection_from_site_map(site_map: dict[str, Any]) -> MapProjection:
    map_width_m = float(site_map.get("width_m") or 4.5)
    map_height_m = float(site_map.get("height_m") or 3.0)
    origin = site_map.get("origin") or {}
    origin_x = float(origin.get("x") or 0.0)
    origin_y = float(origin.get("y") or 0.0)
    resolution = float(site_map.get("resolution_m") or 0.5)
    grid_rows = _costmap_grid(site_map)
    dimos_costmap = site_map.get("dimos_costmap") or {}
    if grid_rows and isinstance(dimos_costmap, dict):
        origin_vector = (dimos_costmap.get("origin") or {}).get("c") or []
        if len(origin_vector) >= 2:
            origin_x = float(origin_vector[0])
            origin_y = float(origin_vector[1])
        resolution = float(dimos_costmap.get("resolution") or resolution)
        map_width_m = max(resolution, len(grid_rows[0]) * resolution)
        map_height_m = max(resolution, len(grid_rows) * resolution)
    return MapProjection(
        width_px=IMAGE_WIDTH_PX,
        height_px=IMAGE_HEIGHT_PX,
        pad_px=IMAGE_PAD_PX,
        origin_x=origin_x,
        origin_y=origin_y,
        map_width_m=max(map_width_m, resolution),
        map_height_m=max(map_height_m, resolution),
        resolution_m=resolution,
    )


def costmap_rgb(site_map: dict[str, Any], projection: MapProjection) -> bytes:
    image = bytearray([15, 23, 42] * projection.width_px * projection.height_px)
    grid_rows = _costmap_grid(site_map)
    if grid_rows:
        for y_index, row in enumerate(grid_rows):
            for x_index, value in enumerate(row):
                x = projection.origin_x + (x_index * projection.resolution_m)
                y = projection.origin_y + (y_index * projection.resolution_m)
                _fill_cell(image, projection, x, y, _cost_color(value))
    else:
        for cell in site_map.get("cells") or []:
            x = projection.origin_x + (int(cell["x_index"]) * projection.resolution_m)
            y = projection.origin_y + (int(cell["y_index"]) * projection.resolution_m)
            _fill_cell(image, projection, x, y, _cell_color(str(cell.get("state", "unknown"))))
    return bytes(image)


def publish_rerun_once(
    run_dir: str | Path,
    source_url: str = DEFAULT_RERUN_SOURCE_URL,
    *,
    view_mode: RerunViewMode = "dogops-2d",
) -> str:
    rr = _load_rerun()
    active_url = _start_rerun_stream(
        rr,
        source_url,
        require_existing=view_mode == "native-3d",
    )
    store = DogOpsStore.load_existing(run_dir)
    assert store.state is not None
    log_state_to_rerun(rr, store.state, view_mode=view_mode)
    return active_url


def serve_rerun_sim(
    run_dir: str | Path,
    *,
    source_url: str = DEFAULT_RERUN_SOURCE_URL,
    poll_interval_s: float = 0.5,
    server_memory_limit: str = "1GB",
    view_mode: RerunViewMode = "dogops-2d",
) -> None:
    rr = _load_rerun()
    active_url = _start_rerun_stream(
        rr,
        source_url,
        server_memory_limit=server_memory_limit,
        require_existing=view_mode == "native-3d",
    )
    if view_mode == "native-3d":
        print(f"DogOps Rerun overlays attached to native DimOS stream at {active_url}", flush=True)
    else:
        print(f"DogOps Rerun stream ready at {active_url}", flush=True)
    last_signature: tuple[tuple[str, int], ...] | None = None
    last_command_id: str | None = None
    run_path = Path(run_dir)
    while True:
        signature = _run_signature(run_path)
        if signature != last_signature:
            store = DogOpsStore.load_existing(run_path)
            assert store.state is not None
            command = _read_rerun_command(run_path)
            command_id = str(command.get("id") or "")
            action = str(command.get("action") or "")
            is_new_replay = bool(command_id and command_id != last_command_id)
            if is_new_replay and action in {"replay_mapping", "replay_route"}:
                log_state_to_rerun(
                    rr,
                    store.state,
                    animate_mapping=True,
                    include_camera=action == "replay_route",
                    prefer_route=action == "replay_route",
                    frame_delay_s=RERUN_MAPPING_REPLAY_DELAY_S,
                    view_mode=view_mode,
                )
                last_command_id = command_id
                print(f"DogOps Rerun stream replayed {action}", flush=True)
            else:
                log_state_to_rerun(rr, store.state, view_mode=view_mode)
                print("DogOps Rerun stream published map/route/POI state", flush=True)
            last_signature = signature
        time.sleep(poll_interval_s)


def log_state_to_rerun(
    rr: Any,
    state: Any,
    *,
    animate_mapping: bool = False,
    include_camera: bool = True,
    prefer_route: bool = True,
    frame_delay_s: float = 0.0,
    view_mode: RerunViewMode = "dogops-2d",
) -> RerunScene:
    scene = build_rerun_scene(state)
    if view_mode == "native-3d":
        _log_native_3d_overlays(rr, state)
        if include_camera:
            _log_poi_cameras(rr, state)
        else:
            rr.log("dogops/camera", rr.Clear(recursive=True))
        return scene

    _send_map_blueprint(rr)
    rr.log("dogops", rr.Clear(recursive=True))
    rr.log("dogops/map/costmap", rr.Clear(recursive=True))
    _log_line(rr, "dogops/map/explored_path", scene.path_points, [37, 99, 235, 220], "DimOS path")
    _log_line(rr, "dogops/map/route", scene.route_points, [20, 184, 166, 255], "RoutePlan")
    _log_demo_obstacles(rr, demo_obstacles(state))
    frames = build_mapping_frames(
        state,
        max_frames=RERUN_MAPPING_REPLAY_FRAMES if animate_mapping else 36,
        prefer_route=prefer_route,
    )
    if frames:
        if animate_mapping:
            _log_mapping_animation(rr, frames, delay_s=frame_delay_s)
        else:
            _log_mapping_frame(rr, frames[-1])
    else:
        rr.set_time("sim_step", sequence=0)
        _log_points(
            rr,
            "dogops/lidar/mapped_free",
            scene.path_points,
            ["mapped"] * len(scene.path_points),
            [37, 99, 235, 220],
            2.0,
            show_labels=False,
        )
    _log_points(
        rr,
        "dogops/map/targets",
        scene.target_points,
        scene.target_labels,
        [226, 232, 240, 255],
        4.5,
        show_labels=True,
    )
    _log_points(
        rr,
        "dogops/map/pois",
        scene.poi_points,
        scene.poi_labels,
        [245, 158, 11, 255],
        8.0,
        show_labels=True,
    )
    if scene.robot_point is None:
        rr.log("dogops/map/robot", rr.Clear(recursive=True))
    else:
        rr.log(
            "dogops/map/robot",
            rr.Points2D(
                [scene.robot_point],
                radii=[8.0],
                colors=[[248, 250, 252, 255]],
                labels=["Go2"],
                show_labels=True,
            ),
        )
    _log_line(rr, "dogops/map/robot_heading", scene.robot_heading, [248, 250, 252, 255], "heading")
    if include_camera:
        _log_poi_cameras(rr, state)
    else:
        rr.log("dogops/camera", rr.Clear(recursive=True))
    return scene


def _load_rerun() -> Any:
    try:
        import rerun as rr  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Rerun simulator requires rerun-sdk. Use the full DimOS environment or install "
            "the optional DogOps Rerun dependency before starting the local Rerun map."
        ) from exc
    return rr


def _start_rerun_stream(
    rr: Any,
    source_url: str,
    *,
    server_memory_limit: str = "1GB",
    require_existing: bool = False,
) -> str:
    host, port = _parse_local_rerun_source(source_url)
    rr.init("dogops_siteops_agent")
    if _port_open(host, port):
        rr.connect_grpc(url=source_url)
        return source_url
    if require_existing:
        raise RuntimeError(f"{NATIVE_3D_START_HINT}. Could not connect to {source_url}.")
    served = rr.serve_grpc(
        grpc_port=port,
        server_memory_limit=server_memory_limit,
        cors_allow_origin=["*"],
    )
    return served if isinstance(served, str) and served else source_url


def _send_map_blueprint(rr: Any) -> None:
    try:
        import rerun.blueprint as rrb  # type: ignore[import-not-found]

        rr.send_blueprint(
            rrb.Blueprint(
                rrb.Spatial2DView(
                    origin="/dogops",
                    contents=["/dogops/map/**", "/dogops/lidar/**", "/dogops/sim/**"],
                    name="DogOps live map",
                    background=[0, 0, 0, 255],
                ),
                collapse_panels=True,
                auto_layout=False,
                auto_views=False,
            )
        )
    except Exception:
        return


def _log_native_3d_overlays(rr: Any, state: Any) -> None:
    scene = build_world_overlay_scene(state)
    rr.log("world/dogops", rr.Clear(recursive=True))
    _log_line_3d(
        rr,
        "world/dogops/map/explored_path",
        scene.path_points,
        [37, 99, 235, 220],
        "DimOS path",
    )
    _log_line_3d(
        rr,
        "world/dogops/route/plan",
        scene.route_points,
        [20, 184, 166, 255],
        "RoutePlan",
    )
    _log_points_3d(
        rr,
        "world/dogops/map/targets",
        scene.target_points,
        scene.target_labels,
        [226, 232, 240, 255],
        0.06,
        show_labels=False,
    )
    _log_points_3d(
        rr,
        "world/dogops/route/pois",
        scene.poi_points,
        scene.poi_labels,
        [245, 158, 11, 255],
        0.10,
        show_labels=True,
    )
    _log_world_obstacles(rr, scene.obstacles)
    if scene.robot_point is None:
        rr.log("world/dogops/robot", rr.Clear(recursive=True))
    else:
        rr.log(
            "world/dogops/robot",
            rr.Points3D(
                [scene.robot_point],
                radii=[0.10],
                colors=[[248, 250, 252, 255]],
                labels=["Go2 Air"],
                show_labels=False,
            ),
        )
    _log_line_3d(
        rr,
        "world/dogops/robot/heading",
        scene.robot_heading,
        [248, 250, 252, 255],
        "heading",
    )


def _parse_local_rerun_source(source_url: str) -> tuple[str, int]:
    if not source_url.startswith("rerun+"):
        raise ValueError("Rerun source URL must start with rerun+")
    parsed = urlparse(source_url.removeprefix("rerun+"))
    host = parsed.hostname or "127.0.0.1"
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("DogOps Rerun simulator only serves local viewers by default")
    return host, int(parsed.port or 9877)


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def _costmap_grid(site_map: dict[str, Any]) -> list[list[int]]:
    dimos_costmap = site_map.get("dimos_costmap") or {}
    dimos_grid_payload = dimos_costmap.get("grid") if isinstance(dimos_costmap, dict) else None
    if isinstance(dimos_grid_payload, dict):
        return decode_dimos_costmap_full(dimos_grid_payload)
    return []


def _dimos_path_points(site_map: dict[str, Any]) -> list[list[float]]:
    dimos_path = site_map.get("dimos_path") or {}
    dimos_path_points = dimos_path.get("points") if isinstance(dimos_path, dict) else None
    if not isinstance(dimos_path_points, list):
        return []
    return [
        [float(point[0]), float(point[1])]
        for point in dimos_path_points
        if isinstance(point, (list, tuple)) and len(point) >= 2
    ]


def _world_path_points(site_map: dict[str, Any]) -> list[list[float]]:
    path = _dimos_path_points(site_map) or [
        [float(point.get("x") or 0.0), float(point.get("y") or 0.0)]
        for point in site_map.get("explored_path") or []
    ]
    return [_point3(point[0], point[1], 0.04) for point in path]


def _route_world_points(route_plan: dict[str, Any]) -> list[list[float]]:
    return [
        _point3(
            float((waypoint.get("pose") or {}).get("x") or 0.0),
            float((waypoint.get("pose") or {}).get("y") or 0.0),
            0.08,
        )
        for waypoint in route_plan.get("waypoints") or []
    ]


def _point3(x: float, y: float, z: float) -> list[float]:
    return [x, y, z]


def _route_or_map_path(
    site_map: dict[str, Any],
    route_plan: dict[str, Any],
    *,
    prefer_route: bool = True,
) -> list[list[float]]:
    route = [
        [
            float((waypoint.get("pose") or {}).get("x") or 0.0),
            float((waypoint.get("pose") or {}).get("y") or 0.0),
        ]
        for waypoint in route_plan.get("waypoints") or []
    ]
    if prefer_route and len(route) >= 2:
        return route
    path = _dimos_path_points(site_map)
    if len(path) >= 2:
        return path
    explored = [
        [float(point.get("x") or 0.0), float(point.get("y") or 0.0)]
        for point in site_map.get("explored_path") or []
    ]
    if len(explored) >= 2:
        return explored
    features = site_map.get("features") or []
    preferred = ["HOME", "INBOUND_DOCK", "COOLING_1", "TEMP_1", "QA_HOLD"]
    by_id = {feature.get("id"): feature for feature in features}
    return [
        [
            float(((by_id.get(target_id) or {}).get("pose") or {}).get("x") or 0.0),
            float(((by_id.get(target_id) or {}).get("pose") or {}).get("y") or 0.0),
        ]
        for target_id in preferred
        if target_id in by_id
    ]


def _sample_path(path: list[list[float]], *, max_frames: int) -> list[list[float]]:
    if len(path) < 2:
        return path
    distances = [
        math.dist(path[index], path[index + 1])
        for index in range(len(path) - 1)
    ]
    total = sum(distances) or 1.0
    samples: list[list[float]] = []
    for frame in range(max_frames):
        target_distance = (frame / max(1, max_frames - 1)) * total
        elapsed = 0.0
        for index, segment_distance in enumerate(distances):
            if target_distance <= elapsed + segment_distance or index == len(distances) - 1:
                ratio = (
                    0.0
                    if segment_distance == 0
                    else (target_distance - elapsed) / segment_distance
                )
                samples.append(
                    [
                        path[index][0] + ((path[index + 1][0] - path[index][0]) * ratio),
                        path[index][1] + ((path[index + 1][1] - path[index][1]) * ratio),
                    ]
                )
                break
            elapsed += segment_distance
    return samples


def _known_cell_points(
    site_map: dict[str, Any],
    projection: MapProjection,
) -> dict[str, list[list[float]]]:
    rows = _costmap_grid(site_map)
    free: list[list[float]] = []
    occupied: list[list[float]] = []
    if rows:
        for y_index, row in enumerate(rows):
            for x_index, value in enumerate(row):
                if value == -1:
                    continue
                x = projection.origin_x + ((x_index + 0.5) * projection.resolution_m)
                y = projection.origin_y + ((y_index + 0.5) * projection.resolution_m)
                bucket = free if value == 0 else occupied
                bucket.append(projection.pixel(x, y))
    else:
        for cell in site_map.get("cells") or []:
            state = str(cell.get("state", "unknown"))
            if state == "unknown":
                continue
            x = projection.origin_x + ((int(cell["x_index"]) + 0.5) * projection.resolution_m)
            y = projection.origin_y + ((int(cell["y_index"]) + 0.5) * projection.resolution_m)
            bucket = free if state == "free" else occupied
            bucket.append(projection.pixel(x, y))
    return {"free": free, "occupied": occupied}


def _visible_points(
    sample_points_px: list[list[float]],
    points_px: list[list[float]],
    *,
    radius_px: float,
) -> list[list[float]]:
    if not sample_points_px or not points_px:
        return []
    visible: list[list[float]] = []
    for point in points_px:
        if any(math.dist(point, sample) <= radius_px for sample in sample_points_px):
            visible.append(point)
    return visible


def _visible_point_indexes(
    sample_points_px: list[list[float]],
    points_px: list[list[float]],
    *,
    radius_px: float,
) -> list[int]:
    if not sample_points_px or not points_px:
        return []
    visible: list[int] = []
    for index, point in enumerate(points_px):
        if any(math.dist(point, sample) <= radius_px for sample in sample_points_px):
            visible.append(index)
    return visible


def _heading_target(samples: list[list[float]], index: int) -> list[float]:
    if index + 1 < len(samples):
        return samples[index + 1]
    if index > 0:
        current = samples[index]
        previous = samples[index - 1]
        return [current[0] + (current[0] - previous[0]), current[1] + (current[1] - previous[1])]
    return samples[index]


def _read_rerun_command(run_dir: Path) -> dict[str, Any]:
    path = run_dir / RERUN_COMMAND_FILENAME
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _fill_cell(
    image: bytearray,
    projection: MapProjection,
    x: float,
    y: float,
    color: tuple[int, int, int],
) -> None:
    top_left = projection.pixel(x, y + projection.resolution_m)
    bottom_right = projection.pixel(x + projection.resolution_m, y)
    x0 = max(0, min(projection.width_px, int(min(top_left[0], bottom_right[0]))))
    x1 = max(0, min(projection.width_px, int(max(top_left[0], bottom_right[0]) + 1)))
    y0 = max(0, min(projection.height_px, int(min(top_left[1], bottom_right[1]))))
    y1 = max(0, min(projection.height_px, int(max(top_left[1], bottom_right[1]) + 1)))
    for py in range(y0, y1):
        row_offset = py * projection.width_px * 3
        for px in range(x0, x1):
            offset = row_offset + (px * 3)
            image[offset : offset + 3] = bytes(color)


def _cost_color(value: int) -> tuple[int, int, int]:
    if value == -1:
        return (30, 41, 59)
    if value == 0:
        return (37, 99, 235)
    return (220, 38, 38)


def _cell_color(state: str) -> tuple[int, int, int]:
    return {
        "free": (37, 99, 235),
        "occupied": (220, 38, 38),
        "restricted": (245, 158, 11),
        "unknown": (30, 41, 59),
    }.get(state, (30, 41, 59))


def _log_line(
    rr: Any,
    path: str,
    points: list[list[float]],
    color: list[int],
    label: str,
    *,
    show_labels: bool = False,
) -> None:
    rr.log(path, rr.Clear(recursive=True))
    if len(points) < 2:
        return
    rr.log(
        path,
        rr.LineStrips2D(
            [points],
            radii=[3.0],
            colors=[color],
            labels=[label],
            show_labels=show_labels,
        ),
    )


def _log_points(
    rr: Any,
    path: str,
    points: list[list[float]],
    labels: list[str],
    color: list[int],
    radius: float,
    *,
    show_labels: bool = True,
) -> None:
    rr.log(path, rr.Clear(recursive=True))
    if not points:
        return
    rr.log(
        path,
        rr.Points2D(
            points,
            radii=[radius] * len(points),
            colors=[color] * len(points),
            labels=labels,
            show_labels=show_labels,
        ),
    )


def _log_line_3d(
    rr: Any,
    path: str,
    points: list[list[float]],
    color: list[int],
    label: str,
    *,
    show_labels: bool = False,
) -> None:
    rr.log(path, rr.Clear(recursive=True))
    if len(points) < 2:
        return
    rr.log(
        path,
        rr.LineStrips3D(
            [points],
            radii=[0.025],
            colors=[color],
            labels=[label],
            show_labels=show_labels,
        ),
    )


def _log_points_3d(
    rr: Any,
    path: str,
    points: list[list[float]],
    labels: list[str],
    color: list[int],
    radius: float,
    *,
    show_labels: bool = True,
) -> None:
    rr.log(path, rr.Clear(recursive=True))
    if not points:
        return
    rr.log(
        path,
        rr.Points3D(
            points,
            radii=[radius] * len(points),
            colors=[color] * len(points),
            labels=labels,
            show_labels=show_labels,
        ),
    )


def _log_mapping_frame(rr: Any, frame: SimFrame) -> None:
    _log_points(
        rr,
        "dogops/lidar/mapped_free",
        frame.mapped_free_points,
        ["free"] * len(frame.mapped_free_points),
        [59, 130, 246, 235],
        2.6,
        show_labels=False,
    )
    _log_points(
        rr,
        "dogops/lidar/mapped_occupied",
        frame.mapped_occupied_points,
        ["occupied"] * len(frame.mapped_occupied_points),
        [239, 68, 68, 255],
        4.4,
        show_labels=False,
    )
    _log_points(
        rr,
        "dogops/lidar/mapped_objects",
        frame.mapped_object_points,
        frame.mapped_object_labels,
        [245, 158, 11, 255],
        7.5,
        show_labels=True,
    )
    _log_points(
        rr,
        "dogops/lidar/current_hits",
        frame.lidar_hits,
        ["lidar"] * len(frame.lidar_hits),
        [45, 212, 191, 255],
        4.6,
        show_labels=False,
    )
    _log_points(
        rr,
        "dogops/lidar/current_object_hits",
        frame.current_object_points,
        frame.current_object_labels,
        [253, 224, 71, 255],
        9.5,
        show_labels=True,
    )
    rr.log("dogops/lidar/current_rays", rr.Clear(recursive=True))
    if frame.lidar_rays:
        rr.log(
            "dogops/lidar/current_rays",
            rr.LineStrips2D(
                frame.lidar_rays,
                radii=[1.0],
                colors=[[94, 234, 212, 120]],
                labels=["lidar scan"],
                show_labels=False,
            ),
        )
    _log_line(rr, "dogops/map/robot_path_live", frame.robot_path, [248, 250, 252, 210], "odom")
    rr.log(
        "dogops/map/robot",
        rr.Points2D(
            [frame.robot_point],
            radii=[8.0],
            colors=[[248, 250, 252, 255]],
            labels=["Go2 mapping"],
            show_labels=True,
        ),
    )
    _log_line(rr, "dogops/map/robot_heading", frame.robot_heading, [248, 250, 252, 255], "heading")


def _log_mapping_animation(rr: Any, frames: list[SimFrame], *, delay_s: float) -> None:
    for frame in frames:
        rr.set_time("sim_step", sequence=frame.sequence)
        _log_mapping_frame(rr, frame)
        if delay_s > 0:
            time.sleep(delay_s)


def _log_demo_obstacles(rr: Any, obstacles: list[SimObstacle]) -> None:
    colors = {
        "box": [180, 83, 9, 255],
        "cone": [249, 115, 22, 255],
        "thermometer": [244, 63, 94, 255],
    }
    rr.log("dogops/sim/objects", rr.Clear(recursive=True))
    if not obstacles:
        return
    rr.log(
        "dogops/sim/objects",
        rr.Points2D(
            [obstacle.point for obstacle in obstacles],
            radii=[9.0 if obstacle.kind != "cone" else 6.5 for obstacle in obstacles],
            colors=[colors.get(obstacle.kind, [226, 232, 240, 255]) for obstacle in obstacles],
            labels=[obstacle.label for obstacle in obstacles],
            show_labels=True,
        ),
    )


def _log_world_obstacles(rr: Any, obstacles: list[SimObstacle]) -> None:
    colors = {
        "box": [180, 83, 9, 255],
        "cone": [249, 115, 22, 255],
        "thermometer": [244, 63, 94, 255],
    }
    rr.log("world/dogops/sim/objects", rr.Clear(recursive=True))
    if not obstacles:
        return
    rr.log(
        "world/dogops/sim/objects",
        rr.Points3D(
            [obstacle.point for obstacle in obstacles],
            radii=[0.12 if obstacle.kind != "cone" else 0.08 for obstacle in obstacles],
            colors=[colors.get(obstacle.kind, [226, 232, 240, 255]) for obstacle in obstacles],
            labels=[obstacle.label for obstacle in obstacles],
            show_labels=True,
        ),
    )


def _log_poi_cameras(rr: Any, state: Any) -> None:
    payload = state.model_dump(mode="json") if hasattr(state, "model_dump") else state
    route_plan = payload.get("route_plan") or {}
    poi_by_id = {poi.get("id"): poi for poi in route_plan.get("points_of_interest") or []}
    captures = payload.get("poi_captures") or []
    rr.log("dogops/camera", rr.Clear(recursive=True))
    for index, capture in enumerate(captures):
        poi = poi_by_id.get(capture.get("poi_id")) or {}
        target_id = str(poi.get("target_id") or capture.get("poi_id") or f"poi_{index + 1}")
        image = _poi_camera_image(target_id)
        entity_path = f"dogops/camera/{_safe_entity_name(target_id)}"
        rr.set_time("sim_step", sequence=100 + index)
        rr.log(
            entity_path,
            rr.Image(bytes=image, width=320, height=180, color_model="RGB", datatype="U8"),
        )
        rr.log(
            f"{entity_path}/analysis",
            rr.TextDocument(
                str(capture.get("analysis") or capture.get("description") or target_id)
            ),
        )
        rr.log(
            "dogops/camera/front",
            rr.Image(bytes=image, width=320, height=180, color_model="RGB", datatype="U8"),
        )


def _poi_camera_image(target_id: str, width: int = 320, height: int = 180) -> bytes:
    image = bytearray([18, 24, 38] * width * height)
    _fill_rect_rgb(image, width, height, 0, height - 42, width, height, (55, 65, 81))
    _fill_rect_rgb(image, width, height, 0, 0, width, 26, (15, 23, 42))
    if target_id == "TEMP_1":
        _fill_rect_rgb(image, width, height, 48, 54, 272, 128, (226, 232, 240))
        _fill_rect_rgb(image, width, height, 68, 80, 252, 96, (248, 250, 252))
        _fill_rect_rgb(image, width, height, 68, 80, 206, 96, (34, 197, 94))
        _fill_rect_rgb(image, width, height, 208, 74, 216, 112, (239, 68, 68))
    elif target_id == "COOLING_1":
        _fill_rect_rgb(image, width, height, 46, 46, 140, 132, (148, 163, 184))
        for offset in range(0, 80, 14):
            _fill_rect_rgb(image, width, height, 54 + offset, 54, 60 + offset, 124, (30, 41, 59))
        _fill_rect_rgb(image, width, height, 170, 78, 254, 142, (180, 83, 9))
        _fill_rect_rgb(image, width, height, 178, 86, 246, 134, (217, 119, 6))
    else:
        _fill_rect_rgb(image, width, height, 72, 70, 144, 138, (180, 83, 9))
        _fill_rect_rgb(image, width, height, 178, 60, 236, 138, (249, 115, 22))
        _fill_rect_rgb(image, width, height, 198, 92, 216, 138, (254, 215, 170))
    return bytes(image)


def _fill_rect_rgb(
    image: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
) -> None:
    for y in range(max(0, y0), min(height, y1)):
        row = y * width * 3
        for x in range(max(0, x0), min(width, x1)):
            offset = row + (x * 3)
            image[offset : offset + 3] = bytes(color)


def _safe_entity_name(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "poi"


def _run_signature(run_dir: Path) -> tuple[tuple[str, int], ...]:
    rows: list[tuple[str, int]] = []
    for filename in (
        "state.json",
        "map.json",
        "route_plan.json",
        "report.json",
        RERUN_COMMAND_FILENAME,
    ):
        path = run_dir / filename
        rows.append((filename, path.stat().st_mtime_ns if path.exists() else 0))
    return tuple(rows)
