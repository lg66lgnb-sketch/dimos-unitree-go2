from __future__ import annotations

from dimos.experimental.dogops.models import (
    DogOpsState,
    IncidentState,
    IncidentType,
    PackageState,
    WorkOrderState,
)
from dimos.experimental.dogops.mapping import map_summary


def _value(value: object) -> object:
    return getattr(value, "value", value)


def build_report_data(state: DogOpsState) -> dict[str, object]:
    package_statuses = list(state.package_statuses.values())
    current_exception_package_ids = {
        status.package_id
        for status in package_statuses
        if status.state
        in {PackageState.missing, PackageState.wrong_zone, PackageState.blocking_asset}
    }
    incident_exception_package_ids = {
        incident.related_package_id
        for incident in state.incidents
        if incident.related_package_id is not None
        and incident.type
        in {
            IncidentType.blocked_cooling,
            IncidentType.wrong_zone,
            IncidentType.missing_package,
            IncidentType.damaged_package,
        }
    }
    manifest_exception_package_ids = current_exception_package_ids | incident_exception_package_ids
    verified_work_orders = [
        work_order
        for work_order in state.work_orders
        if work_order.state == WorkOrderState.verified_closed
    ]
    open_incidents = [
        incident for incident in state.incidents if incident.state != IncidentState.resolved
    ]
    resolved_incidents = [
        incident for incident in state.incidents if incident.state == IncidentState.resolved
    ]
    nav = state.nav_summary
    return {
        "run_id": state.run.id,
        "mission_id": state.run.mission_id,
        "mission_state": _value(state.run.state),
        "summary": state.run.summary,
        "packages_expected": len(package_statuses),
        "packages_observed": len(
            [status for status in package_statuses if status.observed_zone_id is not None]
        ),
        "manifest_exceptions": len(manifest_exception_package_ids),
        "incidents_opened": len(state.incidents),
        "incidents_resolved": len(resolved_incidents),
        "work_orders_verified_closed": len(verified_work_orders),
        "open_issues": [
            {
                "incident_id": incident.id,
                "type": _value(incident.type),
                "entity_id": incident.entity_id,
                "related_package_id": incident.related_package_id,
                "state": _value(incident.state),
            }
            for incident in open_incidents
        ],
        "what_changed": state.what_changed,
        "map": map_summary(state.site_map),
        "route_plan": state.route_plan.model_dump(mode="json"),
        "poi_captures": [
            capture.model_dump(mode="json") for capture in state.poi_captures
        ],
        "sensor_readings": [
            reading.model_dump(mode="json") for reading in state.sensor_readings
        ],
        "nav_summary": nav.model_dump(mode="json") if nav else None,
        "packages": [status.model_dump(mode="json") for status in package_statuses],
        "incidents": [incident.model_dump(mode="json") for incident in state.incidents],
        "work_orders": [
            work_order.model_dump(mode="json") for work_order in state.work_orders
        ],
    }


def render_report_markdown(state: DogOpsState) -> str:
    data = build_report_data(state)
    nav = state.nav_summary
    lines = [
        "DOGOPS RUN REPORT",
        f"Mission: {state.run.mission_id}",
        (
            "Packages scanned: "
            f"{data['packages_observed']} observed / {data['packages_expected']} expected"
        ),
        f"Manifest exceptions: {data['manifest_exceptions']}",
        f"Incidents opened: {data['incidents_opened']}",
        f"Work orders verified closed: {data['work_orders_verified_closed']}",
    ]

    open_issues = data["open_issues"]
    if open_issues:
        issue_text = ", ".join(
            f"{issue['related_package_id'] or issue['entity_id']} {issue['type']}"
            for issue in open_issues  # type: ignore[union-attr]
        )
        lines.append(f"Open issue: {issue_text}")
    else:
        lines.append("Open issue: none")

    if nav:
        lines.append(
            "Nav: "
            f"{nav.waypoints_reached}/{nav.waypoints_total} waypoints reached, "
            f"{nav.tag_reacquisition_successes} tag-search recovery, "
            f"{nav.safety_stops} safety stops"
        )

    lines.append(
        "Map: "
        f"{state.site_map.status}, {state.site_map.coverage_ratio:.0%} coverage, "
        f"{len(state.site_map.features)} landmarks"
    )
    lines.append(
        "Route: "
        f"{len(state.route_plan.waypoints)} waypoints, "
        f"{len(state.route_plan.points_of_interest)} photo points"
    )

    for changed in state.what_changed:
        lines.append(f"What changed: {changed}")

    lines.extend(["", "Point-of-interest results:"])
    for capture in state.poi_captures:
        lines.append(f"- {capture.poi_id}: {capture.analysis}")

    if state.sensor_readings:
        lines.extend(["", "Readings:"])
        for reading in state.sensor_readings:
            value = f"{reading.value}{reading.unit}" if reading.unit else str(reading.value)
            lines.append(
                f"- {reading.poi_id} {reading.name}: {value} [{reading.status}]"
            )

    lines.extend(["", "Incidents:"])
    for incident in state.incidents:
        lines.append(
            "- "
            f"{incident.id} {_value(incident.severity)} {_value(incident.type)}: "
            f"{incident.title} [{_value(incident.state)}]"
        )

    lines.extend(["", "Packages:"])
    for status in state.package_statuses.values():
        location = status.observed_zone_id or "not observed"
        blocker = f", blocks {status.blocks_asset_id}" if status.blocks_asset_id else ""
        lines.append(
            f"- {status.package_id}: {_value(status.state)}, expected {status.expected_zone_id}, "
            f"observed {location}{blocker}"
        )

    return "\n".join(lines) + "\n"


def assert_report_has_closed_loop(state: DogOpsState) -> None:
    incidents_by_id = {incident.id: incident for incident in state.incidents}
    work_orders_by_id = {work_order.id: work_order for work_order in state.work_orders}
    pkg_103 = state.package_statuses.get("PKG-103")
    pkg_104 = state.package_statuses.get("PKG-104")
    if incidents_by_id.get("INC-001") is None:
        raise AssertionError("INC-001 was not opened")
    if incidents_by_id["INC-001"].state != IncidentState.resolved:
        raise AssertionError("INC-001 was not verified closed")
    if work_orders_by_id.get("WO-001") is None:
        raise AssertionError("WO-001 was not opened")
    if work_orders_by_id["WO-001"].state != WorkOrderState.verified_closed:
        raise AssertionError("WO-001 was not verified closed")
    if not pkg_103 or pkg_103.state != PackageState.missing:
        raise AssertionError("PKG-103 must remain missing/open")
    if not pkg_104 or pkg_104.observed_zone_id != "QA_HOLD":
        raise AssertionError("PKG-104 must be moved to QA_HOLD")
    if not state.nav_summary:
        raise AssertionError("nav summary is missing")
    if not any(incident.type == IncidentType.missing_package for incident in state.incidents):
        raise AssertionError("missing package incident is missing")
