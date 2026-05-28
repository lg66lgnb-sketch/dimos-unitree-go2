from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import time
from typing import Any
import uuid


ROUTE_RUN_DB_FILENAME = "dogops.sqlite"


def dogops_history_root(run_dir: str | Path) -> Path:
    path = Path(run_dir).resolve()
    if path.parent.name == "runs" and path.parent.parent.name == ".dogops":
        return path.parent.parent
    return path.parent


def route_run_db_path(run_dir: str | Path) -> Path:
    return dogops_history_root(run_dir) / ROUTE_RUN_DB_FILENAME


def new_route_run_id(route_id: str, *, now: float | None = None) -> str:
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now or time.time()))
    suffix = uuid.uuid4().hex[:8]
    slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in route_id).strip("-")
    return f"RR-{timestamp}-{slug or 'route'}-{suffix}"


class RouteRunStore:
    def __init__(self, run_dir: str | Path, *, db_path: str | Path | None = None) -> None:
        self.run_dir = Path(run_dir)
        self.db_path = Path(db_path) if db_path is not None else route_run_db_path(self.run_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def create_route_run(
        self,
        *,
        route_run_id: str,
        dogops_run_id: str,
        route: Any,
        state: Any,
        dry_run: bool,
        route_snapshot: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO route_runs (
                  route_run_id, dogops_run_id, run_dir, route_id, route_label, mission_id,
                  state, started_at, completed_at, dry_run, transport, frame,
                  selected_route_snapshot_json, active_waypoint_id, active_action_id,
                  waypoints_total, waypoints_reached, actions_total, actions_completed,
                  last_error, summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    route_run_id,
                    dogops_run_id,
                    str(self.run_dir),
                    route.id,
                    route.label,
                    route.mission_id,
                    state.state,
                    state.started_at,
                    state.completed_at,
                    1 if dry_run else 0,
                    state.transport,
                    state.frame,
                    json.dumps(route_snapshot, sort_keys=True),
                    state.active_waypoint_id,
                    getattr(state, "active_action_id", None),
                    state.waypoints_total,
                    state.waypoints_reached,
                    _route_action_count(route_snapshot),
                    0,
                    state.last_error,
                    "",
                ),
            )

    def sync_execution_state(self, state: Any) -> None:
        route_run_id = getattr(state, "route_run_id", None)
        if not route_run_id:
            return
        events = [event.model_dump(mode="json") for event in state.events]
        actions_completed = sum(
            1 for event in events if event.get("kind") == "action" and event.get("state") == "completed"
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE route_runs
                SET state = ?, completed_at = ?, active_waypoint_id = ?, active_action_id = ?,
                    waypoints_total = ?, waypoints_reached = ?, actions_completed = ?,
                    last_error = ?, summary = ?
                WHERE route_run_id = ?
                """,
                (
                    state.state,
                    state.completed_at,
                    state.active_waypoint_id,
                    getattr(state, "active_action_id", None),
                    state.waypoints_total,
                    state.waypoints_reached,
                    actions_completed,
                    state.last_error,
                    _summary_for_state(state),
                    route_run_id,
                ),
            )
            for sequence, event in enumerate(events, 1):
                event_id = f"{route_run_id}-{event['id']}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO route_run_events (
                      event_id, route_run_id, ts, sequence, kind, state, waypoint_id,
                      action_id, target_id, x, y, error_m, retries, guided, payload_json, note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        route_run_id,
                        event["ts"],
                        sequence,
                        event.get("kind") or "waypoint",
                        event["state"],
                        event.get("waypoint_id"),
                        event.get("action_id"),
                        event.get("target_id"),
                        event.get("x"),
                        event.get("y"),
                        event.get("error_m"),
                        event.get("retries") or 0,
                        1 if event.get("guided") else 0,
                        json.dumps(event.get("payload") or {}, sort_keys=True),
                        event.get("note") or "",
                    ),
                )
        self._write_route_run_exports(route_run_id, state)

    def record_evidence(
        self,
        *,
        route_run_id: str,
        event_id: str | None,
        observation_id: str | None,
        kind: str,
        path: str | Path | None,
        metadata: dict[str, Any] | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        evidence_id = f"EVD-{uuid.uuid4().hex[:10]}"
        created_at = time.time()
        evidence_path = str(path) if path is not None else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO route_run_evidence (
                  evidence_id, route_run_id, event_id, observation_id, kind, path, uri,
                  sha256, mime_type, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    route_run_id,
                    event_id,
                    observation_id,
                    kind,
                    evidence_path,
                    None,
                    None,
                    mime_type,
                    json.dumps(metadata or {}, sort_keys=True),
                    created_at,
                ),
            )
        return {
            "evidence_id": evidence_id,
            "route_run_id": route_run_id,
            "event_id": event_id,
            "observation_id": observation_id,
            "kind": kind,
            "path": evidence_path,
            "mime_type": mime_type,
            "metadata": metadata or {},
            "created_at": created_at,
        }

    def list_route_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM route_runs
                ORDER BY started_at DESC, route_run_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def current_route_run(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM route_runs
                WHERE dogops_run_id = ?
                ORDER BY
                  CASE state WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END,
                  started_at DESC
                LIMIT 1
                """,
                (self.run_dir.name,),
            ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def route_run_detail(self, route_run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM route_runs WHERE route_run_id = ?",
                (route_run_id,),
            ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def route_run_events(self, route_run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM route_run_events
                WHERE route_run_id = ?
                ORDER BY sequence ASC
                """,
                (route_run_id,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def route_run_evidence(self, route_run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM route_run_evidence
                WHERE route_run_id = ?
                ORDER BY created_at ASC
                """,
                (route_run_id,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def _write_route_run_exports(self, route_run_id: str, state: Any) -> None:
        run_dir = self.run_dir / "route_runs" / route_run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        run_payload = state.model_dump(mode="json")
        (run_dir / "route_run.json").write_text(
            json.dumps(run_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with (run_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
            for event in run_payload.get("events") or []:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
        (run_dir / "evidence").mkdir(exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS route_runs (
                  route_run_id TEXT PRIMARY KEY,
                  dogops_run_id TEXT NOT NULL,
                  run_dir TEXT NOT NULL,
                  route_id TEXT NOT NULL,
                  route_label TEXT,
                  mission_id TEXT,
                  state TEXT NOT NULL,
                  started_at REAL NOT NULL,
                  completed_at REAL,
                  operator_id TEXT,
                  dry_run INTEGER NOT NULL DEFAULT 0,
                  transport TEXT NOT NULL,
                  frame TEXT NOT NULL,
                  selected_route_snapshot_json TEXT NOT NULL,
                  active_waypoint_id TEXT,
                  active_action_id TEXT,
                  waypoints_total INTEGER NOT NULL DEFAULT 0,
                  waypoints_reached INTEGER NOT NULL DEFAULT 0,
                  actions_total INTEGER NOT NULL DEFAULT 0,
                  actions_completed INTEGER NOT NULL DEFAULT 0,
                  last_error TEXT,
                  summary TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS route_run_events (
                  event_id TEXT PRIMARY KEY,
                  route_run_id TEXT NOT NULL,
                  ts REAL NOT NULL,
                  sequence INTEGER NOT NULL,
                  kind TEXT NOT NULL,
                  state TEXT NOT NULL,
                  waypoint_id TEXT,
                  action_id TEXT,
                  target_id TEXT,
                  x REAL,
                  y REAL,
                  error_m REAL,
                  retries INTEGER NOT NULL DEFAULT 0,
                  guided INTEGER NOT NULL DEFAULT 0,
                  payload_json TEXT NOT NULL DEFAULT '{}',
                  note TEXT NOT NULL DEFAULT '',
                  FOREIGN KEY(route_run_id) REFERENCES route_runs(route_run_id)
                );

                CREATE TABLE IF NOT EXISTS route_run_evidence (
                  evidence_id TEXT PRIMARY KEY,
                  route_run_id TEXT NOT NULL,
                  event_id TEXT,
                  observation_id TEXT,
                  kind TEXT NOT NULL,
                  path TEXT,
                  uri TEXT,
                  sha256 TEXT,
                  mime_type TEXT,
                  metadata_json TEXT NOT NULL DEFAULT '{}',
                  created_at REAL NOT NULL,
                  FOREIGN KEY(route_run_id) REFERENCES route_runs(route_run_id),
                  FOREIGN KEY(event_id) REFERENCES route_run_events(event_id)
                );

                CREATE INDEX IF NOT EXISTS idx_route_runs_started_at
                  ON route_runs(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_route_runs_dogops_run_id
                  ON route_runs(dogops_run_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_route_runs_route_id
                  ON route_runs(route_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_route_run_events_run_sequence
                  ON route_run_events(route_run_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_route_run_evidence_run
                  ON route_run_evidence(route_run_id, created_at);
                """
            )


def _route_action_count(route_snapshot: dict[str, Any]) -> int:
    return sum(len(waypoint.get("actions") or []) for waypoint in route_snapshot.get("waypoints") or [])


def _summary_for_state(state: Any) -> str:
    return (
        f"{state.state}: {state.waypoints_reached}/{state.waypoints_total} waypoints"
        + (f"; {state.last_error}" if state.last_error else "")
    )


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    result = dict(row)
    for key in ("selected_route_snapshot_json", "payload_json", "metadata_json"):
        if key in result:
            raw = result.pop(key)
            target = key.removesuffix("_json")
            try:
                result[target] = json.loads(raw or "{}")
            except json.JSONDecodeError:
                result[target] = {}
    return result
