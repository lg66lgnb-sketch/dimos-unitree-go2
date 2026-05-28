from __future__ import annotations

import json
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any, Literal

from pydantic import Field

from dimos.experimental.dogops.models import DogOpsModel
from dimos.experimental.dogops.route_run_store import RouteRunStore, new_route_run_id


HEATMAP_RUN_ID = "GATHER_HEATMAP"
HEATMAP_RUN_LABEL = "Gather Heatmap"
HEATMAP_DIRNAME = "heatmaps"
LATEST_HEATMAP_FILENAME = "latest_heatmap.json"


class HeatmapRunEvent(DogOpsModel):
    id: str
    ts: float
    kind: str = "heatmap"
    state: str
    waypoint_id: str | None = None
    action_id: str | None = None
    target_id: str | None = None
    x: float | None = None
    y: float | None = None
    error_m: float | None = None
    retries: int = 0
    guided: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class HeatmapRunState(DogOpsModel):
    run_id: str
    route_run_id: str
    route_id: str = HEATMAP_RUN_ID
    state: Literal["running", "completed", "failed"]
    started_at: float
    completed_at: float | None = None
    frame: str = "map"
    transport: str = "dimos_costmap_snapshot"
    active_waypoint_id: str | None = None
    active_action_id: str | None = None
    waypoints_total: int = 0
    waypoints_reached: int = 0
    last_error: str | None = None
    reach_radius_m: float = 0.0
    waypoint_timeout_s: float = 0.0
    max_retries: int = 0
    events: list[HeatmapRunEvent] = Field(default_factory=list)


def gather_heatmap_run(
    run_dir: str | Path,
    *,
    live_snapshot: dict[str, Any],
    area_id: str = "",
    duration_s: float = 0.0,
    now: float | None = None,
) -> dict[str, Any]:
    root = Path(run_dir)
    started_at = now or time.time()
    route_run_id = new_route_run_id(HEATMAP_RUN_ID, now=started_at)
    costmap = live_snapshot.get("costmap") if isinstance(live_snapshot, dict) else None
    cells = costmap.get("cells") if isinstance(costmap, dict) else None
    has_costmap = isinstance(cells, list) and bool(cells)
    state = HeatmapRunState(
        run_id=root.name,
        route_run_id=route_run_id,
        state="running",
        started_at=started_at,
        frame=str((costmap or {}).get("frame") or "map"),
        transport="dimos_costmap_snapshot",
        events=[
            HeatmapRunEvent(
                id="heatmap-started",
                ts=started_at,
                state="started",
                target_id=area_id or None,
                payload={"area_id": area_id, "duration_s": duration_s},
                note="Gather heatmap run started",
            )
        ],
    )
    route = SimpleNamespace(
        id=HEATMAP_RUN_ID,
        label=HEATMAP_RUN_LABEL,
        mission_id="gather_heatmap",
    )
    route_snapshot = {
        "id": HEATMAP_RUN_ID,
        "label": HEATMAP_RUN_LABEL,
        "mission_id": "gather_heatmap",
        "run_kind": "gather_heatmap",
        "area_id": area_id,
        "duration_s": duration_s,
        "waypoints": [],
    }
    store = RouteRunStore(root)
    store.create_route_run(
        route_run_id=route_run_id,
        dogops_run_id=root.name,
        route=route,
        state=state,
        dry_run=False,
        route_snapshot=route_snapshot,
    )

    completed_at = time.time()
    state.completed_at = completed_at
    if has_costmap:
        snapshot = _heatmap_snapshot_payload(
            route_run_id=route_run_id,
            area_id=area_id,
            duration_s=duration_s,
            live_snapshot=live_snapshot,
            costmap=costmap,
            collected_at=completed_at,
        )
        snapshot_path = _write_heatmap_snapshot(root, route_run_id, snapshot)
        state.state = "completed"
        state.events.append(
            HeatmapRunEvent(
                id="heatmap-collected",
                ts=completed_at,
                state="completed",
                target_id=area_id or None,
                payload={
                    "area_id": area_id,
                    "cells": len(cells),
                    "path": str(snapshot_path),
                    "source": costmap.get("source") or live_snapshot.get("source"),
                },
                note=f"Gathered heatmap with {len(cells)} cells",
            )
        )
        store.sync_execution_state(state)
        evidence = store.record_evidence(
            route_run_id=route_run_id,
            event_id=f"{route_run_id}-heatmap-collected",
            observation_id=None,
            kind="costmap_snapshot",
            path=snapshot_path,
            mime_type="application/json",
            metadata={
                "area_id": area_id,
                "cells": len(cells),
                "source": costmap.get("source") or live_snapshot.get("source"),
            },
        )
        return {
            "ok": True,
            "run_kind": "gather_heatmap",
            "route_run_id": route_run_id,
            "state": state.model_dump(mode="json"),
            "heatmap": snapshot,
            "snapshot_path": str(snapshot_path),
            "evidence": evidence,
        }

    state.state = "failed"
    state.last_error = "No live DimOS costmap cells are available to gather."
    state.events.append(
        HeatmapRunEvent(
            id="heatmap-failed",
            ts=completed_at,
            state="failed",
            target_id=area_id or None,
            payload={"area_id": area_id, "live_status": live_snapshot.get("status")},
            note=state.last_error,
        )
    )
    store.sync_execution_state(state)
    return {
        "ok": False,
        "run_kind": "gather_heatmap",
        "error": "heatmap_unavailable",
        "message": state.last_error,
        "route_run_id": route_run_id,
        "state": state.model_dump(mode="json"),
    }


def latest_heatmap_snapshot(run_dir: str | Path) -> dict[str, Any] | None:
    path = Path(run_dir) / HEATMAP_DIRNAME / LATEST_HEATMAP_FILENAME
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_heatmap_snapshot(
    run_dir: Path,
    route_run_id: str,
    snapshot: dict[str, Any],
) -> Path:
    heatmap_dir = run_dir / HEATMAP_DIRNAME
    heatmap_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = heatmap_dir / f"{route_run_id}.json"
    raw = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    snapshot_path.write_text(raw, encoding="utf-8")
    (heatmap_dir / LATEST_HEATMAP_FILENAME).write_text(raw, encoding="utf-8")
    return snapshot_path


def _heatmap_snapshot_payload(
    *,
    route_run_id: str,
    area_id: str,
    duration_s: float,
    live_snapshot: dict[str, Any],
    costmap: dict[str, Any],
    collected_at: float,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_kind": "gather_heatmap",
        "route_run_id": route_run_id,
        "area_id": area_id,
        "duration_s": duration_s,
        "collected_at": collected_at,
        "source": costmap.get("source") or live_snapshot.get("source") or "DimOS live costmap",
        "status": live_snapshot.get("status"),
        "robot_pose": live_snapshot.get("robot_pose"),
        "target": live_snapshot.get("target"),
        "costmap": costmap,
    }
