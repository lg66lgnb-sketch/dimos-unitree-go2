from __future__ import annotations

import base64
from html import escape
import math
from pathlib import Path
import time
from typing import Any
import zlib

from dimos.experimental.dogops.models import (
    Asset,
    EntityKind,
    MapCell,
    MapFeature,
    NavEvent,
    PointOfInterest,
    PointOfInterestCapture,
    Pose2D,
    RoutePlan,
    RouteWaypoint,
    SensorReading,
    SiteConfig,
    SiteEntity,
    SiteMap,
)


DEFAULT_MAP_RESOLUTION_M = 0.5
DIMOS_WEBSOCKET_VIS_MODULE = "dimos.web.websocket_vis.websocket_vis_module"
DIMOS_OPTIMIZED_COSTMAP = "dimos.web.websocket_vis.optimized_costmap.OptimizedCostmapEncoder"


def build_simulated_site_map(site: SiteConfig, nav_events: list[NavEvent]) -> SiteMap:
    features = _features_from_site(site)
    explored_path = _explored_path(site, nav_events)
    all_poses = [feature.pose for feature in features] + explored_path
    origin, width_m, height_m = _bounds_for_poses(all_poses)
    columns = max(1, math.ceil(width_m / DEFAULT_MAP_RESOLUTION_M))
    rows = max(1, math.ceil(height_m / DEFAULT_MAP_RESOLUTION_M))
    cells: list[MapCell] = []

    for y_index in range(rows):
        for x_index in range(columns):
            x = (origin.x or 0.0) + (x_index + 0.5) * DEFAULT_MAP_RESOLUTION_M
            y = (origin.y or 0.0) + (y_index + 0.5) * DEFAULT_MAP_RESOLUTION_M
            state, confidence = _cell_state(site, features, explored_path, x, y)
            cells.append(
                MapCell(
                    x_index=x_index,
                    y_index=y_index,
                    state=state,
                    confidence=confidence,
                )
            )

    observed_cells = [cell for cell in cells if cell.state != "unknown"]
    coverage_ratio = len(observed_cells) / len(cells) if cells else 0.0
    cell_stats = _cell_stats(cells)
    site_map = SiteMap(
        status="mapped",
        source="simulator",
        resolution_m=DEFAULT_MAP_RESOLUTION_M,
        width_m=columns * DEFAULT_MAP_RESOLUTION_M,
        height_m=rows * DEFAULT_MAP_RESOLUTION_M,
        origin=origin,
        cells=cells,
        explored_path=explored_path,
        features=features,
        coverage_ratio=coverage_ratio,
        cell_stats=cell_stats,
        robot_pose=explored_path[-1] if explored_path else None,
        notes=[
            "Simulated map feeds the same DimOS costmap/path contract used by live map/nav streams.",
            "Replace simulator source with live DimOS global_costmap/Path/Odometry when Go2 mapping is available.",
        ],
    )
    site_map.dimos_costmap = build_dimos_costmap_payload(site_map)
    site_map.dimos_path = build_dimos_path_payload(site_map.explored_path)
    return site_map


def build_dimos_costmap_payload(site_map: SiteMap) -> dict[str, Any]:
    """Build the same costmap payload shape emitted by DimOS WebsocketVisModule."""
    grid = _grid_from_site_map_cells(site_map)
    return {
        "type": "costmap",
        "grid": encode_dimos_costmap_full(grid),
        "origin": {
            "type": "vector",
            "c": [site_map.origin.x or 0.0, site_map.origin.y or 0.0, 0],
        },
        "resolution": site_map.resolution_m,
        "origin_theta": 0,
        "source_module": f"{DIMOS_WEBSOCKET_VIS_MODULE}.WebsocketVisModule._process_costmap",
        "encoder": DIMOS_OPTIMIZED_COSTMAP,
    }


def build_dimos_path_payload(points: list[Pose2D]) -> dict[str, Any]:
    return {
        "type": "path",
        "points": [
            [point.x or 0.0, point.y or 0.0] for point in points if point.x is not None and point.y is not None
        ],
        "source_module": f"{DIMOS_WEBSOCKET_VIS_MODULE}.WebsocketVisModule._on_path",
    }


def encode_dimos_costmap_full(grid: list[list[int]]) -> dict[str, Any]:
    """Stdlib equivalent of OptimizedCostmapEncoder's full zlib/base64 update."""
    height = len(grid)
    width = len(grid[0]) if grid else 0
    raw = bytes(_cost_value_to_u8(value) for row in grid for value in row)
    encoded = base64.b64encode(zlib.compress(raw, level=6)).decode("ascii")
    return {
        "update_type": "full",
        "shape": [height, width],
        "dtype": "u8",
        "compressed": True,
        "compression": "zlib",
        "data": encoded,
    }


def decode_dimos_costmap_full(payload: dict[str, Any]) -> list[list[int]]:
    if payload.get("update_type") != "full":
        raise ValueError("DogOps dashboard currently renders full DimOS costmap payloads only")
    shape = payload.get("shape") or [0, 0]
    height, width = int(shape[0]), int(shape[1])
    raw = zlib.decompress(base64.b64decode(str(payload.get("data", ""))))
    values = [_u8_to_cost_value(value) for value in raw]
    return [values[index : index + width] for index in range(0, height * width, width)]


def build_default_route_plan(site: SiteConfig) -> RoutePlan:
    targets = [
        ("HOME", "goto"),
        ("INBOUND_DOCK", "scan"),
        ("COOLING_1", "inspect"),
        ("TEMP_1", "photo"),
        ("QA_HOLD", "scan"),
        ("HOME", "goto"),
    ]
    waypoints = [
        _waypoint_for_target(site, target_id, order=index + 1, action=action)
        for index, (target_id, action) in enumerate(targets)
        if _entity_for_target(site, target_id) is not None
    ]
    waypoint_by_target = {waypoint.target_id: waypoint for waypoint in waypoints}
    pois: list[PointOfInterest] = []
    for target_id, reading_keys, prompt in [
        (
            "COOLING_1",
            ["COOLING_1.clearance_clear", "PKG-104.blocks_asset_id"],
            "Describe whether the cooling clearance is blocked.",
        ),
        (
            "TEMP_1",
            ["TEMP_1.temperature_celsius", "TEMP_1.max_celsius"],
            "Summarize the thermometer reading and threshold status.",
        ),
        ("QA_HOLD", ["PKG-104.zone_id"], "Confirm corrected package placement."),
    ]:
        waypoint = waypoint_by_target.get(target_id)
        entity = _entity_for_target(site, target_id)
        if waypoint is None or entity is None:
            continue
        pois.append(
            PointOfInterest(
                id=f"POI-{len(pois) + 1:03d}",
                waypoint_id=waypoint.id,
                target_id=target_id,
                display_name=entity.display_name,
                pose=waypoint.pose,
                reading_keys=reading_keys,
                analysis_prompt=prompt,
            )
        )
    return RoutePlan(
        id="operator_route",
        name="Open-space inspection route",
        source="default",
        waypoints=waypoints,
        points_of_interest=pois,
    )


def add_waypoint(plan: RoutePlan, site: SiteConfig, target_id: str) -> RoutePlan:
    waypoint = _waypoint_for_target(site, target_id, order=len(plan.waypoints) + 1)
    plan.waypoints.append(waypoint)
    plan.source = "operator"
    return plan


def add_point_of_interest(
    plan: RoutePlan,
    site: SiteConfig,
    target_id: str,
    *,
    waypoint_id: str | None = None,
    reading_keys: list[str] | None = None,
) -> RoutePlan:
    entity = _entity_for_target(site, target_id)
    if entity is None:
        raise KeyError(target_id)
    waypoint = _find_or_create_waypoint(plan, site, target_id, waypoint_id)
    plan.points_of_interest.append(
        PointOfInterest(
            id=f"POI-{len(plan.points_of_interest) + 1:03d}",
            waypoint_id=waypoint.id,
            target_id=target_id,
            display_name=entity.display_name,
            pose=waypoint.pose,
            reading_keys=reading_keys or _default_reading_keys(target_id),
            analysis_prompt=f"Summarize observations at {entity.display_name}.",
        )
    )
    plan.source = "operator"
    return plan


def simulate_poi_captures(
    *,
    run_id: str,
    plan: RoutePlan,
    evidence_dir: str | Path,
) -> tuple[list[PointOfInterestCapture], list[SensorReading]]:
    root = Path(evidence_dir)
    root.mkdir(parents=True, exist_ok=True)
    captures: list[PointOfInterestCapture] = []
    readings: list[SensorReading] = []
    for poi in plan.points_of_interest:
        capture_id = f"CAP-{len(captures) + 1:03d}"
        analysis, detected_entities, poi_readings = _deterministic_poi_analysis(poi, run_id)
        image_path = root / f"{capture_id.lower()}-{_safe_slug(poi.target_id)}.svg"
        _write_evidence_svg(image_path, poi, analysis, detected_entities)
        captures.append(
            PointOfInterestCapture(
                id=capture_id,
                run_id=run_id,
                poi_id=poi.id,
                ts=time.time(),
                image_path=str(image_path),
                description=f"Simulated photo at {poi.display_name}",
                analysis=analysis,
                detected_entities=detected_entities,
                source="simulation",
                vlm_provider="deterministic",
                needs_api_key=False,
            )
        )
        readings.extend(poi_readings)
    return captures, readings


def map_summary(site_map: SiteMap) -> dict[str, object]:
    return {
        "map_id": site_map.map_id,
        "status": site_map.status,
        "source": site_map.source,
        "dimos_schema": site_map.dimos_schema,
        "dimos_costmap": bool(site_map.dimos_costmap),
        "dimos_path": bool(site_map.dimos_path),
        "robot_pose": bool(site_map.robot_pose),
        "resolution_m": site_map.resolution_m,
        "width_m": site_map.width_m,
        "height_m": site_map.height_m,
        "coverage_ratio": site_map.coverage_ratio,
        "cell_stats": site_map.cell_stats,
        "features": len(site_map.features),
        "explored_path_points": len(site_map.explored_path),
    }


def _grid_from_site_map_cells(site_map: SiteMap) -> list[list[int]]:
    width = max((cell.x_index for cell in site_map.cells), default=-1) + 1
    height = max((cell.y_index for cell in site_map.cells), default=-1) + 1
    grid = [[-1 for _ in range(width)] for _ in range(height)]
    for cell in site_map.cells:
        grid[cell.y_index][cell.x_index] = _cell_state_to_cost(cell.state)
    return grid


def _cell_state_to_cost(state: str) -> int:
    if state == "free":
        return 0
    if state in {"occupied", "restricted"}:
        return 100
    return -1


def _cell_stats(cells: list[MapCell]) -> dict[str, int | float]:
    total = len(cells)
    unknown = len([cell for cell in cells if cell.state == "unknown"])
    free = len([cell for cell in cells if cell.state == "free"])
    occupied = len([cell for cell in cells if cell.state == "occupied"])
    restricted = len([cell for cell in cells if cell.state == "restricted"])
    known = total - unknown
    return {
        "total": total,
        "known": known,
        "unknown": unknown,
        "free": free,
        "occupied": occupied,
        "restricted": restricted,
        "coverage_ratio": (known / total) if total else 0.0,
    }


def _cost_value_to_u8(value: int) -> int:
    if value == -1:
        return 255
    return max(0, min(100, int(value)))


def _u8_to_cost_value(value: int) -> int:
    return -1 if value == 255 else int(value)


def _features_from_site(site: SiteConfig) -> list[MapFeature]:
    features: list[MapFeature] = []
    for zone in site.zones:
        if zone.pose_hint is None:
            continue
        features.append(
            MapFeature(
                id=zone.id,
                kind=zone.kind,
                display_name=zone.display_name,
                pose=zone.pose_hint,
                radius_m=zone.radius_m,
            )
        )
    for asset in site.assets:
        pose = _pose_for_asset(site, asset)
        if pose is None:
            continue
        features.append(
            MapFeature(
                id=asset.id,
                kind=asset.kind,
                display_name=asset.display_name,
                pose=pose,
                radius_m=0.35,
            )
        )
    return features


def _explored_path(site: SiteConfig, nav_events: list[NavEvent]) -> list[Pose2D]:
    path: list[Pose2D] = []
    for event in nav_events:
        if event.target_id is None:
            continue
        pose = _pose_for_target(site, event.target_id)
        if pose is not None:
            path.append(Pose2D(x=pose.x, y=pose.y, theta_deg=pose.theta_deg, source="nav_event"))
    if path:
        return path
    return [
        Pose2D(x=pose.x, y=pose.y, theta_deg=pose.theta_deg, source="site_pose")
        for pose in (_pose_for_target(site, target) for target in ["HOME", "INBOUND_DOCK", "COOLING_1", "QA_HOLD"])
        if pose is not None
    ]


def _bounds_for_poses(poses: list[Pose2D]) -> tuple[Pose2D, float, float]:
    xs = [pose.x for pose in poses if pose.x is not None]
    ys = [pose.y for pose in poses if pose.y is not None]
    min_x = min(xs, default=0.0) - 1.0
    max_x = max(xs, default=4.0) + 1.0
    min_y = min(ys, default=-2.0) - 1.0
    max_y = max(ys, default=1.0) + 1.0
    return (
        Pose2D(x=min_x, y=min_y, theta_deg=0.0, frame="world", source="simulated_bounds"),
        max_x - min_x,
        max_y - min_y,
    )


def _cell_state(
    site: SiteConfig,
    features: list[MapFeature],
    explored_path: list[Pose2D],
    x: float,
    y: float,
) -> tuple[str, float]:
    no_go_ids = {zone.id for zone in site.zones if zone.no_go}
    for feature in features:
        if feature.id in no_go_ids and _distance_xy(feature.pose, x, y) <= feature.radius_m:
            return "restricted", 0.95
    for feature in features:
        if feature.kind == EntityKind.asset and _distance_xy(feature.pose, x, y) <= 0.2:
            return "occupied", 0.8
    if any(_distance_xy(pose, x, y) <= 0.75 for pose in explored_path):
        return "free", 0.9
    if any(_distance_xy(feature.pose, x, y) <= feature.radius_m for feature in features):
        return "free", 0.7
    return "unknown", 0.0


def _distance_xy(pose: Pose2D, x: float, y: float) -> float:
    if pose.x is None or pose.y is None:
        return float("inf")
    return math.hypot(pose.x - x, pose.y - y)


def _waypoint_for_target(
    site: SiteConfig,
    target_id: str,
    *,
    order: int,
    action: str = "goto",
) -> RouteWaypoint:
    entity = _entity_for_target(site, target_id)
    pose = _pose_for_target(site, target_id)
    if entity is None or pose is None:
        raise KeyError(target_id)
    return RouteWaypoint(
        id=f"WP-{order:03d}",
        target_id=target_id,
        display_name=entity.display_name,
        pose=pose,
        order=order,
        action=action if action in {"goto", "scan", "inspect", "photo"} else "goto",
    )


def _find_or_create_waypoint(
    plan: RoutePlan,
    site: SiteConfig,
    target_id: str,
    waypoint_id: str | None,
) -> RouteWaypoint:
    for waypoint in plan.waypoints:
        if waypoint_id is not None and waypoint.id == waypoint_id:
            return waypoint
        if waypoint_id is None and waypoint.target_id == target_id:
            return waypoint
    waypoint = _waypoint_for_target(site, target_id, order=len(plan.waypoints) + 1)
    plan.waypoints.append(waypoint)
    return waypoint


def _pose_for_target(site: SiteConfig, target_id: str) -> Pose2D | None:
    zone = site.zone_by_id().get(target_id)
    if zone is not None:
        return zone.pose_hint
    asset = site.asset_by_id().get(target_id)
    if asset is not None:
        return _pose_for_asset(site, asset)
    package = site.package_by_id().get(target_id)
    if package is not None:
        zone = site.zone_by_id().get(package.expected_zone_id)
        return zone.pose_hint if zone else None
    for entity in site.special_entities.values():
        if entity.id == target_id and entity.zone_id:
            zone = site.zone_by_id().get(entity.zone_id)
            return zone.pose_hint if zone else None
    return None


def _pose_for_asset(site: SiteConfig, asset: Asset) -> Pose2D | None:
    if asset.zone_id is None:
        return None
    zone = site.zone_by_id().get(asset.zone_id)
    if zone is None or zone.pose_hint is None:
        return None
    offset = 0.0
    if asset.id == "TEMP_1":
        offset = 0.55
    elif asset.id == "AISLE_1":
        offset = -0.55
    return Pose2D(
        x=(zone.pose_hint.x or 0.0) + offset,
        y=zone.pose_hint.y,
        theta_deg=zone.pose_hint.theta_deg,
        frame=zone.pose_hint.frame,
        source=f"asset_zone:{zone.id}",
    )


def _entity_for_target(site: SiteConfig, target_id: str) -> SiteEntity | None:
    return (
        site.zone_by_id().get(target_id)
        or site.asset_by_id().get(target_id)
        or site.package_by_id().get(target_id)
        or next((entity for entity in site.special_entities.values() if entity.id == target_id), None)
    )


def _default_reading_keys(target_id: str) -> list[str]:
    if target_id == "TEMP_1":
        return ["TEMP_1.temperature_celsius", "TEMP_1.max_celsius"]
    if target_id == "COOLING_1":
        return ["COOLING_1.clearance_clear", "PKG-104.blocks_asset_id"]
    return [f"{target_id}.status"]


def _deterministic_poi_analysis(
    poi: PointOfInterest, run_id: str
) -> tuple[str, list[str], list[SensorReading]]:
    readings: list[SensorReading] = []
    detected_entities = [poi.target_id]
    if poi.target_id == "COOLING_1":
        detected_entities.append("PKG-104")
        readings.append(
            SensorReading(
                id=f"READ-{poi.id}-001",
                run_id=run_id,
                poi_id=poi.id,
                name="cooling_clearance",
                value="clear_after_verification",
                status="normal",
                source="deterministic_photo_analysis",
                notes="PKG-104 was photographed blocking the station before remediation and absent after verification.",
            )
        )
        return (
            "COOLING_1 photo set shows the earlier blocked clearance and the verified clear state after PKG-104 moved to QA_HOLD.",
            detected_entities,
            readings,
        )
    if poi.target_id == "TEMP_1":
        temperature_c = 27.4
        max_c = 30.0
        readings.extend(
            [
                SensorReading(
                    id=f"READ-{poi.id}-001",
                    run_id=run_id,
                    poi_id=poi.id,
                    name="temperature",
                    value=temperature_c,
                    unit="C",
                    status="normal",
                    source="simulated_manual_thermometer",
                    notes="Demo uses manual/simulated thermometer input; no thermal camera claim.",
                ),
                SensorReading(
                    id=f"READ-{poi.id}-002",
                    run_id=run_id,
                    poi_id=poi.id,
                    name="temperature_threshold",
                    value=max_c,
                    unit="C",
                    status="normal",
                    source="site_policy",
                    notes="Configured upper threshold for TEMP_1.",
                ),
            ]
        )
        return (
            f"TEMP_1 thermometer reading is {temperature_c:.1f} C, below the {max_c:.1f} C threshold.",
            detected_entities,
            readings,
        )
    if poi.target_id == "QA_HOLD":
        detected_entities.append("PKG-104")
        readings.append(
            SensorReading(
                id=f"READ-{poi.id}-001",
                run_id=run_id,
                poi_id=poi.id,
                name="pkg_104_zone",
                value="QA_HOLD",
                status="normal",
                source="deterministic_tag_analysis",
                notes="PKG-104 is in its corrected destination after the human fix.",
            )
        )
        return (
            "QA_HOLD image confirms PKG-104 is at the corrected hold location.",
            detected_entities,
            readings,
        )
    return (
        f"{poi.display_name} captured; deterministic analysis found no configured exception.",
        detected_entities,
        readings,
    )


def _write_evidence_svg(
    path: Path,
    poi: PointOfInterest,
    analysis: str,
    detected_entities: list[str],
) -> None:
    entity_text = ", ".join(detected_entities)
    path.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="720" height="420" viewBox="0 0 720 420">
  <rect width="720" height="420" fill="#101820"/>
  <rect x="34" y="34" width="652" height="352" rx="10" fill="#f8fafc"/>
  <text x="64" y="88" fill="#17202a" font-family="Arial, sans-serif" font-size="30" font-weight="700">{escape(poi.display_name)}</text>
  <text x="64" y="128" fill="#475569" font-family="Arial, sans-serif" font-size="18">Simulated Go2 point-of-interest capture</text>
  <rect x="64" y="162" width="242" height="144" fill="#dbeafe" stroke="#2563eb" stroke-width="3"/>
  <rect x="340" y="162" width="270" height="144" fill="#dcfce7" stroke="#0f766e" stroke-width="3"/>
  <text x="84" y="238" fill="#1d4ed8" font-family="Arial, sans-serif" font-size="24">PHOTO</text>
  <text x="364" y="222" fill="#0f766e" font-family="Arial, sans-serif" font-size="20">Detected:</text>
  <text x="364" y="254" fill="#0f766e" font-family="Arial, sans-serif" font-size="18">{escape(entity_text)}</text>
  <text x="64" y="346" fill="#17202a" font-family="Arial, sans-serif" font-size="18">{escape(_truncate(analysis, 92))}</text>
</svg>
""",
        encoding="utf-8",
    )


def _safe_slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


def _truncate(value: str, max_len: int) -> str:
    return value if len(value) <= max_len else value[: max_len - 3] + "..."
