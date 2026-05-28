from __future__ import annotations

from html import escape
from itertools import pairwise
import json
import math
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dimos.experimental.dogops.map_authoring import load_map_authoring

MAP_WIDTH = 920
MAP_HEIGHT = 560
MAP_PADDING_M = 0.55
MAP_CELL_M = 0.18
ENTITY_OFFSETS_M = (
    (0.0, 0.0),
    (0.24, 0.22),
    (0.28, -0.22),
    (-0.26, 0.20),
    (-0.30, -0.18),
    (0.48, 0.0),
    (0.0, -0.46),
)
PACKAGE_OFFSETS_M = (
    (-0.22, -0.18),
    (0.0, -0.22),
    (0.22, -0.18),
    (-0.14, 0.18),
    (0.14, 0.18),
)


def build_map_data(
    state: dict[str, Any],
    report: dict[str, Any],
    *,
    live_overlay: dict[str, Any] | None = None,
    authoring: dict[str, Any] | None = None,
) -> dict[str, Any]:
    site = state.get("site") or {}
    authoring = authoring or {}
    authored_entities = _authoring_entities(authoring)
    authored_incidents = _authoring_incidents(authoring)
    zones = site.get("zones") or []
    assets = site.get("assets") or []
    site_packages = site.get("packages") or []
    observations = state.get("observations") or []
    nav_events = state.get("nav_events") or []
    incidents = report.get("incidents") or []
    report_packages = report.get("packages") or []

    zone_points: dict[str, tuple[float, float]] = {}
    map_zones: list[dict[str, Any]] = []
    for zone in zones:
        pose = _zone_pose(zone)
        zone_id = str(zone["id"])
        authored = authored_entities.get(zone_id)
        if authored is not None:
            pose = _authoring_pose(authored)
        elif zone_id == "HOME" and authoring.get("home"):
            pose = _authoring_pose({"pose": authoring["home"]})
        if pose is None:
            continue
        zone_points[zone_id] = pose
        map_zones.append(
            {
                "id": zone_id,
                "display_name": _authoring_label(authoring, zone_id, zone.get("display_name") or zone_id),
                "zone_kind": zone.get("zone_kind", "zone"),
                "tag_id": _authoring_tag_id(authoring, zone_id, zone.get("tag_id")),
                "radius_m": float(zone.get("radius_m") or 0.8),
                "no_go": bool(zone.get("no_go")),
                "x": pose[0],
                "y": pose[1],
                "source": "dashboard_edit" if authored is not None or (zone_id == "HOME" and authoring.get("home")) else "site_config",
            }
        )

    entity_points = dict(zone_points)
    map_assets: list[dict[str, Any]] = []
    for index, asset in enumerate(assets):
        zone_id = str(asset.get("zone_id") or "")
        base = zone_points.get(zone_id)
        asset_id = str(asset["id"])
        authored = authored_entities.get(asset_id)
        authored_pose = _authoring_pose(authored) if authored is not None else None
        if base is None and authored_pose is None:
            continue
        pose = authored_pose or _offset_pose(base, index + 1)  # type: ignore[arg-type]
        entity_points[asset_id] = pose
        map_assets.append(
            {
                "id": asset_id,
                "display_name": _authoring_label(authoring, asset_id, asset.get("display_name") or asset_id),
                "asset_kind": asset.get("asset_kind", "asset"),
                "tag_id": _authoring_tag_id(authoring, asset_id, asset.get("tag_id")),
                "zone_id": str((authored or {}).get("zone_id") or zone_id),
                "x": pose[0],
                "y": pose[1],
                "source": "dashboard_edit" if authored_pose is not None else "site_config",
            }
        )

    site_package_by_id = {str(package["id"]): package for package in site_packages}
    package_counts_by_zone: dict[str, int] = {}
    map_packages: list[dict[str, Any]] = []
    for package in report_packages:
        package_id = str(package["package_id"])
        authored = authored_entities.get(package_id)
        observed_zone = package.get("observed_zone_id")
        expected_zone = package.get("expected_zone_id")
        zone_id = str(observed_zone or expected_zone or "")
        base = zone_points.get(zone_id)
        authored_pose = _authoring_pose(authored) if authored is not None else None
        if base is None and authored_pose is None:
            continue
        count = package_counts_by_zone.get(zone_id, 0)
        package_counts_by_zone[zone_id] = count + 1
        pose = authored_pose or _package_pose(base, count)  # type: ignore[arg-type]
        site_package = site_package_by_id.get(package_id) or {}
        entity_points[package_id] = pose
        map_packages.append(
            {
                "id": package_id,
                "display_name": _authoring_label(authoring, package_id, site_package.get("display_name") or package_id),
                "tag_id": _authoring_tag_id(authoring, package_id, site_package.get("tag_id")),
                "expected_zone_id": expected_zone,
                "observed_zone_id": observed_zone,
                "state": package.get("state", "unknown"),
                "blocks_asset_id": package.get("blocks_asset_id"),
                "x": pose[0],
                "y": pose[1],
                "source": "dashboard_edit" if authored_pose is not None else "site_config",
            }
        )

    for entity in (authoring.get("entities") or []):
        if not isinstance(entity, dict):
            continue
        entity_id = str(entity.get("id") or "")
        if not entity_id or entity_id in entity_points:
            continue
        pose = _authoring_pose(entity)
        if pose is None:
            continue
        kind = str(entity.get("kind") or "checkpoint")
        entity_points[entity_id] = pose
        if kind in {"zone", "checkpoint"}:
            zone_points[entity_id] = pose
            map_zones.append(
                {
                    "id": entity_id,
                    "display_name": entity.get("label") or entity_id,
                    "zone_kind": kind,
                    "tag_id": entity.get("tag_id"),
                    "radius_m": 0.45,
                    "no_go": False,
                    "x": pose[0],
                    "y": pose[1],
                    "source": "dashboard_edit",
                }
            )
        elif kind == "asset":
            map_assets.append(
                {
                    "id": entity_id,
                    "display_name": entity.get("label") or entity_id,
                    "asset_kind": "authored",
                    "tag_id": entity.get("tag_id"),
                    "zone_id": entity.get("zone_id"),
                    "x": pose[0],
                    "y": pose[1],
                    "source": "dashboard_edit",
                }
            )
        elif kind == "package":
            map_packages.append(
                {
                    "id": entity_id,
                    "display_name": entity.get("label") or entity_id,
                    "tag_id": entity.get("tag_id"),
                    "expected_zone_id": entity.get("zone_id"),
                    "observed_zone_id": entity.get("zone_id"),
                    "state": "authored",
                    "blocks_asset_id": None,
                    "x": pose[0],
                    "y": pose[1],
                    "source": "dashboard_edit",
                }
            )

    map_route: list[dict[str, Any]] = []
    authored_route = _selected_authoring_route(authoring)
    if authored_route is not None:
        for waypoint in authored_route.get("waypoints") or []:
            if not isinstance(waypoint, dict):
                continue
            pose = _authoring_pose(waypoint)
            if pose is None:
                continue
            target_id = str(waypoint.get("target_id") or waypoint.get("id") or "waypoint")
            map_route.append(
                {
                    "target_id": target_id,
                    "x": pose[0],
                    "y": pose[1],
                    "success": True,
                    "guided": False,
                    "retries": 0,
                    "note": "authored route",
                    "source": "dashboard_edit",
                }
            )
    else:
        for event in nav_events:
            if event.get("action") != "goto":
                continue
            target_id = str(event.get("target_id") or "")
            pose = entity_points.get(target_id)
            if pose is None:
                continue
            map_route.append(
                {
                    "target_id": target_id,
                    "x": pose[0],
                    "y": pose[1],
                    "success": bool(event.get("success", True)),
                    "guided": bool(event.get("guided", False)),
                    "retries": int(event.get("retries") or 0),
                    "note": event.get("note", ""),
                    "source": "nav_event",
                }
            )

    map_observations: list[dict[str, Any]] = []
    for observation in observations:
        zone_id = str(observation.get("zone_id") or "")
        base = zone_points.get(zone_id)
        if base is None:
            continue
        pose = _offset_pose(base, len(map_observations) + 1)
        map_observations.append(
            {
                "id": observation.get("id"),
                "zone_id": zone_id,
                "entity_id": observation.get("entity_id"),
                "tag_id": observation.get("tag_id"),
                "visible_tag_ids": _visible_tag_ids(observation),
                "source": observation.get("source", "unknown"),
                "x": pose[0],
                "y": pose[1],
            }
        )

    map_incidents: list[dict[str, Any]] = []
    for incident in incidents:
        entity_id = str(incident.get("entity_id") or "")
        location = authored_incidents.get(str(incident.get("id") or ""))
        pose = _authoring_pose(location) if location is not None else entity_points.get(entity_id)
        if pose is None and incident.get("related_package_id"):
            pose = entity_points.get(str(incident["related_package_id"]))
        if pose is None:
            continue
        map_incidents.append(
            {
                "id": incident.get("id"),
                "entity_id": entity_id,
                "related_package_id": incident.get("related_package_id"),
                "severity": incident.get("severity", "INFO"),
                "state": incident.get("state", "unknown"),
                "x": pose[0],
                "y": pose[1],
                "source": "dashboard_edit" if location is not None else "run_state",
            }
        )

    live = live_overlay or {
        "ok": False,
        "source": "DimOS live LCM topics",
        "status": "not_requested",
        "error": "",
        "topics": {},
        "costmap": None,
        "path": [],
        "route": [],
        "robot_pose": None,
        "target": None,
    }
    points = [
        (item["x"], item["y"])
        for group in (map_zones, map_assets, map_packages, map_route, map_observations)
        for item in group
    ]
    points.extend(_no_go_shape_points(authoring))
    points.extend(_live_overlay_points(live))
    bounds = _map_bounds(points)
    return {
        "site_id": site.get("site_id"),
        "site_name": site.get("site_name"),
        "zones": map_zones,
        "assets": map_assets,
        "packages": map_packages,
        "route": map_route,
        "observations": map_observations,
        "incidents": map_incidents,
        "no_go_shapes": authoring.get("no_go_shapes") or [],
        "tag_bindings": authoring.get("tag_bindings") or [],
        "authoring": {
            "schema_version": authoring.get("schema_version", 1),
            "updated_at": authoring.get("updated_at"),
            "selected_route_id": authoring.get("selected_route_id"),
            "entities": len(authoring.get("entities") or []),
            "no_go_shapes": len(authoring.get("no_go_shapes") or []),
            "routes": len(authoring.get("routes") or []),
            "tag_bindings": len(authoring.get("tag_bindings") or []),
        },
        "bounds": bounds,
        "live": live,
        "layers": {
            "semantic": True,
            "heatmap": bool((live.get("costmap") or {}).get("cells")) if isinstance(live, dict) else False,
            "path": bool(live.get("path") or live.get("route")) if isinstance(live, dict) else False,
            "robot": bool(live.get("robot_pose")) if isinstance(live, dict) else False,
        },
    }


def _live_overlay_points(live: dict[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for point in [*(live.get("path") or []), *(live.get("route") or [])]:
        maybe_point = _xy_point(point)
        if maybe_point is not None:
            points.append(maybe_point)
    for point in (live.get("robot_pose"), live.get("target")):
        maybe_point = _xy_point(point)
        if maybe_point is not None:
            points.append(maybe_point)
    costmap = live.get("costmap") or {}
    cells = costmap.get("cells") if isinstance(costmap, dict) else None
    if isinstance(cells, list):
        for cell in cells:
            maybe_point = _xy_point(cell)
            if maybe_point is None:
                continue
            x, y = maybe_point
            width = _float_or_none(cell.get("width") if isinstance(cell, dict) else None) or 0.0
            height = _float_or_none(cell.get("height") if isinstance(cell, dict) else None) or 0.0
            points.append((x, y))
            points.append((x + width, y + height))
    return points


def _authoring_entities(authoring: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entity.get("id")): entity
        for entity in authoring.get("entities") or []
        if isinstance(entity, dict) and entity.get("id")
    }


def _authoring_incidents(authoring: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(location.get("incident_id")): location
        for location in authoring.get("incident_locations") or []
        if isinstance(location, dict) and location.get("incident_id")
    }


def _authoring_pose(item: dict[str, Any] | None) -> tuple[float, float] | None:
    if not isinstance(item, dict):
        return None
    pose = item.get("pose") if isinstance(item.get("pose"), dict) else item
    if not isinstance(pose, dict):
        return None
    x = _float_or_none(pose.get("x"))
    y = _float_or_none(pose.get("y"))
    if x is None or y is None:
        return None
    return x, y


def _authoring_label(authoring: dict[str, Any], entity_id: str, fallback: object) -> str:
    entity = _authoring_entities(authoring).get(entity_id)
    if entity is None:
        return str(fallback)
    return str(entity.get("label") or fallback)


def _authoring_tag_id(
    authoring: dict[str, Any],
    entity_id: str,
    fallback: object | None,
) -> object | None:
    entity = _authoring_entities(authoring).get(entity_id)
    if entity is not None and entity.get("tag_id") is not None:
        return entity.get("tag_id")
    for binding in authoring.get("tag_bindings") or []:
        if isinstance(binding, dict) and binding.get("entity_id") == entity_id:
            return binding.get("tag_id")
    return fallback


def _selected_authoring_route(authoring: dict[str, Any]) -> dict[str, Any] | None:
    routes = [route for route in authoring.get("routes") or [] if isinstance(route, dict)]
    if not routes:
        return None
    selected_route_id = authoring.get("selected_route_id")
    if selected_route_id:
        for route in routes:
            if route.get("id") == selected_route_id and route.get("waypoints"):
                return route
    routes_with_points = [route for route in routes if route.get("waypoints")]
    return routes_with_points[0] if routes_with_points else None


def _no_go_shape_points(authoring: dict[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for shape in authoring.get("no_go_shapes") or []:
        if not isinstance(shape, dict) or not shape.get("enabled", True):
            continue
        for point in shape.get("points") or []:
            maybe_point = _authoring_pose(point)
            if maybe_point is not None:
                points.append(maybe_point)
    return points


def _xy_point(item: Any) -> tuple[float, float] | None:
    if not isinstance(item, dict):
        return None
    x = _float_or_none(item.get("x"))
    y = _float_or_none(item.get("y"))
    if x is None or y is None:
        return None
    return x, y


def _float_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def build_route_data(
    state: dict[str, Any],
    report: dict[str, Any],
    *,
    authoring: dict[str, Any] | None = None,
) -> dict[str, Any]:
    map_data = build_map_data(state, report, authoring=authoring)
    checkpoints = {
        str(checkpoint.get("target_id")): checkpoint
        for checkpoint in report.get("checkpoint_verifications") or []
    }
    nav_events = [event for event in state.get("nav_events") or [] if event.get("action") == "goto"]
    nav_by_target = {str(event.get("target_id")): event for event in nav_events}
    stops = []
    for index, stop in enumerate(map_data["route"], 1):
        target_id = str(stop["target_id"])
        event = nav_by_target.get(target_id) or {}
        checkpoint = checkpoints.get(target_id) or {}
        stops.append(
            {
                "sequence": index,
                "target_id": target_id,
                "x": stop["x"],
                "y": stop["y"],
                "success": bool(stop.get("success", True)),
                "guided": bool(stop.get("guided", False)),
                "retries": int(stop.get("retries") or 0),
                "elapsed_s": float(event.get("elapsed_s") or 0.0),
                "note": stop.get("note", ""),
                "expected_tag_id": checkpoint.get("expected_tag_id"),
                "verification_observation_id": checkpoint.get("observation_id"),
                "tag_verified": bool(checkpoint.get("verified", False)),
            }
        )
    nav = report.get("nav_summary") or {}
    return {
        "run_id": report.get("run_id"),
        "mission_id": report.get("mission_id"),
        "route_targets": nav.get("route_targets", len(stops)),
        "route_coverage": nav.get("route_coverage", 0.0),
        "waypoints_reached": nav.get("waypoints_reached", 0),
        "waypoints_total": nav.get("waypoints_total", len(stops)),
        "tag_reacquisition_attempts": nav.get("tag_reacquisition_attempts", 0),
        "tag_reacquisition_successes": nav.get("tag_reacquisition_successes", 0),
        "stops": stops,
    }


def build_poi_data(state: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    observations = state.get("observations") or []
    incidents = report.get("incidents") or []
    captures = []
    for observation in observations:
        observation_id = str(observation.get("id") or "")
        related_incident_ids = [
            str(incident.get("id"))
            for incident in incidents
            if observation_id in (incident.get("evidence_observation_ids") or [])
        ]
        captures.append(
            {
                "id": observation_id,
                "zone_id": observation.get("zone_id"),
                "entity_id": observation.get("entity_id"),
                "tag_id": observation.get("tag_id"),
                "visible_tag_ids": _visible_tag_ids(observation),
                "source": observation.get("source", "unknown"),
                "image_path": observation.get("image_path"),
                "related_incident_ids": related_incident_ids,
            }
        )

    readings = []
    for asset in (state.get("site") or {}).get("assets") or []:
        asset_id = str(asset.get("id") or "")
        expected_state = asset.get("expected_state") or {}
        if asset.get("expected_clear") is not None:
            raw_clear = _latest_fact_value(observations, f"{asset_id}.clearance_clear")
            clearance_clear = _to_bool(raw_clear)
            if clearance_clear is None:
                clearance_clear = bool(asset.get("expected_clear"))
            readings.append(
                {
                    "asset_id": asset_id,
                    "kind": "clearance",
                    "state": "clear" if clearance_clear else "blocked",
                    "clearance_clear": clearance_clear,
                    "expected_clear": asset.get("expected_clear"),
                }
            )
        threshold = _to_float(expected_state.get("max_celsius"))
        if threshold is not None:
            reading = _to_float(_latest_fact_value(observations, f"{asset_id}.temperature_c"))
            source = "observation"
            if reading is None:
                reading = _to_float(expected_state.get("current_celsius"))
                source = "expected_state"
            if reading is None:
                reading = round(threshold - 2.0, 1)
                source = "deterministic_fallback"
            readings.append(
                {
                    "asset_id": asset_id,
                    "kind": "temperature",
                    "reading_celsius": reading,
                    "max_celsius": threshold,
                    "within_threshold": reading <= threshold,
                    "source": source,
                }
            )
    return {
        "run_id": report.get("run_id"),
        "captures": captures,
        "readings": readings,
    }


def render_site_map(
    state: dict[str, Any],
    report: dict[str, Any],
    *,
    authoring: dict[str, Any] | None = None,
    route_execution: dict[str, Any] | None = None,
) -> str:
    map_data = build_map_data(state, report, authoring=authoring)
    if not map_data["zones"]:
        return '<div class="map-empty">Map data unavailable</div>'

    bounds = map_data["bounds"]
    bounds_attr = escape(json.dumps(bounds, separators=(",", ":")), quote=True)
    authoring_attr = escape(json.dumps(authoring or {}, separators=(",", ":")), quote=True)
    home_pose = next((zone for zone in map_data["zones"] if zone.get("id") == "HOME"), None)
    home_pose_attr = escape(
        json.dumps(
            {"x": home_pose["x"], "y": home_pose["y"]} if home_pose else {},
            separators=(",", ":"),
        ),
        quote=True,
    )
    projector = _MapProjector(bounds)
    route_points = " ".join(
        f"{projector.x(point['x']):.1f},{projector.y(point['y']):.1f}"
        for point in map_data["route"]
    )
    grid = _render_grid(projector)
    floor_cells = _render_floor_cells(projector, map_data)
    point_cloud = _render_point_cloud(projector, map_data)
    no_go = "".join(_render_no_go_zone(projector, zone) for zone in map_data["zones"])
    no_go += "".join(
        _render_no_go_shape(projector, shape) for shape in map_data["no_go_shapes"]
    )
    zones = "".join(_render_zone(projector, zone) for zone in map_data["zones"])
    assets = "".join(_render_asset(projector, asset) for asset in map_data["assets"])
    packages = "".join(_render_package(projector, package) for package in map_data["packages"])
    observations = "".join(
        _render_observation(projector, observation) for observation in map_data["observations"]
    )
    incidents = "".join(
        _render_incident(projector, incident) for incident in map_data["incidents"]
    )
    route = ""
    if route_points:
        route = (
            f'<polyline class="map-route" points="{route_points}" />'
            + "".join(_render_route_stop(projector, stop, index) for index, stop in enumerate(map_data["route"], 1))
        )
    robot = _render_live_robot_pose()
    scan_items = "".join(_render_scan_item(observation) for observation in map_data["observations"])
    rerun_source_url = _trusted_rerun_source_url(os.environ.get("DOGOPS_RERUN_SOURCE_URL"))
    rerun_web_url = _trusted_rerun_web_url(os.environ.get("DOGOPS_RERUN_WEB_URL"))
    rerun_web_url_attr = escape(rerun_web_url, quote=True)
    legend = (
        '<div class="map-legend">'
        '<span><i class="legend-free"></i>free grid</span>'
        '<span><i class="legend-heatmap"></i>DimOS heatmap</span>'
        '<span><i class="legend-route"></i>trajectory</span>'
        '<span><i class="legend-live"></i>live odom</span>'
        '<span><i class="legend-tag"></i>tag return</span>'
        '<span><i class="legend-no-go"></i>no-go cost</span>'
        '<span><i class="legend-incident"></i>P1/P2 event</span>'
        "</div>"
    )
    layer_controls = (
        '<div class="map-layer-controls" data-map-layer-controls>'
        '<button type="button" data-map-layer="semantic" aria-pressed="true">Semantic</button>'
        '<button type="button" data-map-layer="heatmap" aria-pressed="true">Heatmap</button>'
        '<button type="button" data-map-layer="path" aria-pressed="true">Path</button>'
        '<button type="button" data-map-layer="robot" aria-pressed="true">Robot</button>'
        "</div>"
    )
    edit_controls = (
        '<div class="map-edit-controls" data-map-edit-controls>'
        '<button type="button" data-map-edit-action="map_from_scratch">Map From Scratch</button>'
        '<button type="button" data-map-edit-action="return_home">Return Home</button>'
        '<button type="button" data-map-edit-mode="select" aria-pressed="true">Select</button>'
        '<button type="button" data-map-edit-mode="home" aria-pressed="false">Set Home</button>'
        '<button type="button" data-map-edit-mode="zone" aria-pressed="false">Label</button>'
        '<button type="button" data-map-edit-mode="asset" aria-pressed="false">Asset</button>'
        '<button type="button" data-map-edit-mode="package" aria-pressed="false">Package</button>'
        '<button type="button" data-map-edit-mode="no_go" aria-pressed="false">No-Go</button>'
        '<button type="button" data-map-edit-mode="route" aria-pressed="false">Add Photo POI</button>'
        '<button type="button" data-map-edit-mode="incident" aria-pressed="false">Incident</button>'
        '<button type="button" data-map-edit-mode="tag" aria-pressed="false">Bind Tag</button>'
        '<button type="button" data-map-edit-action="use_observation">Use Observation</button>'
        '<button type="button" data-map-edit-action="delete_selected">Delete</button>'
        '<button type="button" data-map-edit-action="route_select">Select Route</button>'
        '<button type="button" data-map-edit-action="run_route_sim">Simulate POI Route</button>'
        '<button type="button" data-map-edit-action="run_route">Run POI Route</button>'
        '<button type="button" data-map-edit-action="stop_route">Stop Route</button>'
        '<button type="button" data-map-edit-action="route_up">Route Up</button>'
        '<button type="button" data-map-edit-action="route_down">Route Down</button>'
        '<button type="button" data-map-edit-action="publish_no_go">Publish No-Go</button>'
        '<button type="button" data-map-edit-action="save">Save</button>'
        '<button type="button" data-map-edit-action="reset">Reset</button>'
        '<button type="button" data-map-edit-action="export">Export</button>'
        "</div>"
    )
    route_execution_status = _route_execution_status_text(route_execution)
    return f"""
      <div class="map-shell" data-map-surface>
        {_render_rerun_surface(rerun_source_url, rerun_web_url)}
        {layer_controls}
        {edit_controls}
        <svg class="site-map" role="img" aria-label="DogOps mission map"
          data-live-map-svg data-map-bounds="{bounds_attr}" data-map-authoring="{authoring_attr}"
          data-home-pose="{home_pose_attr}"
          viewBox="0 0 {MAP_WIDTH} {MAP_HEIGHT}">
          <defs>
            <filter id="dogops-map-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <pattern id="dogops-map-hatch" width="8" height="8" patternUnits="userSpaceOnUse">
              <path d="M-2,8 L8,-2 M0,10 L10,0" class="map-hatch-line" />
            </pattern>
          </defs>
          <rect class="map-bg" x="0" y="0" width="{MAP_WIDTH}" height="{MAP_HEIGHT}" rx="8" />
          <g data-layer="heatmap" data-live-heatmap></g>
          <g data-layer="semantic">
            {floor_cells}
            {grid}
            {point_cloud}
            {no_go}
            {zones}
            {assets}
            {packages}
            {observations}
            {incidents}
          </g>
          <g data-layer="path">
            {route}
            <polyline class="map-dimos-path" data-live-path points="" />
          </g>
          <g data-layer="robot">
            {robot}
          </g>
        </svg>
        {legend}
        <div class="map-workflow">
          <a href="{rerun_web_url_attr}" target="_blank" rel="noreferrer" data-rerun-web-link>Open 3D View</a>
          <span class="map-command-status" data-map-command-status>Map command idle</span>
        </div>
        <div class="map-authoring-status" data-map-authoring-status>Map authoring idle</div>
        <div class="map-route-execution-status" data-route-execution-status>{escape(route_execution_status)}</div>
        <div class="map-live-status" data-live-map-status>Live odom: waiting for Go2</div>
        <ol class="scan-strip">{scan_items}</ol>
      </div>
    """


def render_dashboard_html(
    state: dict[str, Any],
    report: dict[str, Any],
    *,
    robot_control_token: str | None = None,
    authoring: dict[str, Any] | None = None,
    route_execution: dict[str, Any] | None = None,
    rerun_command: dict[str, Any] | None = None,
) -> str:
    run = state["run"]
    nav = report.get("nav_summary") or {}
    packages = report.get("packages") or []
    incidents = report.get("incidents") or []
    work_orders = report.get("work_orders") or []
    checkpoints = report.get("checkpoint_verifications") or []
    what_changed = report.get("what_changed") or []
    packages_metric = f"{report['packages_observed']}/{report['packages_expected']}"
    nav_metric = f"{nav.get('waypoints_reached', 0)}/{nav.get('waypoints_total', 0)}"
    checkpoint_metric = f"{report.get('checkpoints_verified', 0)}/{report.get('checkpoints_total', 0)}"
    tag_recovery_metric = (
        f"{nav.get('tag_reacquisition_successes', 0)}/"
        f"{nav.get('tag_reacquisition_attempts', 0)}"
    )
    mean_target_time_metric = f"{nav.get('mean_elapsed_s', 0):.1f}s"
    route_coverage_metric = f"{float(nav.get('route_coverage', 0.0)) * 100:.0f}%"
    map_html = render_site_map(
        state,
        report,
        authoring=authoring,
        route_execution=route_execution,
    )
    route_data = build_route_data(state, report, authoring=authoring)
    poi_data = build_poi_data(state, report)
    proof_data = build_test_flow_proof(
        state,
        report,
        route_data,
        poi_data,
        route_execution=route_execution,
        rerun_command=rerun_command,
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DogOps SiteOps Agent</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --ink: #17202a;
      --muted: #5b6776;
      --line: #d7dce3;
      --panel: #ffffff;
      --accent: #0f766e;
      --warn: #b45309;
      --danger: #b91c1c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      background: #111827;
      color: white;
      padding: 18px 28px;
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: end;
    }}
    h1, h2 {{ margin: 0; }}
    h1 {{ font-size: 22px; font-weight: 700; letter-spacing: 0; }}
    h2 {{ font-size: 15px; margin-bottom: 8px; }}
    main {{
      padding: 22px 28px 32px;
      display: grid;
      grid-template-columns: minmax(360px, 1.05fr) minmax(320px, 0.95fr);
      gap: 16px;
      align-items: start;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }}
    .ops-stack {{ display: grid; gap: 10px; }}
    .wide {{ grid-column: 1 / -1; }}
    .metric-row {{
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 10px;
    }}
    .ops-stack .metric-row {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 6px;
      min-height: 66px;
      padding: 8px 10px;
      background: #fbfcfd;
    }}
    .metric strong {{ display: block; font-size: 19px; }}
    .muted {{ color: var(--muted); }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 6px; text-align: left; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .state-resolved, .state-verified, .state-verified_closed, .state-found_ok {{ color: var(--accent); font-weight: 700; }}
    .state-open, .state-missing {{ color: var(--danger); font-weight: 700; }}
    .severity-P1 {{ color: var(--danger); font-weight: 700; }}
    .state-captured, .state-returned, .state-pass {{ color: var(--accent); font-weight: 700; }}
    .state-fail {{ color: var(--danger); font-weight: 700; }}
    .timeline {{ display: grid; gap: 8px; }}
    .timeline div {{ border-left: 3px solid var(--accent); padding-left: 10px; }}
    .evidence-grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }}
    .compact-list {{
      display: grid;
      gap: 8px;
      list-style: none;
      margin: 0;
      padding: 0;
    }}
    .compact-list li {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfd;
      padding: 8px 10px;
    }}
    .poi-capture {{
      align-items: center;
      display: grid;
      gap: 0.65rem;
      grid-template-columns: 96px 1fr;
    }}
    .poi-capture img {{
      aspect-ratio: 16 / 9;
      background: #03060b;
      border: 1px solid #263244;
      border-radius: 6px;
      object-fit: cover;
      width: 96px;
    }}
    .proof-grid {{
      display: grid;
      gap: 8px;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    }}
    .proof-item {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfd;
      padding: 10px 12px;
    }}
    .proof-item strong {{
      display: block;
      margin-bottom: 4px;
    }}
    .map-panel {{
      background: #07090d;
      border-color: #1d2430;
      color: #d8dee9;
      min-height: 675px;
      overflow: hidden;
    }}
    .map-panel h2 {{ color: #eef2f8; }}
    .map-shell {{ display: grid; gap: 10px; }}
    .rerun-surface {{
      background: #03060b;
      border: 1px solid #1d2430;
      border-radius: 8px;
      contain: layout paint;
      display: grid;
      height: clamp(360px, 44vh, 620px);
      max-height: 620px;
      min-height: 360px;
      overflow: hidden;
      position: relative;
    }}
    .rerun-canvas {{
      background: #03060b;
      display: block;
      height: 100%;
      max-height: 100%;
      min-height: 0;
      overflow: hidden;
      position: relative;
      width: 100%;
    }}
    .rerun-canvas > * {{
      height: 100% !important;
      max-height: 100% !important;
      min-height: 0 !important;
      width: 100% !important;
    }}
    .rerun-canvas canvas {{
      height: 100%;
      max-height: 100%;
      width: 100%;
    }}
    .rerun-canvas[hidden] {{ display: none; }}
    .rerun-standby {{
      align-items: center;
      background:
        linear-gradient(135deg, rgba(82, 224, 196, 0.12), rgba(125, 211, 252, 0.08)),
        repeating-linear-gradient(90deg, rgba(148, 163, 184, 0.08) 0 1px, transparent 1px 34px),
        repeating-linear-gradient(0deg, rgba(148, 163, 184, 0.08) 0 1px, transparent 1px 34px),
        #05070c;
      display: grid;
      gap: 10px;
      inset: 0;
      justify-items: center;
      padding: 18px;
      position: absolute;
      text-align: center;
      z-index: 1;
    }}
    .rerun-standby[hidden] {{ display: none; }}
    .rerun-offline {{
      align-items: center;
      color: #d8dee9;
      display: grid;
      inset: 0;
      justify-items: center;
      padding: 18px;
      position: absolute;
      text-align: center;
      z-index: 2;
    }}
    .rerun-offline[hidden] {{ display: none; }}
    .rerun-chip {{
      border: 1px solid #2d3a4f;
      border-radius: 999px;
      color: #d8fff6;
      font-size: 12px;
      font-weight: 700;
      padding: 5px 10px;
    }}
    .rerun-status {{
      color: #a9b4c4;
      font: 12px/1.35 ui-monospace, SFMono-Regular, Menlo, monospace;
      min-height: 16px;
    }}
    .rerun-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: center;
    }}
    .rerun-controls button, .rerun-controls a {{
      border: 1px solid #334155;
      border-radius: 6px;
      background: #0d1119;
      color: #e5edf5;
      cursor: pointer;
      font: inherit;
      min-height: 34px;
      padding: 6px 10px;
      text-decoration: none;
    }}
    .rerun-controls button:hover, .rerun-controls a:hover {{ border-color: #52e0c4; }}
    .site-map {{
      aspect-ratio: 23 / 14;
      background: #03060b;
      border: 1px solid #1d2430;
      border-radius: 8px;
      display: block;
      max-height: 580px;
      min-height: 420px;
      width: 100%;
    }}
    .map-bg {{ fill: #05070c; }}
    .map-free-cell {{ fill: #484981; opacity: 0.42; }}
    .map-cost-cell {{ fill: #171b2b; opacity: 0.72; }}
    .map-grid {{ stroke: #18202c; stroke-width: 1; }}
    .map-grid-major {{ stroke: #2f4058; stroke-width: 1.2; }}
    .map-hatch-line {{ stroke: #f87171; stroke-width: 1; opacity: 0.35; }}
    .map-point {{ fill: #7dd3fc; opacity: 0.46; }}
    .map-point.hot {{ fill: #f0abfc; opacity: 0.62; }}
    .map-live-cost-cell {{ opacity: 0.64; stroke: rgba(255, 255, 255, 0.08); stroke-width: 0.4; }}
    .map-no-go {{
      fill: rgba(127, 29, 29, 0.42);
      stroke: #ef4444;
      stroke-dasharray: 8 5;
      stroke-width: 1.6;
    }}
    .map-no-go-hatch {{ fill: url(#dogops-map-hatch); opacity: 0.55; }}
    .map-route {{
      fill: none;
      filter: url(#dogops-map-glow);
      stroke: #52e0c4;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-width: 4;
    }}
    .map-route-stop {{ fill: #05070c; stroke: #52e0c4; stroke-width: 2; }}
    .map-route-index {{
      dominant-baseline: central;
      fill: #d8fff6;
      font-size: 11px;
      font-weight: 700;
      text-anchor: middle;
    }}
    .map-zone-anchor {{ fill: #05070c; stroke: #8b95a7; stroke-width: 1.5; }}
    .map-zone-label {{
      fill: #b9c4d5;
      font-size: 11px;
      font-weight: 650;
      letter-spacing: 0.03em;
      paint-order: stroke;
      stroke: #05070c;
      stroke-linejoin: round;
      stroke-width: 4px;
      text-anchor: middle;
    }}
    .map-zone-label, .map-asset-label, .map-package-label {{
      fill: #e5edf5;
      font-size: 11px;
      paint-order: stroke;
      stroke: #05070c;
      stroke-width: 4px;
      stroke-linejoin: round;
    }}
    .map-asset {{ fill: #c7f9ff; stroke: #22d3ee; stroke-width: 1.5; }}
    .map-asset-label {{ fill: #d6fbff; }}
    .map-tag-face {{ fill: #05070c; stroke: #d1d5db; stroke-width: 1.5; }}
    .map-tag-core {{ fill: #d1d5db; }}
    .map-package {{ fill: #f59e0b; stroke: #fef3c7; stroke-width: 1.2; }}
    .map-package.state-found_ok {{ fill: #34d399; stroke: #bbf7d0; }}
    .map-package.state-missing {{ fill: #7f1d1d; stroke: #f87171; stroke-dasharray: 4 3; }}
    .map-package.state-wrong_zone, .map-package.state-blocking_asset {{
      fill: #fb923c;
      stroke: #fed7aa;
    }}
    .map-observation {{ fill: #05070c; stroke: #a78bfa; stroke-width: 2; }}
    .map-observation-ray {{ stroke: #a78bfa; stroke-dasharray: 4 5; stroke-width: 1.2; }}
    .map-incident {{ fill: none; filter: url(#dogops-map-glow); stroke: #fb7185; stroke-width: 2.4; }}
    .map-incident-label {{
      fill: #fecdd3;
      font-size: 11px;
      font-weight: 700;
      paint-order: stroke;
      stroke: #05070c;
      stroke-linejoin: round;
      stroke-width: 4px;
    }}
    .map-robot {{ fill: rgba(82, 224, 196, 0.12); stroke: #52e0c4; stroke-width: 1.5; }}
    .map-robot-core {{ fill: #52e0c4; stroke: #d8fff6; stroke-width: 1.2; }}
    .map-live-trace {{
      fill: none;
      filter: url(#dogops-map-glow);
      stroke: #facc15;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-width: 3.5;
    }}
    .map-dimos-path {{
      fill: none;
      filter: url(#dogops-map-glow);
      stroke: #38bdf8;
      stroke-dasharray: 9 7;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-width: 3;
    }}
    .map-live-robot-halo {{ fill: rgba(250, 204, 21, 0.16); stroke: #facc15; stroke-width: 1.5; }}
    .map-live-robot-core {{ fill: #facc15; stroke: #fff7cc; stroke-width: 1.2; }}
    .map-dimos-target-ring {{ fill: rgba(56, 189, 248, 0.16); stroke: #38bdf8; stroke-width: 2; }}
    .map-dimos-target-core {{ fill: #38bdf8; stroke: #e0f2fe; stroke-width: 1.2; }}
    .map-go-to-ring {{ fill: rgba(248, 113, 113, 0.14); stroke: #f87171; stroke-width: 2; }}
    .map-go-to-cross {{ stroke: #fecaca; stroke-linecap: round; stroke-width: 2; }}
    .map-axis-label {{ fill: #657184; font-size: 10px; }}
    .site-map.go-to-armed {{ cursor: crosshair; }}
    .map-legend {{
      color: #a9b4c4;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      font-size: 12px;
    }}
    .map-legend span {{ align-items: center; display: inline-flex; gap: 6px; }}
    .map-legend i {{
      border-radius: 999px;
      display: inline-block;
      height: 10px;
      width: 10px;
    }}
    .legend-free {{ background: #484981; }}
    .legend-heatmap {{ background: #f97316; }}
    .legend-route {{ background: #52e0c4; }}
    .legend-live {{ background: #facc15; }}
    .legend-tag {{ background: #a78bfa; }}
    .legend-no-go {{ background: #ef4444; }}
    .legend-incident {{ background: #fb7185; }}
    .map-workflow {{
      align-items: center;
      color: #a9b4c4;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      font-size: 12px;
    }}
    .map-workflow a {{
      color: #bfdbfe;
      font-weight: 700;
      text-decoration: none;
    }}
    .map-workflow a:hover {{ text-decoration: underline; }}
    .map-command-status {{
      color: #fecaca;
      font: 12px/1.35 ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    .map-command-status.ok {{ color: #86efac; }}
    .map-command-status.error {{ color: #fca5a5; }}
    .map-layer-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .map-edit-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .map-layer-controls button, .map-edit-controls button {{
      background: #0d1119;
      border: 1px solid #334155;
      border-radius: 999px;
      color: #d8dee9;
      cursor: pointer;
      font: inherit;
      min-height: 30px;
      padding: 5px 10px;
    }}
    .map-layer-controls button[aria-pressed="true"], .map-edit-controls button[aria-pressed="true"] {{
      background: #123b36;
      border-color: #52e0c4;
      color: #d8fff6;
      font-weight: 700;
    }}
    .map-live-status {{
      color: #f7d75d;
      font: 12px/1.35 ui-monospace, SFMono-Regular, Menlo, monospace;
      min-height: 18px;
    }}
    .map-authoring-status {{
      color: #c4b5fd;
      font: 12px/1.35 ui-monospace, SFMono-Regular, Menlo, monospace;
      min-height: 18px;
    }}
    .map-authoring-status.ok {{ color: #86efac; }}
    .map-authoring-status.error {{ color: #fca5a5; }}
    .map-route-execution-status {{
      color: #bfdbfe;
      font: 12px/1.35 ui-monospace, SFMono-Regular, Menlo, monospace;
      min-height: 18px;
    }}
    .map-route-execution-status.ok {{ color: #86efac; }}
    .map-route-execution-status.error {{ color: #fca5a5; }}
    .scan-strip {{
      color: #b8c4d4;
      display: grid;
      gap: 6px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      list-style: none;
      margin: 0;
      padding: 0;
    }}
    .scan-strip li {{
      background: #0d1119;
      border: 1px solid #1d2430;
      border-radius: 6px;
      min-height: 36px;
      padding: 7px 9px;
    }}
    .scan-strip strong {{ color: #eef2f8; }}
    .map-empty {{
      align-items: center;
      background: #101721;
      border: 1px solid #263241;
      border-radius: 8px;
      color: #cbd5e1;
      display: flex;
      min-height: 420px;
      justify-content: center;
    }}
    .robot-controls {{
      display: grid;
      grid-template-columns: repeat(3, minmax(72px, 1fr));
      gap: 6px;
    }}
    .keyboard-map {{
      color: var(--muted);
      display: grid;
      gap: 6px;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      margin-top: 8px;
    }}
    .keyboard-map span {{
      align-items: center;
      display: inline-flex;
      gap: 6px;
      min-width: 0;
    }}
    kbd {{
      background: #eef2f7;
      border: 1px solid #cfd6df;
      border-bottom-color: #b8c0cc;
      border-radius: 4px;
      color: #17202a;
      display: inline-block;
      font: 11px/1.1 ui-monospace, SFMono-Regular, Menlo, monospace;
      min-width: 22px;
      padding: 3px 5px;
      text-align: center;
    }}
    .posture-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
    }}
    .map-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
    }}
    .posture-controls button {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      color: var(--ink);
      cursor: pointer;
      font: inherit;
      min-height: 34px;
      padding: 6px 10px;
    }}
    .map-controls button {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      color: var(--ink);
      cursor: pointer;
      font: inherit;
      min-height: 34px;
      padding: 6px 10px;
    }}
    .posture-controls button:hover {{ border-color: var(--accent); }}
    .map-controls button:hover {{ border-color: var(--accent); }}
    .map-controls button[aria-pressed="true"] {{
      background: #fef2f2;
      border-color: var(--danger);
      color: var(--danger);
      font-weight: 700;
    }}
    .posture-controls button:disabled {{ cursor: wait; opacity: 0.65; }}
    .map-controls button:disabled {{ cursor: wait; opacity: 0.65; }}
    .motion-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
    }}
    .motion-controls button {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      color: var(--ink);
      cursor: pointer;
      font: inherit;
      min-height: 34px;
      padding: 6px 10px;
    }}
    .motion-controls button[aria-pressed="true"] {{
      background: #e6f4f1;
      border-color: var(--accent);
      color: var(--accent);
      font-weight: 700;
    }}
    .motion-controls button:disabled {{ cursor: wait; opacity: 0.65; }}
    .robot-controls button {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      color: var(--ink);
      cursor: pointer;
      font: inherit;
      min-height: 36px;
      padding: 6px 10px;
    }}
    .robot-controls button:hover {{ border-color: var(--accent); }}
    .robot-controls button:disabled {{ cursor: wait; opacity: 0.65; }}
    .robot-controls .hard-stop {{
      background: var(--danger);
      border-color: var(--danger);
      color: #ffffff;
      font-weight: 700;
    }}
    .robot-status {{
      min-height: 18px;
      margin-top: 8px;
      color: var(--muted);
    }}
    .robot-status.error {{ color: var(--danger); }}
    .robot-status.ok {{ color: var(--accent); }}
    @media (max-width: 920px) {{
      main {{ gap: 12px; padding: 16px 18px 24px; }}
      section {{ padding: 10px; }}
      .ops-stack {{ gap: 8px; }}
      .map-panel {{ min-height: 0; }}
      .site-map {{ min-height: 320px; }}
      .keyboard-map {{
        font-size: 12px;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 720px) {{
      header {{ align-items: start; flex-direction: column; }}
      main {{ grid-template-columns: 1fr; padding: 14px; }}
      .metric-row {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .evidence-grid {{ grid-template-columns: 1fr; }}
      .site-map {{ min-height: 330px; }}
      .scan-strip {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>DogOps SiteOps Agent</h1>
      <div class="muted">Mission {escape(str(run["mission_id"]))} / run {escape(str(run["id"]))}</div>
    </div>
    <div>State: <strong>{escape(str(run["state"]))}</strong></div>
  </header>
  <main>
    <section class="wide" data-test-flow-proof>
      <h2>Test Flow Proof</h2>
      {test_flow_proof(proof_data)}
    </section>
    <section class="map-panel">
      <h2>Mission Map</h2>
      {map_html}
    </section>
    <div class="ops-stack">
      <section>
        <h2>Run Summary</h2>
        <div class="metric-row">
          {metric("Packages", packages_metric)}
          {metric("Exceptions", report["manifest_exceptions"])}
          {metric("Incidents", report["incidents_opened"])}
          {metric("Verified WOs", report["work_orders_verified_closed"])}
          {metric("Nav", nav_metric)}
          {metric("Tag Sign-In", checkpoint_metric)}
          {metric("Coverage", route_coverage_metric)}
        </div>
      </section>
      <section>
        <h2>Robot Control</h2>
        <div class="posture-controls" data-posture-controls>
          <button type="button" data-posture="wake">Wake / Stand</button>
          <button type="button" data-posture="balance">Balance</button>
          <button type="button" data-posture="sleep">Sleep</button>
        </div>
        <div class="map-controls" data-map-controls>
          <button type="button" data-map-action="start">Start Live Map</button>
          <button type="button" data-map-action="origin">Set Map Origin</button>
          <button type="button" data-map-action="arm_go_to" aria-pressed="false">Arm Go To</button>
        </div>
        <div class="motion-controls" data-motion-controls>
          <button type="button" data-motion="nudge" aria-pressed="true">Nudge</button>
          <button type="button" data-motion="step" aria-pressed="false">Step</button>
          <button type="button" data-motion="walk" aria-pressed="false">Walk</button>
        </div>
        <div class="robot-controls" data-robot-controls>
          <span></span>
          <button type="button" data-command="forward" data-key-hint="W / Up">Forward</button>
          <span></span>
          <button type="button" data-command="left" data-key-hint="A / Left">Left</button>
          <button type="button" class="hard-stop" data-command="hard_stop" data-key-hint="Space / Esc">HARD STOP</button>
          <button type="button" data-command="right" data-key-hint="D / Right">Right</button>
          <button type="button" data-command="yaw_left" data-key-hint="Q">Yaw L</button>
          <button type="button" data-command="backward" data-key-hint="S / Down">Back</button>
          <button type="button" data-command="yaw_right" data-key-hint="E">Yaw R</button>
        </div>
        <div class="keyboard-map" data-keyboard-map aria-label="Keyboard controls">
          <span><kbd>W</kbd><kbd>Up</kbd>Forward</span>
          <span><kbd>S</kbd><kbd>Down</kbd>Back</span>
          <span><kbd>A</kbd><kbd>Left</kbd>Left</span>
          <span><kbd>D</kbd><kbd>Right</kbd>Right</span>
          <span><kbd>Q</kbd>Yaw L</span>
          <span><kbd>E</kbd>Yaw R</span>
          <span><kbd>Space</kbd><kbd>Esc</kbd>Hard stop</span>
        </div>
        <div class="robot-status" data-robot-status>Idle</div>
      </section>
      <section>
        <h2>Checkpoint Sign-In</h2>
        {checkpoint_table(checkpoints)}
      </section>
      <section>
        <h2>Mission Timeline</h2>
        <div class="timeline">
          <div>Inbound scan completed</div>
          <div>COOLING_1 inspected</div>
          <div>INC-001 / WO-001 opened</div>
          <div>Human remediation simulated</div>
          <div>Verification completed</div>
        </div>
      </section>
      <section>
        <h2>What Changed</h2>
        <ul>{''.join(f"<li>{escape(str(item))}</li>" for item in what_changed)}</ul>
      </section>
    </div>
    <section class="wide">
      <h2>Package Reconciliation</h2>
      {package_table(packages)}
    </section>
    <section>
      <h2>Incidents</h2>
      {incident_table(incidents)}
    </section>
    <section>
      <h2>Work Orders</h2>
      {work_order_table(work_orders)}
    </section>
    <section class="wide">
      <h2>Navigation Eval</h2>
      <div class="metric-row">
        {metric("Waypoints", nav_metric)}
        {metric("Retries", nav.get("retries_total", 0))}
        {metric("Guided", nav.get("guided_interventions", 0))}
        {metric("Tag Recovery", tag_recovery_metric)}
        {metric("Route Coverage", route_coverage_metric)}
        {metric("Mean Target Time", mean_target_time_metric)}
      </div>
    </section>
    <section class="wide">
      <h2>Route / POI Evidence</h2>
      <div class="evidence-grid">
        <div>
          <h2>Route Stops</h2>
          {route_table(route_data["stops"], poi_data)}
        </div>
        <div>
          <h2>POI Evidence</h2>
          <div data-poi-evidence>{poi_list(poi_data)}</div>
        </div>
      </div>
    </section>
  </main>
  <script>
    (() => {{
      const controls = document.querySelector("[data-robot-controls]");
      const postureControls = document.querySelector("[data-posture-controls]");
      const motionControls = document.querySelector("[data-motion-controls]");
      const mapControls = document.querySelector("[data-map-controls]");
      const layerControls = document.querySelector("[data-map-layer-controls]");
      const mapEditControls = document.querySelector("[data-map-edit-controls]");
      const rerunSurface = document.querySelector("[data-rerun-surface]");
      const rerunConnect = document.querySelector("[data-rerun-connect]");
      const rerunStandby = document.querySelector("[data-rerun-standby]");
      const rerunStatus = document.querySelector("[data-rerun-status]");
      const liveMapSvg = document.querySelector("[data-live-map-svg]");
      const poiEvidence = document.querySelector("[data-poi-evidence]");
      const liveMapStatus = document.querySelector("[data-live-map-status]");
      const mapCommandStatus = document.querySelector("[data-map-command-status]");
      const mapAuthoringStatus = document.querySelector("[data-map-authoring-status]");
      const routeExecutionStatus = document.querySelector("[data-route-execution-status]");
      const liveHeatmap = liveMapSvg ? liveMapSvg.querySelector("[data-live-heatmap]") : null;
      const livePath = liveMapSvg ? liveMapSvg.querySelector("[data-live-path]") : null;
      const liveTrace = liveMapSvg ? liveMapSvg.querySelector("[data-live-trace]") : null;
      const liveRobot = liveMapSvg ? liveMapSvg.querySelector("[data-live-robot]") : null;
      const liveTarget = liveMapSvg ? liveMapSvg.querySelector("[data-live-target]") : null;
      const goToMarker = liveMapSvg ? liveMapSvg.querySelector("[data-go-to-marker]") : null;
      const status = document.querySelector("[data-robot-status]");
      if (!controls || !status) return;
      let motionProfile = "nudge";
      let robotBusy = false;
      let liveMapPolling = false;
      let dimosMapPolling = false;
      let routeExecutionPolling = false;
      let dimosRobotPoseActive = false;
      let goToArmed = false;
      let mapEditMode = "select";
      let mapAuthoring = null;
      let selectedMapObject = null;
      let dragMapObject = null;
      let liveMapBounds = null;
      let liveOverlayBounds = null;
      let mapHomePose = null;
      try {{
        liveMapBounds = liveMapSvg ? JSON.parse(liveMapSvg.dataset.mapBounds || "{{}}") : null;
      }} catch (_) {{
        liveMapBounds = null;
      }}
      try {{
        mapAuthoring = liveMapSvg ? JSON.parse(liveMapSvg.dataset.mapAuthoring || "{{}}") : null;
      }} catch (_) {{
        mapAuthoring = null;
      }}
      try {{
        mapHomePose = liveMapSvg ? JSON.parse(liveMapSvg.dataset.homePose || "{{}}") : null;
      }} catch (_) {{
        mapHomePose = null;
      }}
      liveOverlayBounds = liveMapBounds;
      const liveMapSize = {{width: {MAP_WIDTH}, height: {MAP_HEIGHT}}};
      const motionLabels = {{
        nudge: "Nudge",
        step: "Step",
        walk: "Walk",
      }};
      const robotControlToken = {json.dumps(robot_control_token)};
      const keyboardCommands = new Map([
        ["KeyW", "forward"],
        ["ArrowUp", "forward"],
        ["KeyS", "backward"],
        ["ArrowDown", "backward"],
        ["KeyA", "left"],
        ["ArrowLeft", "left"],
        ["KeyD", "right"],
        ["ArrowRight", "right"],
        ["KeyQ", "yaw_left"],
        ["KeyE", "yaw_right"],
        ["Space", "hard_stop"],
        ["Escape", "hard_stop"],
      ]);
      const buttons = Array.from(document.querySelectorAll("[data-command], [data-posture], [data-motion], [data-map-action]"));
      const setBusy = (busy) => buttons.forEach((button) => {{
        button.disabled = busy && button.getAttribute("data-command") !== "hard_stop";
      }});
      const setStatus = (text, state) => {{
        status.textContent = text;
        status.className = `robot-status ${{state || ""}}`;
      }};
      const setMapCommandStatus = (text, state) => {{
        if (!mapCommandStatus) return;
        mapCommandStatus.textContent = text;
        mapCommandStatus.className = `map-command-status ${{state || ""}}`;
      }};
      const setMapAuthoringStatus = (text, state) => {{
        if (!mapAuthoringStatus) return;
        mapAuthoringStatus.textContent = text;
        mapAuthoringStatus.className = `map-authoring-status ${{state || ""}}`;
      }};
      const setRouteExecutionStatus = (text, state) => {{
        if (!routeExecutionStatus) return;
        routeExecutionStatus.textContent = text;
        routeExecutionStatus.className = `map-route-execution-status ${{state || ""}}`;
      }};
      const setRerunStatus = (text) => {{
        if (rerunStatus) rerunStatus.textContent = text;
      }};
      const connectRerunSurface = async ({{replay = false}} = {{}}) => {{
        if (!rerunSurface) return false;
        setRerunStatus("Connecting 3D View...");
        try {{
          const viewer = window.DogOpsRerunWebViewer || await import("/static/rerun-web-viewer.js?v=dogops-rerun-v2");
          await viewer.mount(rerunSurface);
          if (replay && viewer.replay) await viewer.replay(rerunSurface);
          if (rerunStandby) rerunStandby.hidden = true;
          return true;
        }} catch (error) {{
          setRerunStatus(`3D View unavailable: ${{error.message}}`);
          return false;
        }}
      }};
      const projectPoseWithBounds = (pose, bounds) => {{
        if (!bounds || !pose) return null;
        const spanX = Math.max(0.1, bounds.x_max - bounds.x_min);
        const spanY = Math.max(0.1, bounds.y_max - bounds.y_min);
        return {{
          x: ((pose.x - bounds.x_min) / spanX) * liveMapSize.width,
          y: liveMapSize.height - (((pose.y - bounds.y_min) / spanY) * liveMapSize.height),
        }};
      }};
      const projectLivePose = (pose) => projectPoseWithBounds(pose, liveMapBounds);
      const projectLiveOverlayPose = (pose) => projectPoseWithBounds(pose, liveOverlayBounds);
      const projectWorldPoint = (x, y) => projectLivePose({{x, y}});
      const projectLiveOverlayPoint = (x, y) => projectLiveOverlayPose({{x, y}});
      const worldFromSvgEvent = (event) => {{
        if (!liveMapSvg || !liveMapBounds) return null;
        const matrix = liveMapSvg.getScreenCTM();
        if (!matrix) return null;
        const point = liveMapSvg.createSVGPoint();
        point.x = event.clientX;
        point.y = event.clientY;
        const svgPoint = point.matrixTransform(matrix.inverse());
        const spanX = Math.max(0.1, liveMapBounds.x_max - liveMapBounds.x_min);
        const spanY = Math.max(0.1, liveMapBounds.y_max - liveMapBounds.y_min);
        return {{
          x: liveMapBounds.x_min + (svgPoint.x / liveMapSize.width) * spanX,
          y: liveMapBounds.y_min + ((liveMapSize.height - svgPoint.y) / liveMapSize.height) * spanY,
        }};
      }};
      const setGoToArmed = (armed) => {{
        goToArmed = armed;
        if (liveMapSvg) liveMapSvg.classList.toggle("go-to-armed", armed);
        if (mapControls) {{
          const button = mapControls.querySelector('[data-map-action="arm_go_to"]');
          if (button) button.setAttribute("aria-pressed", armed ? "true" : "false");
        }}
        setMapCommandStatus(armed ? "Map Go To armed" : "Map command idle", armed ? "ok" : "");
      }};
      const setGoToMarker = (target) => {{
        if (!goToMarker || !target) return;
        const projected = projectWorldPoint(target.x, target.y);
        if (!projected) return;
        goToMarker.style.display = "";
        goToMarker.setAttribute(
          "transform",
          `translate(${{projected.x.toFixed(1)}} ${{projected.y.toFixed(1)}})`
        );
      }};
      const authoringPoint = (target) => ({{
        x: Math.round(target.x * 1000) / 1000,
        y: Math.round(target.y * 1000) / 1000,
        theta_deg: null,
        source: "dashboard_edit",
      }});
      const postAuthoring = async (url, body, method = "POST") => {{
        setMapAuthoringStatus("Saving map edit...", "");
        try {{
          const response = await fetch(url, {{
            method,
            headers: {{
              "Content-Type": "application/json",
              "X-DogOps-Control-Token": robotControlToken,
            }},
            body: JSON.stringify(body),
          }});
          const result = await response.json();
          if (!response.ok || result.ok === false) {{
            throw new Error(result.message || result.error || "map_authoring_failed");
          }}
          mapAuthoring = result.authoring || mapAuthoring;
          setMapAuthoringStatus("Map edit saved; refreshing", "ok");
          await refreshDimOSMap();
          window.setTimeout(() => window.location.reload(), 150);
          return result;
        }} catch (error) {{
          setMapAuthoringStatus(`Map edit failed: ${{error.message}}`, "error");
          return null;
        }}
      }};
      const setMapEditMode = (mode) => {{
        mapEditMode = mode || "select";
        if (mapEditControls) {{
          mapEditControls.querySelectorAll("[data-map-edit-mode]").forEach((button) => {{
            button.setAttribute("aria-pressed", button.getAttribute("data-map-edit-mode") === mapEditMode ? "true" : "false");
          }});
        }}
        setMapAuthoringStatus(mapEditMode === "select" ? "Map authoring idle" : `Map authoring: ${{mapEditMode}}`, mapEditMode === "select" ? "" : "ok");
      }};
      const selectMapObject = (target) => {{
        const item = target ? target.closest("[data-edit-kind][data-edit-id]") : null;
        selectedMapObject = item ? {{
          kind: item.getAttribute("data-edit-kind"),
          id: item.getAttribute("data-edit-id"),
        }} : null;
        setMapAuthoringStatus(
          selectedMapObject ? `Selected ${{selectedMapObject.kind}} ${{selectedMapObject.id}}` : "Map authoring idle",
          selectedMapObject ? "ok" : ""
        );
        return selectedMapObject;
      }};
      const entityKindForSelected = () => {{
        if (!selectedMapObject) return "checkpoint";
        if (["zone", "asset", "package"].includes(selectedMapObject.kind)) return selectedMapObject.kind;
        return "checkpoint";
      }};
      const deleteSelectedMapObject = async () => {{
        if (!selectedMapObject || !selectedMapObject.id) {{
          setMapAuthoringStatus("Select an authored object first", "error");
          return;
        }}
        const id = selectedMapObject.id;
        if (!window.confirm(`Delete authored map object ${{id}}?`)) return;
        const kind = selectedMapObject.kind;
        if (kind === "route_stop") {{
          await removeRouteWaypoint(id);
        }} else if (kind === "no_go_shape") {{
          await postAuthoring(`/api/map/no_go_shapes/${{encodeURIComponent(id)}}`, {{}}, "DELETE");
        }} else if (kind === "incident") {{
          const current = mapAuthoring || {{}};
          const incidentLocations = (current.incident_locations || []).filter((item) => item.incident_id !== id);
          await postAuthoring("/api/map/authoring", {{...current, incident_locations: incidentLocations}}, "PUT");
        }} else {{
          await postAuthoring(`/api/map/entities/${{encodeURIComponent(id)}}`, {{}}, "DELETE");
        }}
      }};
      const placeSelectedFromObservation = async () => {{
        if (!selectedMapObject || !selectedMapObject.id) {{
          setMapAuthoringStatus("Select an entity before using an observation", "error");
          return;
        }}
        const observationId = window.prompt("Observation id or blank to use tag id", "");
        const tagInput = observationId ? "" : window.prompt("Tag id", "");
        const payload = observationId
          ? {{observation_id: observationId, kind: entityKindForSelected()}}
          : {{tag_id: Number(tagInput), kind: entityKindForSelected()}};
        await postAuthoring(`/api/map/entities/${{encodeURIComponent(selectedMapObject.id)}}/from_observation`, payload);
      }};
      const selectedRoute = () => {{
        const current = mapAuthoring || {{}};
        const routes = Array.isArray(current.routes) ? current.routes : [];
        if (!routes.length) return null;
        if (!current.selected_route_id) return null;
        return routes.find((route) => route.id === current.selected_route_id) || null;
      }};
      const routeExecutionText = (state) => {{
        if (!state || !state.state) return "Execution: idle";
        const total = Number(state.waypoints_total || 0);
        const reached = Number(state.waypoints_reached || 0);
        const active = state.active_waypoint_id ? ` active=${{state.active_waypoint_id}}` : "";
        const transport = state.transport ? ` transport=${{state.transport}}` : "";
        const error = state.last_error ? ` error=${{state.last_error}}` : "";
        return `Execution: ${{state.state}} ${{reached}}/${{total}}${{active}}${{transport}}${{error}}`;
      }};
      const safeText = (value) => String(value == null ? "" : value);
      const appendText = (parent, tagName, text, className = "") => {{
        const element = document.createElement(tagName);
        if (className) element.className = className;
        element.textContent = safeText(text);
        parent.appendChild(element);
        return element;
      }};
      const evidenceImageSrc = (imagePath) => {{
        const path = safeText(imagePath).replace(/^\\/+/, "");
        return path ? `/${{path}}` : "";
      }};
      const renderPoiEvidence = (poi) => {{
        if (!poiEvidence) return;
        const list = document.createElement("ul");
        list.className = "compact-list";
        for (const capture of (poi.captures || []).slice(0, 8)) {{
          const item = document.createElement("li");
          const row = document.createElement("div");
          row.className = "poi-capture";
          const imageSrc = evidenceImageSrc(capture.image_path);
          if (imageSrc) {{
            const image = document.createElement("img");
            image.src = imageSrc;
            image.alt = `${{capture.id}} photo evidence`;
            row.appendChild(image);
          }}
          const detail = document.createElement("div");
          const title = appendText(detail, "strong", capture.id || "capture");
          title.style.display = "block";
          const tags = (capture.visible_tag_ids || []).length ? capture.visible_tag_ids.join(", ") : "none";
          appendText(detail, "span", `${{capture.zone_id || "unknown"}} / tags ${{tags}}`);
          row.appendChild(detail);
          item.appendChild(row);
          list.appendChild(item);
        }}
        for (const reading of (poi.readings || []).slice(0, 3)) {{
          const item = document.createElement("li");
          const label = reading.kind === "temperature"
            ? `${{reading.asset_id}} ${{reading.reading_celsius}}C <= ${{reading.max_celsius}}C`
            : `${{reading.asset_id}} ${{reading.state || "unknown"}}`;
          appendText(item, "strong", reading.kind || "reading");
          item.appendChild(document.createTextNode(` ${{label}}`));
          list.appendChild(item);
        }}
        poiEvidence.replaceChildren(list);
      }};
      const refreshPoiEvidence = async () => {{
        try {{
          const response = await fetch("/api/poi");
          if (!response.ok) return;
          renderPoiEvidence(await response.json());
        }} catch (_) {{
          // Keep the static evidence if the live refresh is unavailable.
        }}
      }};
      const refreshRouteExecution = async () => {{
        if (!robotControlToken) return;
        if (routeExecutionPolling) return;
        routeExecutionPolling = true;
        try {{
          const response = await fetch("/api/map/routes/status", {{
            cache: "no-store",
            headers: {{"X-DogOps-Control-Token": robotControlToken}},
          }});
          const result = await response.json();
          if (!response.ok || result.ok === false) {{
            throw new Error(result.message || result.error || "route_status_failed");
          }}
          const state = result.route_execution || {{}};
          setRouteExecutionStatus(routeExecutionText(state), state.state === "failed" ? "error" : "ok");
        }} catch (error) {{
          setRouteExecutionStatus(`Execution: status unavailable (${{error.message}})`, "error");
        }} finally {{
          routeExecutionPolling = false;
        }}
      }};
      const requestRerunReplay = async (action) => {{
        try {{
          const response = await fetch("/api/rerun/replay", {{
            method: "POST",
            headers: {{
              "Content-Type": "application/json",
              "X-DogOps-Control-Token": robotControlToken,
            }},
            body: JSON.stringify({{action}}),
          }});
          const result = await response.json();
          if (!response.ok || result.ok === false) {{
            throw new Error(result.message || result.error || "rerun_replay_failed");
          }}
          setMapCommandStatus("3D replay requested; waiting for simulation frames...", "ok");
          await new Promise((resolve) => window.setTimeout(resolve, Number(result.replay_after_ms || 850)));
          await connectRerunSurface({{replay: true}});
          setMapCommandStatus("3D replay started.", "ok");
          return true;
        }} catch (error) {{
          setMapCommandStatus(`3D replay failed: ${{error.message}}`, "error");
          return false;
        }}
      }};
      const mapFromScratch = async () => {{
        setMapCommandStatus("Mapping from scratch in simulation...", "ok");
        await requestRerunReplay("replay_mapping");
      }};
      const returnHome = async () => {{
        const route = selectedRoute();
        const home = route && Array.isArray(route.waypoints)
          ? route.waypoints.find((waypoint) => waypoint.target_id === "HOME" || waypoint.label === "HOME")
          : null;
        const target = (home && home.pose)
          || ((mapAuthoring && mapAuthoring.home) ? mapAuthoring.home : null)
          || mapHomePose;
        if (!target) {{
          setMapCommandStatus("Home target unavailable", "error");
          return;
        }}
        setMapCommandStatus("Return home target selected", "ok");
        await sendGoToTarget({{x: Number(target.x), y: Number(target.y), source: "return_home"}});
      }};
      const runSelectedRoute = async (dryRun = false) => {{
        const route = selectedRoute();
        if (!route) {{
          setRouteExecutionStatus("Execution: select or author POIs first", "error");
          return;
        }}
        setRouteExecutionStatus(`Execution: starting ${{route.id}}${{dryRun ? " simulation" : ""}}...`, "");
        await requestRerunReplay("replay_route");
        try {{
          const response = await fetch("/api/map/routes/follow", {{
            method: "POST",
            headers: {{
              "Content-Type": "application/json",
              "X-DogOps-Control-Token": robotControlToken,
            }},
            body: JSON.stringify({{route_id: route.id, dry_run: dryRun}}),
          }});
          const result = await response.json();
          const state = (result.mcp_result && result.mcp_result.route_execution) || result.route_execution || {{}};
          if (!response.ok || result.ok === false) {{
            throw new Error(result.message || result.error || "follow_route_failed");
          }}
          setRouteExecutionStatus(routeExecutionText(state), "ok");
          await refreshPoiEvidence();
        }} catch (error) {{
          setRouteExecutionStatus(`Execution failed: ${{error.message}}`, "error");
        }} finally {{
          await refreshRouteExecution();
        }}
      }};
      const stopRouteExecution = async () => {{
        setRouteExecutionStatus("Execution: stopping route...", "");
        try {{
          const response = await fetch("/api/map/routes/stop", {{
            method: "POST",
            headers: {{
              "Content-Type": "application/json",
              "X-DogOps-Control-Token": robotControlToken,
            }},
            body: JSON.stringify({{}}),
          }});
          const result = await response.json();
          if (!response.ok || result.ok === false) {{
            throw new Error(result.message || result.error || "stop_route_failed");
          }}
          setRouteExecutionStatus(routeExecutionText(result.route_execution || {{}}), "ok");
        }} catch (error) {{
          setRouteExecutionStatus(`Stop route failed: ${{error.message}}`, "error");
        }} finally {{
          await refreshRouteExecution();
        }}
      }};
      const routeIndexForTarget = (route, targetId) => {{
        if (!route || !Array.isArray(route.waypoints)) return -1;
        return route.waypoints.findIndex((waypoint) => waypoint.id === targetId || waypoint.target_id === targetId);
      }};
      const saveRoutes = async (routes, selectedRouteId = null) => {{
        const current = mapAuthoring || {{}};
        await postAuthoring("/api/map/authoring", {{
          ...current,
          routes,
          selected_route_id: selectedRouteId || current.selected_route_id || (routes[0] && routes[0].id) || null,
        }}, "PUT");
      }};
      const removeRouteWaypoint = async (targetId) => {{
        const current = mapAuthoring || {{}};
        const routes = Array.isArray(current.routes) ? [...current.routes] : [];
        const route = routes.find((item) => item.id === current.selected_route_id) || routes[0];
        const routeIndex = routes.indexOf(route);
        if (!route || routeIndex < 0) return;
        route.waypoints = (route.waypoints || []).filter((waypoint) => waypoint.id !== targetId && waypoint.target_id !== targetId);
        routes[routeIndex] = route;
        await saveRoutes(routes, route.id);
      }};
      const moveSelectedRouteWaypoint = async (direction) => {{
        if (!selectedMapObject || selectedMapObject.kind !== "route_stop") {{
          setMapAuthoringStatus("Select a route waypoint first", "error");
          return;
        }}
        const current = mapAuthoring || {{}};
        const routes = Array.isArray(current.routes) ? [...current.routes] : [];
        const route = routes.find((item) => item.id === current.selected_route_id) || routes[0];
        const routeIndex = routes.indexOf(route);
        const waypointIndex = routeIndex >= 0 ? routeIndexForTarget(route, selectedMapObject.id) : -1;
        const nextIndex = waypointIndex + direction;
        if (!route || waypointIndex < 0 || nextIndex < 0 || nextIndex >= route.waypoints.length) return;
        const waypoints = [...route.waypoints];
        [waypoints[waypointIndex], waypoints[nextIndex]] = [waypoints[nextIndex], waypoints[waypointIndex]];
        route.waypoints = waypoints;
        routes[routeIndex] = route;
        await saveRoutes(routes, route.id);
      }};
      const selectRouteByPrompt = async () => {{
        const current = mapAuthoring || {{}};
        const routes = Array.isArray(current.routes) ? current.routes : [];
        const routeId = window.prompt("Route id", current.selected_route_id || (routes[0] && routes[0].id) || "AUTHORED_ROUTE");
        if (!routeId) return;
        await postAuthoring(`/api/map/routes/${{encodeURIComponent(routeId)}}/select`, {{}});
      }};
      const mapEditId = (prefix) => `${{prefix}}-${{Date.now().toString(36)}}`;
      const applyMapEditAt = async (target) => {{
        const pose = authoringPoint(target);
        if (mapEditMode === "home") {{
          const current = mapAuthoring || {{}};
          await postAuthoring("/api/map/authoring", {{...current, home: pose}}, "PUT");
        }} else if (mapEditMode === "zone") {{
          const label = window.prompt("Label name", "CHECKPOINT");
          if (!label) return;
          await postAuthoring("/api/map/entities", {{
            id: label.trim().replace(/\\s+/g, "_").toUpperCase(),
            kind: "checkpoint",
            label,
            pose,
          }});
        }} else if (mapEditMode === "asset") {{
          const label = window.prompt("Asset id", "ASSET_1");
          if (!label) return;
          await postAuthoring("/api/map/entities", {{
            id: label.trim().replace(/\\s+/g, "_").toUpperCase(),
            kind: "asset",
            label,
            pose,
          }});
        }} else if (mapEditMode === "package") {{
          const label = window.prompt("Package id", "PKG-NEW");
          if (!label) return;
          await postAuthoring("/api/map/entities", {{
            id: label.trim().replace(/\\s+/g, "_").toUpperCase(),
            kind: "package",
            label,
            pose,
          }});
        }} else if (mapEditMode === "no_go") {{
          const size = 0.5;
          await postAuthoring("/api/map/no_go_shapes", {{
            id: mapEditId("NO_GO"),
            label: "Authored No-Go",
            shape: "rectangle",
            points: [
              {{...pose, x: pose.x - size, y: pose.y - size}},
              {{...pose, x: pose.x + size, y: pose.y + size}},
            ],
            enabled: true,
            dimos_constraint_status: "not_supported",
          }});
        }} else if (mapEditMode === "route") {{
          const current = mapAuthoring || {{}};
          const routes = Array.isArray(current.routes) ? [...current.routes] : [];
          const route = routes.find((item) => item.id === "AUTHORED_POI_ROUTE") || {{id: "AUTHORED_POI_ROUTE", label: "Authored photo POI route", waypoints: [], mission_id: null}};
          const routeIndex = routes.indexOf(route);
          const existingWaypoints = (route.waypoints || []).filter((waypoint) => waypoint.target_id !== "HOME");
          const poiCount = existingWaypoints.length + 1;
          route.waypoints = [...existingWaypoints, {{
            id: mapEditId("WP"),
            label: `Photo POI ${{poiCount}}`,
            pose,
            target_id: `PHOTO_POI_${{poiCount}}`,
            required: true,
          }}];
          const homePose = (mapAuthoring && mapAuthoring.home) || mapHomePose;
          if (homePose) {{
            route.waypoints.push({{
              id: "HOME-RETURN",
              label: "Return Home",
              pose: {{x: Number(homePose.x), y: Number(homePose.y), source: "site_config"}},
              target_id: "HOME",
              required: true,
            }});
          }}
          routes[routeIndex >= 0 ? routeIndex : 0] = route;
          await postAuthoring("/api/map/authoring", {{...current, routes, selected_route_id: route.id}}, "PUT");
        }} else if (mapEditMode === "incident") {{
          const incidentId = window.prompt("Incident id", "INC-001");
          if (!incidentId) return;
          await postAuthoring(`/api/map/incidents/${{encodeURIComponent(incidentId)}}/location`, {{
            pose,
            evidence_observation_ids: [],
          }});
        }} else if (mapEditMode === "tag") {{
          const tagId = Number(window.prompt("Tag id", "999"));
          const entityId = window.prompt("Entity id", "CHECKPOINT");
          if (!Number.isFinite(tagId) || !entityId) return;
          await postAuthoring("/api/map/tag_bindings", {{
            tag_id: tagId,
            entity_id: entityId.trim(),
            label: entityId.trim(),
            binding_kind: "checkpoint",
          }});
        }}
      }};
      const setLiveMapUnavailable = (text, keepRobot = false) => {{
        if (liveMapStatus) liveMapStatus.textContent = text;
        if (liveRobot && !keepRobot) liveRobot.style.display = "none";
      }};
      const heatColor = (cost) => {{
        if (cost >= 0.75) return "#dc2626";
        if (cost >= 0.5) return "#f97316";
        if (cost >= 0.28) return "#eab308";
        return "#22c55e";
      }};
      const renderLiveHeatmap = (costmap) => {{
        if (!liveHeatmap) return 0;
        liveHeatmap.textContent = "";
        const cells = costmap && Array.isArray(costmap.cells) ? costmap.cells : [];
        let rendered = 0;
        for (const cell of cells) {{
          const cost = Math.max(0, Math.min(1, Number(cell.cost || 0)));
          if (cost < 0.12) continue;
          const p1 = projectLiveOverlayPoint(Number(cell.x), Number(cell.y));
          const p2 = projectLiveOverlayPoint(Number(cell.x) + Number(cell.width || 0), Number(cell.y) + Number(cell.height || 0));
          if (!p1 || !p2) continue;
          const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
          rect.setAttribute("class", "map-live-cost-cell");
          rect.setAttribute("x", Math.min(p1.x, p2.x).toFixed(1));
          rect.setAttribute("y", Math.min(p1.y, p2.y).toFixed(1));
          rect.setAttribute("width", Math.abs(p2.x - p1.x).toFixed(1));
          rect.setAttribute("height", Math.abs(p2.y - p1.y).toFixed(1));
          rect.setAttribute("fill", heatColor(cost));
          rect.setAttribute("opacity", (0.18 + cost * 0.55).toFixed(2));
          liveHeatmap.appendChild(rect);
          rendered += 1;
        }}
        return rendered;
      }};
      const renderDimOSPath = (path) => {{
        if (!livePath) return 0;
        const points = Array.isArray(path) ? path : [];
        const projected = points
          .map((point) => projectLiveOverlayPoint(point.x, point.y))
          .filter(Boolean)
          .map((point) => `${{point.x.toFixed(1)}},${{point.y.toFixed(1)}}`);
        livePath.setAttribute("points", projected.join(" "));
        return projected.length;
      }};
      const renderDimOSTarget = (target) => {{
        if (!liveTarget) return;
        const projected = target ? projectLiveOverlayPoint(target.x, target.y) : null;
        if (!projected) {{
          liveTarget.style.display = "none";
          return;
        }}
        liveTarget.style.display = "";
        liveTarget.setAttribute(
          "transform",
          `translate(${{projected.x.toFixed(1)}} ${{projected.y.toFixed(1)}})`
        );
      }};
      const updateDimOSMapLayers = (data) => {{
        const live = data && data.live ? data.live : null;
        if (!live) return;
        if (data.bounds) liveOverlayBounds = data.bounds;
        const heatmapCells = renderLiveHeatmap(live.costmap);
        const pathPoints = renderDimOSPath(live.path || live.route || []);
        renderDimOSTarget(live.target);
        dimosRobotPoseActive = Boolean(live.robot_pose);
        if (live.robot_pose) {{
          const yawRad = Number.isFinite(live.robot_pose.theta_deg)
            ? live.robot_pose.theta_deg * Math.PI / 180
            : 0;
          updateLiveMap(
            {{ok: true, pose: {{x: live.robot_pose.x, y: live.robot_pose.y, yaw_rad: yawRad}}, trajectory: [], ts: Date.now() / 1000}},
            liveOverlayBounds
          );
        }}
        if (liveMapStatus) {{
          if (live.ok) {{
            liveMapStatus.textContent = `Live DimOS: heatmap=${{heatmapCells}} path=${{pathPoints}} source=${{live.source || "LCM topics"}}`;
          }} else if (!liveMapStatus.textContent.startsWith("Live odom: x=")) {{
            liveMapStatus.textContent = `Live DimOS: waiting for topics${{live.error ? ` (${{live.error}})` : ""}}`;
          }}
        }}
      }};
      const updateLiveMap = (data, bounds = liveMapBounds) => {{
        if (!liveMapSvg || !liveTrace || !liveRobot || !liveMapStatus) return;
        if (!data || !data.ok || !data.pose) {{
          if (dimosRobotPoseActive) return;
          const error = data && data.error ? data.error : "offline";
          setLiveMapUnavailable(`Live odom: ${{error}}`);
          return;
        }}
        const trajectory = Array.isArray(data.trajectory) ? data.trajectory : [];
        const points = trajectory
          .map((pose) => projectPoseWithBounds(pose, bounds))
          .filter(Boolean)
          .map((point) => `${{point.x.toFixed(1)}},${{point.y.toFixed(1)}}`);
        liveTrace.setAttribute("points", points.join(" "));
        const projected = projectPoseWithBounds(data.pose, bounds);
        if (!projected) {{
          if (!dimosRobotPoseActive) setLiveMapUnavailable("Live odom: map projection unavailable");
          return;
        }}
        const yawDeg = (data.pose.yaw_rad || 0) * 180 / Math.PI;
        liveRobot.style.display = "";
        liveRobot.setAttribute(
          "transform",
          `translate(${{projected.x.toFixed(1)}} ${{projected.y.toFixed(1)}}) rotate(${{(-yawDeg).toFixed(1)}})`
        );
        const ageS = Math.max(0, Date.now() / 1000 - (data.ts || 0));
        liveMapStatus.textContent = `Live odom: x=${{data.pose.x.toFixed(2)}}m y=${{data.pose.y.toFixed(2)}}m yaw=${{yawDeg.toFixed(0)}}deg age=${{ageS.toFixed(1)}}s`;
      }};
      const refreshLiveMap = async () => {{
        if (liveMapPolling || !liveMapSvg) return;
        liveMapPolling = true;
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 1500);
        try {{
          const response = await fetch("/api/robot/pose", {{
            cache: "no-store",
            signal: controller.signal,
          }});
          const result = await response.json();
          updateLiveMap(result);
        }} catch (error) {{
          if (!dimosRobotPoseActive) setLiveMapUnavailable(`Live odom: ${{error.message}}`);
        }} finally {{
          window.clearTimeout(timeout);
          liveMapPolling = false;
        }}
      }};
      const refreshDimOSMap = async () => {{
        if (dimosMapPolling || !liveMapSvg) return;
        dimosMapPolling = true;
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 1800);
        try {{
          const response = await fetch("/api/map", {{
            cache: "no-store",
            signal: controller.signal,
          }});
          const result = await response.json();
          updateDimOSMapLayers(result);
        }} catch (error) {{
          if (liveMapStatus && !liveMapStatus.textContent.startsWith("Live odom: x=")) {{
            liveMapStatus.textContent = `Live DimOS: ${{error.message}}`;
          }}
        }} finally {{
          window.clearTimeout(timeout);
          dimosMapPolling = false;
        }}
      }};
      const shouldIgnoreKeyboardEvent = (event) => {{
        if (event.defaultPrevented || event.repeat) return true;
        if (event.metaKey || event.ctrlKey || event.altKey) return true;
        const target = event.target;
        if (!target) return false;
        const tagName = target.tagName ? target.tagName.toLowerCase() : "";
        return (
          target.isContentEditable ||
          tagName === "input" ||
          tagName === "textarea" ||
          tagName === "select" ||
          tagName === "button"
        );
      }};
      const motionTextForCommand = (command) => (result) => {{
        if (command === "hard_stop") return "Hard stop sent";
        const profile = motionLabels[result.profile] || motionLabels[motionProfile] || motionProfile;
        if (!result.observed) return `Sent ${{profile}} ${{command}}`;
        const distanceCm = Math.round((result.observed_distance_m || 0) * 1000) / 10;
        const yawDeg = Math.round(Math.abs(result.observed_dyaw_rad || 0) * 1800 / Math.PI) / 10;
        if (distanceCm >= 0.5) return `Sent ${{profile}} ${{command}} / observed ${{distanceCm}} cm`;
        if (yawDeg >= 0.5) return `Sent ${{profile}} ${{command}} / observed ${{yawDeg}} deg`;
        return `Sent ${{profile}} ${{command}} / no clear odom movement`;
      }};
      const sendJogCommand = async (command, source = "button") => {{
        if (robotBusy && command !== "hard_stop") return;
        await sendRobotAction(
          "/api/robot/jog",
          {{command, profile: motionProfile, source}},
          motionTextForCommand(command)
        );
        await refreshLiveMap();
      }};
      const sendGoToTarget = async (target) => {{
        if (!target || robotBusy) return;
        setGoToMarker(target);
        setMapCommandStatus(`Sending Go To x=${{target.x.toFixed(2)}} y=${{target.y.toFixed(2)}}...`, "");
        const result = await sendRobotAction(
          "/api/robot/go_to",
          {{command: "go_to", x: target.x, y: target.y, source: target.source || "map_click"}},
          () => `Go To sent x=${{target.x.toFixed(2)}} y=${{target.y.toFixed(2)}}`
        );
        setMapCommandStatus(
          result ? `Go To sent x=${{target.x.toFixed(2)}} y=${{target.y.toFixed(2)}}` : "Go To failed",
          result ? "ok" : "error"
        );
        await refreshLiveMap();
      }};
      const sendRobotAction = async (url, body, successText) => {{
        robotBusy = true;
        setBusy(true);
        setStatus(`Sending ${{body.command}}...`, "");
        try {{
          const headers = {{"Content-Type": "application/json"}};
          if (robotControlToken) headers["X-DogOps-Control-Token"] = robotControlToken;
          const response = await fetch(url, {{
            method: "POST",
            headers,
            body: JSON.stringify(body),
          }});
          const result = await response.json();
          if (!response.ok || !result.ok) {{
            throw new Error(result.error || "command_failed");
          }}
          setStatus(successText(result), "ok");
          return result;
        }} catch (error) {{
          setStatus(`Robot command failed: ${{error.message}}`, "error");
          return null;
        }} finally {{
          robotBusy = false;
          setBusy(false);
        }}
      }};
      controls.addEventListener("click", async (event) => {{
        const button = event.target.closest("button[data-command]");
        if (!button) return;
        const command = button.getAttribute("data-command");
        button.blur();
        await sendJogCommand(command);
      }});
      if (rerunConnect) {{
        rerunConnect.addEventListener("click", () => {{
          connectRerunSurface();
        }});
      }}
      if (liveMapSvg) {{
        liveMapSvg.addEventListener("mousedown", (event) => {{
          if (mapEditMode !== "select") return;
          const item = selectMapObject(event.target);
          if (!item || !["zone", "asset", "package"].includes(item.kind)) return;
          dragMapObject = item;
        }});
        liveMapSvg.addEventListener("mouseup", async (event) => {{
          if (!dragMapObject) return;
          const item = dragMapObject;
          dragMapObject = null;
          const target = worldFromSvgEvent(event);
          if (!target) return;
          await postAuthoring(`/api/map/entities/${{encodeURIComponent(item.id)}}`, {{
            id: item.id,
            kind: item.kind,
            label: item.id,
            pose: authoringPoint(target),
          }}, "PUT");
        }});
        liveMapSvg.addEventListener("click", async (event) => {{
          if (mapEditMode !== "select") {{
            event.preventDefault();
            const target = worldFromSvgEvent(event);
            if (!target) {{
              setMapAuthoringStatus("Map edit target unavailable", "error");
              return;
            }}
            await applyMapEditAt(target);
            return;
          }}
          if (selectMapObject(event.target)) return;
          if (!goToArmed) return;
          event.preventDefault();
          const target = worldFromSvgEvent(event);
          setGoToArmed(false);
          if (!target) {{
            setMapCommandStatus("Go To target unavailable", "error");
            return;
          }}
          await sendGoToTarget(target);
        }});
      }}
      window.addEventListener("keydown", async (event) => {{
        if (shouldIgnoreKeyboardEvent(event)) return;
        const command = keyboardCommands.get(event.code);
        if (!command) return;
        event.preventDefault();
        await sendJogCommand(command, "keyboard");
      }});
      if (motionControls) {{
        motionControls.addEventListener("click", (event) => {{
          const button = event.target.closest("button[data-motion]");
          if (!button) return;
          motionProfile = button.getAttribute("data-motion") || "nudge";
          motionControls.querySelectorAll("[data-motion]").forEach((item) => {{
            item.setAttribute("aria-pressed", item === button ? "true" : "false");
          }});
          setStatus(`Motion: ${{motionLabels[motionProfile] || motionProfile}}`, "ok");
          button.blur();
        }});
      }}
      if (postureControls) {{
        postureControls.addEventListener("click", async (event) => {{
          const button = event.target.closest("button[data-posture]");
          if (!button) return;
          const command = button.getAttribute("data-posture");
          button.blur();
          await sendRobotAction(
            "/api/robot/posture",
            {{command}},
            () => command === "wake" ? "Wake / stand complete" : `Sent ${{command}}`
          );
          await refreshLiveMap();
        }});
      }}
      if (mapControls) {{
        mapControls.addEventListener("click", async (event) => {{
          const button = event.target.closest("button[data-map-action]");
          if (!button) return;
          const action = button.getAttribute("data-map-action");
          button.blur();
          if (action === "start") {{
            await sendRobotAction(
              "/api/robot/map_start",
              {{command: "map_start"}},
              () => "Live map connected"
            );
          }} else if (action === "origin") {{
            await sendRobotAction(
              "/api/robot/map_origin",
              {{command: "map_origin"}},
              () => "Map origin set"
            );
          }} else if (action === "arm_go_to") {{
            setGoToArmed(!goToArmed);
          }}
          await refreshLiveMap();
        }});
      }}
      if (mapEditControls) {{
        mapEditControls.addEventListener("click", async (event) => {{
          const modeButton = event.target.closest("button[data-map-edit-mode]");
          if (modeButton) {{
            setGoToArmed(false);
            setMapEditMode(modeButton.getAttribute("data-map-edit-mode") || "select");
            modeButton.blur();
            return;
          }}
          const actionButton = event.target.closest("button[data-map-edit-action]");
          if (!actionButton) return;
          const action = actionButton.getAttribute("data-map-edit-action");
          actionButton.blur();
          if (action === "save") {{
            const current = mapAuthoring || {{}};
            await postAuthoring("/api/map/authoring", current, "PUT");
          }} else if (action === "reset") {{
            if (!window.confirm("Remove all authored map edits for this run?")) return;
            await postAuthoring("/api/map/authoring", {{
              schema_version: 1,
              site_id: "",
              frame: "world",
              entities: [],
              no_go_shapes: [],
              routes: [],
              incident_locations: [],
              tag_bindings: [],
            }}, "PUT");
          }} else if (action === "export") {{
            const result = await postAuthoring("/api/map/export", {{}});
            if (result && result.exports) {{
              setMapAuthoringStatus("Map authoring exported to run exports directory", "ok");
            }}
          }} else if (action === "delete_selected") {{
            await deleteSelectedMapObject();
          }} else if (action === "use_observation") {{
            await placeSelectedFromObservation();
          }} else if (action === "route_select") {{
            await selectRouteByPrompt();
          }} else if (action === "map_from_scratch") {{
            await mapFromScratch();
          }} else if (action === "return_home") {{
            await returnHome();
          }} else if (action === "run_route_sim") {{
            await runSelectedRoute(true);
          }} else if (action === "run_route") {{
            await runSelectedRoute(false);
          }} else if (action === "stop_route") {{
            await stopRouteExecution();
          }} else if (action === "route_up") {{
            await moveSelectedRouteWaypoint(-1);
          }} else if (action === "route_down") {{
            await moveSelectedRouteWaypoint(1);
          }} else if (action === "publish_no_go") {{
            await postAuthoring("/api/map/no_go_shapes/publish", {{}});
          }}
        }});
      }}
      if (layerControls) {{
        layerControls.addEventListener("click", (event) => {{
          const button = event.target.closest("button[data-map-layer]");
          if (!button || !liveMapSvg) return;
          const layer = button.getAttribute("data-map-layer");
          const pressed = button.getAttribute("aria-pressed") !== "true";
          button.setAttribute("aria-pressed", pressed ? "true" : "false");
          liveMapSvg.querySelectorAll(`[data-layer="${{layer}}"]`).forEach((item) => {{
            item.toggleAttribute("hidden", !pressed);
          }});
        }});
      }}
      refreshLiveMap();
      refreshDimOSMap();
      refreshRouteExecution();
      window.setInterval(refreshLiveMap, 1000);
      window.setInterval(refreshDimOSMap, 1500);
      window.setInterval(refreshRouteExecution, 1500);
    }})();
  </script>
</body>
</html>
"""


class _MapProjector:
    def __init__(self, bounds: dict[str, float]) -> None:
        self.x_min = bounds["x_min"]
        self.x_max = bounds["x_max"]
        self.y_min = bounds["y_min"]
        self.y_max = bounds["y_max"]

    def x(self, value: float) -> float:
        span = max(0.1, self.x_max - self.x_min)
        return ((value - self.x_min) / span) * MAP_WIDTH

    def y(self, value: float) -> float:
        span = max(0.1, self.y_max - self.y_min)
        return MAP_HEIGHT - (((value - self.y_min) / span) * MAP_HEIGHT)

    def radius(self, value_m: float) -> float:
        span_x = max(0.1, self.x_max - self.x_min)
        span_y = max(0.1, self.y_max - self.y_min)
        px_per_m = min(MAP_WIDTH / span_x, MAP_HEIGHT / span_y)
        return max(22.0, value_m * px_per_m)

    def size(self, value_m: float) -> float:
        span_x = max(0.1, self.x_max - self.x_min)
        span_y = max(0.1, self.y_max - self.y_min)
        px_per_m = min(MAP_WIDTH / span_x, MAP_HEIGHT / span_y)
        return max(2.0, value_m * px_per_m)


def _zone_pose(zone: dict[str, Any]) -> tuple[float, float] | None:
    pose = zone.get("pose_hint") or {}
    try:
        return float(pose["x"]), float(pose["y"])
    except (KeyError, TypeError, ValueError):
        return None


def _offset_pose(base: tuple[float, float], index: int) -> tuple[float, float]:
    dx, dy = ENTITY_OFFSETS_M[index % len(ENTITY_OFFSETS_M)]
    return base[0] + dx, base[1] + dy


def _package_pose(base: tuple[float, float], index: int) -> tuple[float, float]:
    dx, dy = PACKAGE_OFFSETS_M[index % len(PACKAGE_OFFSETS_M)]
    return base[0] + dx, base[1] + dy


def _visible_tag_ids(observation: dict[str, Any]) -> list[int]:
    facts = observation.get("facts") or {}
    raw = facts.get("visible_tag_ids")
    if isinstance(raw, str):
        tag_ids = []
        for item in raw.split(","):
            item = item.strip()
            if item:
                try:
                    tag_ids.append(int(item))
                except ValueError:
                    continue
        return tag_ids
    if isinstance(raw, list):
        return [int(item) for item in raw if isinstance(item, int | str)]
    tag_id = observation.get("tag_id")
    return [int(tag_id)] if isinstance(tag_id, int) else []


def _trusted_rerun_web_url(raw_url: str | None) -> str:
    fallback = "http://127.0.0.1:9877"
    if not raw_url:
        return fallback
    try:
        parsed = urlparse(raw_url)
    except ValueError:
        return fallback
    if parsed.scheme not in {"http", "https"}:
        return fallback
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return fallback
    return raw_url


def _trusted_rerun_source_url(raw_url: str | None) -> str:
    fallback = "rerun+http://127.0.0.1:9877/proxy"
    if not raw_url or not raw_url.startswith("rerun+"):
        return fallback
    try:
        parsed = urlparse(raw_url.removeprefix("rerun+"))
    except ValueError:
        return fallback
    if parsed.scheme not in {"http", "https"}:
        return fallback
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return fallback
    return raw_url


def _route_execution_status_text(route_execution: dict[str, Any] | None) -> str:
    if not route_execution or not route_execution.get("state"):
        return "Execution: idle"
    reached = int(route_execution.get("waypoints_reached") or 0)
    total = int(route_execution.get("waypoints_total") or 0)
    transport = route_execution.get("transport")
    suffix = f" transport={transport}" if transport else ""
    return f"Execution: {route_execution['state']} {reached}/{total}{suffix}"


def _with_default_route_authoring(
    authoring: dict[str, Any],
    state: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    if authoring.get("routes"):
        return authoring
    route_data = build_route_data(state, report, authoring=authoring)
    waypoints = []
    for index, stop in enumerate(route_data.get("stops") or [], 1):
        try:
            x = float(stop["x"])
            y = float(stop["y"])
        except (KeyError, TypeError, ValueError):
            continue
        target_id = str(stop.get("target_id") or f"POI_{index}")
        waypoints.append(
            {
                "id": f"POI-{index}",
                "label": f"Photo POI {index}: {target_id}",
                "target_id": target_id,
                "pose": {"x": x, "y": y, "source": "site_config"},
            }
        )
    if not waypoints:
        return authoring
    updated = dict(authoring)
    updated["routes"] = [
        {
            "id": "DOGOPS_PHOTO_POI_ROUTE",
            "label": "DogOps photo POI route",
            "mission_id": str(state.get("mission_id") or report.get("mission_id") or ""),
            "waypoints": waypoints,
        }
    ]
    updated["selected_route_id"] = "DOGOPS_PHOTO_POI_ROUTE"
    return updated


def _render_rerun_surface(rerun_source_url: str, rerun_web_url: str) -> str:
    rerun_source_url_attr = escape(rerun_source_url, quote=True)
    rerun_web_url_attr = escape(rerun_web_url, quote=True)
    return (
        '<div class="rerun-surface" data-rerun-surface data-map-viewer '
        f'data-rerun-source-url="{rerun_source_url_attr}" '
        'data-rerun-asset-base-url="/assets/vendor/@rerun-io/web-viewer/" '
        'data-rerun-view-mode="dogops-2d">'
        '<div class="rerun-canvas" data-rerun-canvas hidden></div>'
        '<div class="rerun-offline" data-viewer-offline hidden>'
        '<div>3D View unavailable. Start the Rerun stream, then connect again.</div>'
        "</div>"
        '<div class="rerun-standby" data-rerun-standby>'
        '<span class="rerun-chip">3D View</span>'
        '<div class="rerun-status" data-rerun-status>3D View standby</div>'
        '<div class="rerun-controls">'
        '<button type="button" data-rerun-connect>Connect 3D View</button>'
        f'<a href="{rerun_web_url_attr}" target="_blank" rel="noreferrer">Open</a>'
        "</div>"
        "</div>"
        "</div>"
    )


def _map_bounds(points: list[tuple[float, float]]) -> dict[str, float]:
    if not points:
        return {"x_min": -1.0, "x_max": 1.0, "y_min": -1.0, "y_max": 1.0}
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_min = min(xs) - MAP_PADDING_M
    x_max = max(xs) + MAP_PADDING_M
    y_min = min(ys) - MAP_PADDING_M
    y_max = max(ys) + MAP_PADDING_M
    if math.isclose(x_min, x_max):
        x_min -= 1.0
        x_max += 1.0
    if math.isclose(y_min, y_max):
        y_min -= 1.0
        y_max += 1.0
    return {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max}


def _render_floor_cells(projector: _MapProjector, map_data: dict[str, Any]) -> str:
    free_cells: set[tuple[int, int]] = set()
    cost_cells: set[tuple[int, int]] = set()
    route_positions = [(float(point["x"]), float(point["y"])) for point in map_data["route"]]

    for x, y in _route_samples(route_positions):
        _add_cells(free_cells, x, y, radius_m=0.38)

    for zone in map_data["zones"]:
        x = float(zone["x"])
        y = float(zone["y"])
        if zone.get("no_go"):
            _add_cells(cost_cells, x, y, radius_m=float(zone.get("radius_m") or 0.8))
        else:
            _add_cells(free_cells, x, y, radius_m=0.42)

    for item in [*map_data["assets"], *map_data["packages"], *map_data["observations"]]:
        _add_cells(free_cells, float(item["x"]), float(item["y"]), radius_m=0.24)

    free_cells -= cost_cells
    free_markup = "".join(_render_cell(projector, cell, "map-free-cell") for cell in sorted(free_cells))
    cost_markup = "".join(_render_cell(projector, cell, "map-cost-cell") for cell in sorted(cost_cells))
    return free_markup + cost_markup


def _render_point_cloud(projector: _MapProjector, map_data: dict[str, Any]) -> str:
    points: list[tuple[float, float, bool]] = []
    for index, observation in enumerate(map_data["observations"]):
        x = float(observation["x"])
        y = float(observation["y"])
        visible_tags = observation.get("visible_tag_ids") or []
        count = max(4, len(visible_tags) * 3)
        for point_index in range(count):
            angle = (index * 0.91) + (point_index * 2.399)
            radius = 0.05 + ((point_index % 5) * 0.035)
            points.append(
                (
                    x + math.cos(angle) * radius,
                    y + math.sin(angle) * radius,
                    bool(visible_tags),
                )
            )

    for package in map_data["packages"]:
        x = float(package["x"])
        y = float(package["y"])
        points.extend(
            [
                (x - 0.035, y - 0.025, True),
                (x + 0.038, y - 0.015, True),
                (x + 0.004, y + 0.041, True),
            ]
        )

    markup = []
    for x, y, hot in points:
        css_class = "map-point hot" if hot else "map-point"
        markup.append(
            f'<circle class="{css_class}" cx="{projector.x(x):.1f}" '
            f'cy="{projector.y(y):.1f}" r="2.1" />'
        )
    return "".join(markup)


def _route_samples(route_positions: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not route_positions:
        return []
    samples = [route_positions[0]]
    for start, end in pairwise(route_positions):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.hypot(dx, dy)
        steps = max(1, int(distance / MAP_CELL_M))
        for step in range(1, steps + 1):
            ratio = step / steps
            samples.append((start[0] + dx * ratio, start[1] + dy * ratio))
    return samples


def _add_cells(cells: set[tuple[int, int]], x: float, y: float, *, radius_m: float) -> None:
    radius_cells = max(1, math.ceil(radius_m / MAP_CELL_M))
    center_x = round(x / MAP_CELL_M)
    center_y = round(y / MAP_CELL_M)
    for dx in range(-radius_cells, radius_cells + 1):
        for dy in range(-radius_cells, radius_cells + 1):
            cell_x = center_x + dx
            cell_y = center_y + dy
            world_x = cell_x * MAP_CELL_M
            world_y = cell_y * MAP_CELL_M
            if math.hypot(world_x - x, world_y - y) <= radius_m:
                cells.add((cell_x, cell_y))


def _render_cell(projector: _MapProjector, cell: tuple[int, int], css_class: str) -> str:
    world_x = cell[0] * MAP_CELL_M
    world_y = cell[1] * MAP_CELL_M
    size = projector.size(MAP_CELL_M) * 0.9
    x = projector.x(world_x) - size / 2
    y = projector.y(world_y) - size / 2
    return f'<rect class="{css_class}" x="{x:.1f}" y="{y:.1f}" width="{size:.1f}" height="{size:.1f}" />'


def _render_grid(projector: _MapProjector) -> str:
    x_start = math.floor(projector.x_min * 2) / 2
    x_stop = math.ceil(projector.x_max * 2) / 2
    y_start = math.floor(projector.y_min * 2) / 2
    y_stop = math.ceil(projector.y_max * 2) / 2
    lines = []
    x_value = x_start
    while x_value <= x_stop + 0.001:
        x = projector.x(float(x_value))
        is_major = math.isclose(x_value % 1.0, 0.0, abs_tol=0.001)
        css_class = "map-grid-major" if is_major else "map-grid"
        lines.append(
            f'<line class="{css_class}" x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{MAP_HEIGHT}" />'
        )
        if is_major:
            label = round(x_value)
            lines.append(
                f'<text class="map-axis-label" x="{x + 4:.1f}" y="{MAP_HEIGHT - 8}">{label}m</text>'
            )
        x_value += 0.5

    y_value = y_start
    while y_value <= y_stop + 0.001:
        y = projector.y(float(y_value))
        is_major = math.isclose(y_value % 1.0, 0.0, abs_tol=0.001)
        css_class = "map-grid-major" if is_major else "map-grid"
        lines.append(
            f'<line class="{css_class}" x1="0" y1="{y:.1f}" x2="{MAP_WIDTH}" y2="{y:.1f}" />'
        )
        if is_major:
            label = round(y_value)
            lines.append(f'<text class="map-axis-label" x="8" y="{y - 4:.1f}">{label}m</text>')
        y_value += 0.5
    return "".join(lines)


def _render_no_go_zone(projector: _MapProjector, zone: dict[str, Any]) -> str:
    if not zone.get("no_go"):
        return ""
    x = projector.x(float(zone["x"]))
    y = projector.y(float(zone["y"]))
    radius = projector.size(float(zone.get("radius_m") or 0.8))
    width = radius * 1.55
    height = radius * 1.25
    title = escape(str(zone.get("display_name") or zone["id"]))
    return (
        f'<g data-edit-kind="zone" data-edit-id="{escape(str(zone["id"]))}"><title>{title}</title>'
        f'<rect class="map-no-go" x="{x - width / 2:.1f}" y="{y - height / 2:.1f}" '
        f'width="{width:.1f}" height="{height:.1f}" rx="4" />'
        f'<rect class="map-no-go-hatch" x="{x - width / 2:.1f}" y="{y - height / 2:.1f}" '
        f'width="{width:.1f}" height="{height:.1f}" rx="4" />'
        "</g>"
    )


def _render_no_go_shape(projector: _MapProjector, shape: dict[str, Any]) -> str:
    if not isinstance(shape, dict) or not shape.get("enabled", True):
        return ""
    points = [_authoring_pose(point) for point in shape.get("points") or []]
    points = [point for point in points if point is not None]
    if len(points) < 2:
        return ""
    title = escape(
        f"{shape.get('label') or shape.get('id') or 'No-go shape'} / "
        f"{shape.get('dimos_constraint_status') or 'not_supported'}"
    )
    if shape.get("shape") == "rectangle":
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        x1 = projector.x(min(xs))
        x2 = projector.x(max(xs))
        y1 = projector.y(max(ys))
        y2 = projector.y(min(ys))
        x = min(x1, x2)
        y = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        return (
            f'<g data-edit-kind="no_go_shape" data-edit-id="{escape(str(shape.get("id") or ""))}" '
            f'data-authored-no-go="{escape(str(shape.get("id") or ""))}"><title>{title}</title>'
            f'<rect class="map-no-go" x="{x:.1f}" y="{y:.1f}" '
            f'width="{width:.1f}" height="{height:.1f}" rx="4" />'
            f'<rect class="map-no-go-hatch" x="{x:.1f}" y="{y:.1f}" '
            f'width="{width:.1f}" height="{height:.1f}" rx="4" />'
            "</g>"
        )
    svg_points = " ".join(
        f"{projector.x(point[0]):.1f},{projector.y(point[1]):.1f}" for point in points
    )
    return (
        f'<g data-edit-kind="no_go_shape" data-edit-id="{escape(str(shape.get("id") or ""))}" '
        f'data-authored-no-go="{escape(str(shape.get("id") or ""))}"><title>{title}</title>'
        f'<polygon class="map-no-go" points="{svg_points}" />'
        f'<polygon class="map-no-go-hatch" points="{svg_points}" />'
        "</g>"
    )


def _render_zone(projector: _MapProjector, zone: dict[str, Any]) -> str:
    x = projector.x(float(zone["x"]))
    y = projector.y(float(zone["y"]))
    label = escape(str(zone["id"]))
    title = escape(str(zone.get("display_name") or zone["id"]))
    return (
        f'<g data-edit-kind="zone" data-edit-id="{escape(str(zone["id"]))}"><title>{title}</title>'
        f'<line class="map-zone-anchor" x1="{x - 8:.1f}" y1="{y:.1f}" x2="{x + 8:.1f}" y2="{y:.1f}" />'
        f'<line class="map-zone-anchor" x1="{x:.1f}" y1="{y - 8:.1f}" x2="{x:.1f}" y2="{y + 8:.1f}" />'
        f'<circle class="map-zone-anchor" cx="{x:.1f}" cy="{y:.1f}" r="4.5" />'
        f'<text class="map-zone-label" x="{x:.1f}" y="{y + 19:.1f}">{label}</text>'
        "</g>"
    )


def _render_asset(projector: _MapProjector, asset: dict[str, Any]) -> str:
    x = projector.x(float(asset["x"]))
    y = projector.y(float(asset["y"]))
    label = escape(str(asset["id"]))
    title = escape(str(asset.get("display_name") or asset["id"]))
    return (
        f'<g data-edit-kind="asset" data-edit-id="{escape(str(asset["id"]))}"><title>{title}</title>'
        f'<rect class="map-asset" x="{x - 7:.1f}" y="{y - 7:.1f}" width="14" height="14" rx="2" />'
        f'<rect class="map-tag-face" x="{x - 3:.1f}" y="{y - 3:.1f}" width="6" height="6" />'
        f'<text class="map-asset-label" x="{x + 10:.1f}" y="{y + 4:.1f}">{label}</text>'
        "</g>"
    )


def _render_package(projector: _MapProjector, package: dict[str, Any]) -> str:
    x = projector.x(float(package["x"]))
    y = projector.y(float(package["y"]))
    state = str(package.get("state") or "unknown")
    label = escape(str(package["id"]))
    title = escape(f"{package['id']} / {state}")
    return (
        f'<g data-edit-kind="package" data-edit-id="{escape(str(package["id"]))}"><title>{title}</title>'
        f'<rect class="map-package state-{escape(state)}" x="{x - 7:.1f}" y="{y - 7:.1f}" '
        f'width="14" height="14" rx="2" transform="rotate(45 {x:.1f} {y:.1f})" />'
        f'<text class="map-package-label" x="{x + 11:.1f}" y="{y + 4:.1f}">{label}</text>'
        "</g>"
    )


def _render_observation(projector: _MapProjector, observation: dict[str, Any]) -> str:
    zone_x = projector.x(float(observation["x"]))
    zone_y = projector.y(float(observation["y"]))
    label = escape(str(observation["id"]))
    title = escape(
        f"{observation.get('id')} tags {','.join(str(tag) for tag in observation['visible_tag_ids'])}"
    )
    return (
        f'<g data-edit-kind="observation" data-edit-id="{escape(str(observation["id"]))}"><title>{title}</title>'
        f'<circle class="map-observation" cx="{zone_x:.1f}" cy="{zone_y:.1f}" r="5.5" />'
        f'<text class="map-asset-label" x="{zone_x + 8:.1f}" y="{zone_y - 7:.1f}">{label}</text>'
        "</g>"
    )


def _render_incident(projector: _MapProjector, incident: dict[str, Any]) -> str:
    x = projector.x(float(incident["x"]))
    y = projector.y(float(incident["y"]))
    label = escape(str(incident["id"]))
    title = escape(
        f"{incident.get('id')} {incident.get('severity')} {incident.get('state')}"
    )
    return (
        f'<g data-edit-kind="incident" data-edit-id="{escape(str(incident["id"]))}"><title>{title}</title>'
        f'<circle class="map-incident" cx="{x:.1f}" cy="{y:.1f}" r="15" />'
        f'<text class="map-incident-label" x="{x + 14:.1f}" y="{y - 13:.1f}">{label}</text>'
        "</g>"
    )


def _render_route_stop(projector: _MapProjector, stop: dict[str, Any], index: int) -> str:
    x = projector.x(float(stop["x"]))
    y = projector.y(float(stop["y"]))
    title = escape(str(stop.get("target_id") or "route stop"))
    return (
        f'<g data-edit-kind="route_stop" data-edit-id="{escape(str(stop.get("target_id") or ""))}"><title>{title}</title>'
        f'<circle class="map-route-stop" cx="{x:.1f}" cy="{y:.1f}" r="9" />'
        f'<text class="map-route-index" x="{x:.1f}" y="{y + 1:.1f}">{index}</text>'
        "</g>"
    )


def _render_live_robot_pose() -> str:
    return (
        '<polyline class="map-live-trace" data-live-trace points="" />'
        '<g data-live-robot style="display:none" transform="translate(0 0)">'
        "<title>Live Go2 odometry pose</title>"
        '<circle class="map-live-robot-halo" cx="0" cy="0" r="18" />'
        '<path class="map-live-robot-core" d="M 14 0 L -9 -8 L -5 0 L -9 8 Z" />'
        "</g>"
        '<g data-live-target style="display:none" transform="translate(0 0)">'
        "<title>DimOS planner target</title>"
        '<circle class="map-dimos-target-ring" cx="0" cy="0" r="14" />'
        '<circle class="map-dimos-target-core" cx="0" cy="0" r="4" />'
        "</g>"
        '<g data-go-to-marker style="display:none" transform="translate(0 0)">'
        "<title>DimOS go_to target</title>"
        '<circle class="map-go-to-ring" cx="0" cy="0" r="13" />'
        '<line class="map-go-to-cross" x1="-17" y1="0" x2="-6" y2="0" />'
        '<line class="map-go-to-cross" x1="6" y1="0" x2="17" y2="0" />'
        '<line class="map-go-to-cross" x1="0" y1="-17" x2="0" y2="-6" />'
        '<line class="map-go-to-cross" x1="0" y1="6" x2="0" y2="17" />'
        "</g>"
    )


def _render_scan_item(observation: dict[str, Any]) -> str:
    tag_ids = ", ".join(str(tag_id) for tag_id in observation["visible_tag_ids"]) or "none"
    return (
        "<li>"
        f"<strong>{escape(str(observation['id']))}</strong> "
        f"{escape(str(observation['zone_id']))} / tags {escape(tag_ids)}"
        "</li>"
    )


def metric(label: str, value: object) -> str:
    return (
        '<div class="metric">'
        f"<span class=\"muted\">{escape(label)}</span>"
        f"<strong>{escape(str(value))}</strong>"
        "</div>"
    )


def build_test_flow_proof(
    state: dict[str, Any],
    report: dict[str, Any],
    route_data: dict[str, Any],
    poi_data: dict[str, Any],
    *,
    route_execution: dict[str, Any] | None = None,
    rerun_command: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    nav = report.get("nav_summary") or {}
    events = route_execution.get("events") if isinstance(route_execution, dict) else []
    reached_targets = [
        str(event.get("target_id"))
        for event in events or []
        if event.get("state") == "reached" and event.get("target_id")
    ]
    captures = poi_data.get("captures") or []
    photo_captures = [
        capture
        for capture in captures
        if str(capture.get("id") or "").startswith("OBS-POI-")
        and str(capture.get("image_path") or "")
    ]
    photo_targets = {
        str(capture.get("entity_id") or capture.get("zone_id") or "")
        for capture in photo_captures
    }
    route_targets = [str(stop.get("target_id")) for stop in route_data.get("stops") or []]
    poi_targets = [target for target in route_targets if target.startswith("PHOTO_POI_")]
    home_reached = "HOME" in reached_targets or any(
        str(event.get("target_id")) == "HOME"
        and "dashboard simulation go_to" in str(event.get("note") or "")
        for event in state.get("nav_events") or []
    )
    route_complete = (
        isinstance(route_execution, dict)
        and route_execution.get("state") == "completed"
        and int(route_execution.get("waypoints_reached") or 0)
        == int(route_execution.get("waypoints_total") or 0)
        and int(route_execution.get("waypoints_total") or 0) > 0
    )
    safety_clear = (
        route_complete
        and route_execution.get("last_error") in {None, ""}
        and int(nav.get("safety_stops") or 0) == 0
    )
    rerun_actions = [
        str(item)
        for item in (rerun_command or {}).get("history", [])
        if isinstance(item, str)
    ]
    current_rerun_action = (rerun_command or {}).get("action")
    if isinstance(current_rerun_action, str):
        rerun_actions.append(current_rerun_action)
    return [
        {
            "label": "Map area from scratch",
            "ok": "replay_mapping" in rerun_actions,
            "detail": f"3D View replay actions: {', '.join(rerun_actions) or 'not run'}",
        },
        {
            "label": "Return home",
            "ok": home_reached,
            "detail": "HOME reached by return-home command or final route stop",
        },
        {
            "label": "Avoid obstacles",
            "ok": safety_clear,
            "detail": (
                f"safety_stops={int(nav.get('safety_stops') or 0)}, "
                f"last_error={route_execution.get('last_error') if isinstance(route_execution, dict) else 'none'}"
            ),
        },
        {
            "label": "Select POIs on lower map",
            "ok": len(poi_targets) > 0,
            "detail": f"{len(poi_targets)} photo POI target(s): {', '.join(poi_targets) or 'none'}",
        },
        {
            "label": "Visit POIs",
            "ok": bool(poi_targets) and set(poi_targets).issubset(set(reached_targets)),
            "detail": f"reached: {', '.join(reached_targets) or 'none'}",
        },
        {
            "label": "Capture POI images",
            "ok": bool(poi_targets) and set(poi_targets).issubset(photo_targets),
            "detail": f"{len(photo_captures)} image evidence item(s)",
        },
        {
            "label": "Return home after POIs",
            "ok": bool(reached_targets) and reached_targets[-1] == "HOME",
            "detail": f"final reached target: {reached_targets[-1] if reached_targets else 'none'}",
        },
    ]


def test_flow_proof(items: list[dict[str, Any]]) -> str:
    rows = []
    for item in items:
        ok = bool(item.get("ok"))
        state = "pass" if ok else "fail"
        rows.append(
            '<div class="proof-item">'
            f"<strong>{escape(str(item.get('label') or 'Proof'))}</strong>"
            f'<span class="state-{state}">{state}</span>'
            f'<div class="muted">{escape(str(item.get("detail") or ""))}</div>'
            "</div>"
        )
    return '<div class="proof-grid">' + "".join(rows) + "</div>"


def package_table(packages: list[dict[str, Any]]) -> str:
    rows = []
    for package in packages:
        state = str(package["state"])
        rows.append(
            "<tr>"
            f"<td>{escape(str(package['package_id']))}</td>"
            f"<td>{escape(str(package['expected_zone_id']))}</td>"
            f"<td>{escape(str(package.get('observed_zone_id') or 'not observed'))}</td>"
            f"<td class=\"state-{escape(state)}\">{escape(state)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Package</th><th>Expected</th><th>Observed</th>"
        "<th>State</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def incident_table(incidents: list[dict[str, Any]]) -> str:
    rows = []
    for incident in incidents:
        severity = str(incident["severity"])
        state = str(incident["state"])
        rows.append(
            "<tr>"
            f"<td>{escape(str(incident['id']))}</td>"
            f"<td class=\"severity-{escape(severity)}\">{escape(severity)}</td>"
            f"<td>{escape(str(incident['title']))}</td>"
            f"<td class=\"state-{escape(state)}\">{escape(state)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>ID</th><th>Severity</th><th>Title</th><th>State</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def work_order_table(work_orders: list[dict[str, Any]]) -> str:
    rows = []
    for work_order in work_orders:
        state = str(work_order["state"])
        rows.append(
            "<tr>"
            f"<td>{escape(str(work_order['id']))}</td>"
            f"<td>{escape(str(work_order['incident_id']))}</td>"
            f"<td>{escape(str(work_order['assignee']))}</td>"
            f"<td class=\"state-{escape(state)}\">{escape(state)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>ID</th><th>Incident</th><th>Assignee</th><th>State</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def checkpoint_table(checkpoints: list[dict[str, Any]]) -> str:
    rows = []
    for checkpoint in checkpoints:
        verified = bool(checkpoint.get("verified"))
        state = "verified" if verified else "missing"
        tag_id = checkpoint.get("expected_tag_id")
        observation_id = checkpoint.get("observation_id") or "not observed"
        rows.append(
            "<tr>"
            f"<td>{escape(str(checkpoint['target_id']))}</td>"
            f"<td>{escape(str(tag_id if tag_id is not None else 'none'))}</td>"
            f"<td>{escape(str(observation_id))}</td>"
            f"<td class=\"state-{state}\">{state}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Target</th><th>Tag</th><th>Observation</th><th>State</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def route_table(stops: list[dict[str, Any]], poi_data: dict[str, Any] | None = None) -> str:
    captured_targets = {
        str(capture.get("entity_id") or capture.get("zone_id") or "")
        for capture in (poi_data or {}).get("captures", [])
        if str(capture.get("image_path") or "")
    }
    rows = []
    for stop in stops:
        target_id = str(stop["target_id"])
        if target_id in captured_targets and target_id == "HOME":
            state = "returned"
        elif target_id in captured_targets:
            state = "captured"
        else:
            state = "verified" if stop.get("tag_verified") else "missing"
        tag_id = stop.get("expected_tag_id")
        rows.append(
            "<tr>"
            f"<td>{escape(str(stop['sequence']))}</td>"
            f"<td>{escape(target_id)}</td>"
            f"<td>{escape(str(tag_id if tag_id is not None else 'none'))}</td>"
            f"<td>{escape(str(stop.get('retries', 0)))}</td>"
            f"<td class=\"state-{state}\">{state}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>#</th><th>Target</th><th>Tag</th><th>Retries</th>"
        "<th>State</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def poi_list(poi_data: dict[str, Any]) -> str:
    captures = poi_data.get("captures") or []
    readings = poi_data.get("readings") or []
    items = []
    image_captures = [capture for capture in captures if capture.get("image_path")]
    text_captures = [capture for capture in captures if not capture.get("image_path")]
    for capture in [*image_captures, *text_captures][:8]:
        tags = ", ".join(str(tag_id) for tag_id in capture.get("visible_tag_ids") or []) or "none"
        incidents = capture.get("related_incident_ids") or []
        incident_text = f" / incidents {', '.join(incidents)}" if incidents else ""
        image_path = str(capture.get("image_path") or "").lstrip("/")
        image = (
            f'<img src="/{escape(image_path, quote=True)}" '
            f'alt="{escape(str(capture["id"]), quote=True)} photo evidence">'
            if image_path
            else ""
        )
        items.append(
            "<li>"
            '<div class="poi-capture">'
            f"{image}"
            "<div>"
            f"<strong>{escape(str(capture['id']))}</strong> "
            f"<span>{escape(str(capture.get('zone_id') or 'unknown'))} / tags {escape(tags)}"
            f"{escape(incident_text)}</span>"
            "</div></div>"
            "</li>"
        )
    for reading in readings[:3]:
        if reading.get("kind") == "temperature":
            label = (
                f"{reading['asset_id']} {reading['reading_celsius']}C "
                f"<= {reading['max_celsius']}C"
            )
        else:
            label = f"{reading['asset_id']} {reading.get('state', 'unknown')}"
        items.append(f"<li><strong>{escape(str(reading['kind']))}</strong> {escape(label)}</li>")
    return '<ul class="compact-list">' + "".join(items) + "</ul>"


def write_dashboard_html(run_dir: str | Path, *, robot_control_token: str | None = None) -> Path:
    root = Path(run_dir)
    state = _read_json(root / "state.json")
    report = _read_json(root / "report.json")
    route_execution = _read_json_if_exists(root / "route_execution.json")
    rerun_command = _read_json_if_exists(root / "rerun_command.json")
    authoring = load_map_authoring(
        root,
        site_id=str((state.get("site") or {}).get("site_id") or ""),
    ).model_dump(mode="json")
    authoring = _with_default_route_authoring(authoring, state, report)
    html_path = root / "dashboard.html"
    html_path.write_text(
        render_dashboard_html(
            state,
            report,
            robot_control_token=robot_control_token,
            authoring=authoring,
            route_execution=route_execution,
            rerun_command=rerun_command,
        ),
        encoding="utf-8",
    )
    return html_path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)


def _latest_fact_value(observations: list[dict[str, Any]], key: str) -> object | None:
    for observation in reversed(observations):
        facts = observation.get("facts") or {}
        if key in facts:
            return facts[key]
    return None


def _to_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _to_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "clear"}:
            return True
        if normalized in {"false", "no", "0", "blocked"}:
            return False
    return None
