from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
import ipaddress
import json
import math
import os
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import urlparse

from dimos.experimental.dogops.dashboard_static import write_dashboard_html
from dimos.experimental.dogops.mapping import (
    add_point_of_interest,
    add_waypoint,
    build_simulated_site_map,
    simulate_poi_captures,
)
from dimos.experimental.dogops.models import NavAction, NavEvent
from dimos.experimental.dogops.nav_eval import summarize_nav_events
from dimos.experimental.dogops.rerun_sim import RERUN_COMMAND_FILENAME
from dimos.experimental.dogops.store import DogOpsStore

try:  # pragma: no cover - exercised only inside a full DimOS checkout.
    from dimos.core.module import Module
except ModuleNotFoundError:

    class Module:
        @classmethod
        def blueprint(cls, **kwargs: object) -> dict[str, object]:
            return {"module": cls.__name__, "kwargs": kwargs}


DEFAULT_JOG_DURATION_S = 0.35
PACKAGE_DIR = Path(__file__).parent
REPO_ROOT = PACKAGE_DIR.parents[2]
RERUN_WEB_VIEWER_DIR = REPO_ROOT / "node_modules" / "@rerun-io" / "web-viewer"
MAX_JOG_DURATION_S = 1.20
MAX_LINEAR_SPEED = 0.22
MAX_ANGULAR_SPEED = 0.45
ROBOT_CALL_TIMEOUT_S = 8.0
WEBRTC_COMMAND_TIMEOUT_S = 2.0
HARD_STOP_REPEATS = 6
HARD_STOP_INTERVAL_S = 0.05
MOTION_PROFILES: dict[str, tuple[float, float, float]] = {
    "nudge": (0.35, 1.0, 1.0),
    "step": (0.80, 1.2, 1.15),
    "walk": (1.20, 1.35, 1.35),
}
DEFAULT_MOTION_PROFILE = "nudge"
DEFAULT_DOGOPS_RUNTIME_MODE = "real"
SIMULATION_RUNTIME_MODES = {"sim", "simulation", "demo"}
OFFLINE_RUNTIME_MODES = {"offline", "static", "artifact"}
DIMOS_CONTROL_TIMEOUT_S = 3.0
ROBOT_JOG_COMMANDS: dict[str, tuple[float, float, float]] = {
    "forward": (0.15, 0.0, 0.0),
    "backward": (-0.15, 0.0, 0.0),
    "left": (0.0, 0.15, 0.0),
    "right": (0.0, -0.15, 0.0),
    "yaw_left": (0.0, 0.0, 0.30),
    "yaw_right": (0.0, 0.0, -0.30),
    "hard_stop": (0.0, 0.0, 0.0),
    "stop": (0.0, 0.0, 0.0),
}
HARD_STOP_COMMANDS = {"hard_stop", "stop"}
ROBOT_POSTURE_COMMANDS = {"wake", "balance", "sleep"}
ROBOT_CONTROL_TOKEN_HEADER = "X-DogOps-Control-Token"
DEFAULT_ROBOT_IP = (
    os.environ.get("DOGOPS_ROBOT_IP")
    or os.environ.get("GO2_IP")
    or os.environ.get("ROBOT_IP")
    or "192.168.12.1"
)
_ROBOT_SESSIONS: dict[str, "_RobotMotionSession"] = {}
_ROBOT_SESSIONS_LOCK = threading.Lock()


def make_dashboard_server(run_dir: str | Path, host: str, port: int) -> ThreadingHTTPServer:
    root = Path(run_dir)
    robot_control_token = secrets.token_urlsafe(32)
    selected_runtime_mode = _dogops_runtime_mode()
    write_dashboard_html(
        root,
        robot_control_token=robot_control_token,
        runtime_mode=selected_runtime_mode,
    )
    token = robot_control_token

    class Handler(DogOpsDashboardHandler):
        run_dir = root
        robot_control_token = token
        robot_ip = DEFAULT_ROBOT_IP
        runtime_mode = selected_runtime_mode

    return ThreadingHTTPServer((host, port), Handler)


def serve_dashboard(run_dir: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = make_dashboard_server(run_dir, host, port)
    address = f"http://{host}:{server.server_address[1]}"
    print(f"DogOps dashboard serving {Path(run_dir)} at {address}")
    try:
        server.serve_forever()
    finally:
        server.server_close()


class DogOpsDashboardModule(Module):
    def __init__(
        self,
        *,
        run_dir: str | Path = ".dogops/runs/latest",
        host: str = "127.0.0.1",
        port: int = 8765,
        **_: object,
    ) -> None:
        self.run_dir = Path(run_dir)
        self.host = host
        self.port = port

    def write_dashboard(self) -> str:
        return str(write_dashboard_html(self.run_dir, runtime_mode=_dogops_runtime_mode()))

    def serve(self) -> None:
        serve_dashboard(self.run_dir, self.host, self.port)

    def status(self) -> dict[str, object]:
        return {
            "run_dir": str(self.run_dir),
            "dashboard_html": str(self.run_dir / "dashboard.html"),
            "host": self.host,
            "port": self.port,
            "exists": (self.run_dir / "dashboard.html").exists(),
        }


class DogOpsDashboardHandler(BaseHTTPRequestHandler):
    run_dir: Path
    robot_control_token: str
    robot_ip: str
    runtime_mode: str

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", "/dashboard.html"}:
            self._send_file(self.run_dir / "dashboard.html", "text/html; charset=utf-8")
        elif path.startswith("/assets/"):
            asset = _resolve_dashboard_asset(path)
            if asset is None:
                self._send_json({"error": "asset_not_found", "path": path}, HTTPStatus.NOT_FOUND)
            else:
                self._send_file(*asset)
        elif path.startswith("/evidence/"):
            filename = Path(path).name
            content_type = "image/svg+xml" if filename.endswith(".svg") else "application/octet-stream"
            self._send_file(self.run_dir / "evidence" / filename, content_type)
        elif path == "/api/state":
            self._send_file(self.run_dir / "state.json", "application/json")
        elif path == "/api/report":
            self._send_file(self.run_dir / "report.json", "application/json")
        elif path == "/api/nav":
            report = self._read_json(self.run_dir / "report.json")
            self._send_json(report.get("nav_summary") or {})
        elif path == "/api/map":
            self._send_file(self.run_dir / "map.json", "application/json")
        elif path == "/api/route":
            self._send_file(self.run_dir / "route_plan.json", "application/json")
        elif path == "/api/poi":
            report = self._read_json(self.run_dir / "report.json")
            self._send_json(
                {
                    "captures": report.get("poi_captures") or [],
                    "readings": report.get("sensor_readings") or [],
                }
            )
        else:
            self._send_json({"error": "not_found", "path": path}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/work_orders/") and path.endswith("/ready_to_verify"):
            work_order_id = path.split("/")[3]
            self._mark_work_order_ready(work_order_id)
        elif path == "/api/operator/event":
            self._record_operator_event()
        elif path == "/api/map/explore":
            if self._authorize_dashboard_mutation():
                self._explore_map()
        elif path == "/api/map/stop_explore":
            if self._authorize_dashboard_mutation():
                self._stop_explore_map()
        elif path == "/api/route/waypoints":
            if self._authorize_dashboard_mutation():
                self._add_route_waypoint()
        elif path == "/api/route/pois":
            if self._authorize_dashboard_mutation():
                self._add_route_poi()
        elif path == "/api/route/run":
            if self._authorize_dashboard_mutation():
                self._run_route_plan()
        elif path == "/api/rerun/replay_map":
            if self._authorize_dashboard_mutation():
                self._replay_rerun_map()
        elif path == "/api/robot/jog":
            if self._authorize_robot_control():
                self._robot_jog()
        elif path == "/api/robot/posture":
            if self._authorize_robot_control():
                self._robot_posture()
        else:
            self._send_json({"error": "not_found", "path": path}, HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _mark_work_order_ready(self, work_order_id: str) -> None:
        store = DogOpsStore.load_existing(self.run_dir)
        state = store.state
        assert state is not None
        for work_order in state.work_orders:
            if work_order.id == work_order_id:
                work_order.state = "ready_to_verify"
                store.update_work_order(work_order)
                store.write_state(state.run.id)
                store.write_report(state.run.id)
                write_dashboard_html(
                    self.run_dir,
                    robot_control_token=self.robot_control_token,
                    runtime_mode=self.runtime_mode,
                )
                self._send_json({"ok": True, "work_order_id": work_order_id, "state": "ready_to_verify"})
                return
        self._send_json(
            {"ok": False, "error": "unknown_work_order", "work_order_id": work_order_id},
            HTTPStatus.NOT_FOUND,
        )

    def _record_operator_event(self) -> None:
        payload = self._read_body_json()
        events_path = self.run_dir / "operator_events.jsonl"
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        self._send_json({"ok": True, "path": str(events_path)})

    def _explore_map(self) -> None:
        store = DogOpsStore.load_existing(self.run_dir)
        state = store.state
        assert state is not None
        if _uses_dimos_navigation_runtime(self.runtime_mode):
            try:
                control = _dimos_start_explore()
            except Exception as exc:
                self._send_json(
                    {"ok": False, "error": "dimos_explore_failed", "message": str(exc)},
                    HTTPStatus.BAD_GATEWAY,
                )
                return
            site_map = state.site_map.model_copy(deep=True)
            site_map.status = "mapping"
            site_map.source = (
                "dimos_simulation" if _is_simulation_runtime(self.runtime_mode) else "dimos_real"
            )
            note = f"DimOS {self.runtime_mode} exploration command sent."
            if note not in site_map.notes:
                site_map.notes.append(note)
            store.set_site_map(site_map)
            store.write_state(state.run.id)
            store.write_report(state.run.id)
            write_dashboard_html(
                self.run_dir,
                robot_control_token=self.robot_control_token,
                runtime_mode=self.runtime_mode,
            )
            self._send_json(
                {
                    "ok": True,
                    "mode": self.runtime_mode,
                    "dimos": control,
                    "map": {
                        "status": site_map.status,
                        "coverage_ratio": site_map.coverage_ratio,
                        "features": len(site_map.features),
                    },
                }
            )
            return
        site_map = build_simulated_site_map(state.site, state.nav_events)
        store.set_site_map(site_map)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        command = _write_rerun_command(self.run_dir, "replay_mapping")
        write_dashboard_html(
            self.run_dir,
            robot_control_token=self.robot_control_token,
            runtime_mode=self.runtime_mode,
        )
        self._send_json(
            {
                "ok": True,
                "rerun": command,
                "map": {
                    "status": site_map.status,
                    "coverage_ratio": site_map.coverage_ratio,
                    "features": len(site_map.features),
                },
            }
        )

    def _stop_explore_map(self) -> None:
        if not _uses_dimos_navigation_runtime(self.runtime_mode):
            self._send_json(
                {"ok": False, "error": "stop_explore_requires_dimos_runtime"},
                HTTPStatus.BAD_REQUEST,
            )
            return
        try:
            control = _dimos_stop_explore()
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": "dimos_stop_explore_failed", "message": str(exc)},
                HTTPStatus.BAD_GATEWAY,
            )
            return

        store = DogOpsStore.load_existing(self.run_dir)
        state = store.state
        assert state is not None
        site_map = state.site_map.model_copy(deep=True)
        if site_map.status == "mapping":
            site_map.status = "mapped" if site_map.coverage_ratio > 0 else "empty"
        note = f"DimOS {self.runtime_mode} exploration stop command sent."
        if note not in site_map.notes:
            site_map.notes.append(note)
        store.set_site_map(site_map)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        write_dashboard_html(
            self.run_dir,
            robot_control_token=self.robot_control_token,
            runtime_mode=self.runtime_mode,
        )
        self._send_json({"ok": True, "mode": self.runtime_mode, "dimos": control})

    def _add_route_waypoint(self) -> None:
        payload = self._read_body_json()
        target_id = str(payload.get("target_id") or "").strip()
        if not target_id:
            self._send_json({"ok": False, "error": "missing_target_id"}, HTTPStatus.BAD_REQUEST)
            return
        store = DogOpsStore.load_existing(self.run_dir)
        state = store.state
        assert state is not None
        try:
            add_waypoint(state.route_plan, state.site, target_id)
        except KeyError:
            self._send_json(
                {"ok": False, "error": "unknown_target", "target_id": target_id},
                HTTPStatus.BAD_REQUEST,
            )
            return
        store.set_route_plan(state.route_plan)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        write_dashboard_html(
            self.run_dir,
            robot_control_token=self.robot_control_token,
            runtime_mode=self.runtime_mode,
        )
        self._send_json(
            {
                "ok": True,
                "waypoints": len(state.route_plan.waypoints),
                "route_plan": state.route_plan.model_dump(mode="json"),
            }
        )

    def _add_route_poi(self) -> None:
        payload = self._read_body_json()
        target_id = str(payload.get("target_id") or "").strip()
        if not target_id:
            self._send_json({"ok": False, "error": "missing_target_id"}, HTTPStatus.BAD_REQUEST)
            return
        reading_keys = payload.get("reading_keys")
        if reading_keys is not None and not isinstance(reading_keys, list):
            self._send_json({"ok": False, "error": "bad_reading_keys"}, HTTPStatus.BAD_REQUEST)
            return
        store = DogOpsStore.load_existing(self.run_dir)
        state = store.state
        assert state is not None
        try:
            add_point_of_interest(
                state.route_plan,
                state.site,
                target_id,
                waypoint_id=payload.get("waypoint_id"),
                reading_keys=[str(item) for item in reading_keys] if reading_keys else None,
            )
        except KeyError:
            self._send_json(
                {"ok": False, "error": "unknown_target", "target_id": target_id},
                HTTPStatus.BAD_REQUEST,
            )
            return
        store.set_route_plan(state.route_plan)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        write_dashboard_html(
            self.run_dir,
            robot_control_token=self.robot_control_token,
            runtime_mode=self.runtime_mode,
        )
        self._send_json(
            {
                "ok": True,
                "points_of_interest": len(state.route_plan.points_of_interest),
                "route_plan": state.route_plan.model_dump(mode="json"),
            }
        )

    def _run_route_plan(self) -> None:
        store = DogOpsStore.load_existing(self.run_dir)
        state = store.state
        assert state is not None
        dimos_goals: list[dict[str, Any]] = []
        if _uses_dimos_navigation_runtime(self.runtime_mode):
            try:
                dimos_goals = [
                    _dimos_click_goal(waypoint.pose.x or 0.0, waypoint.pose.y or 0.0)
                    for waypoint in state.route_plan.waypoints
                ]
            except Exception as exc:
                self._send_json(
                    {"ok": False, "error": "dimos_route_goal_failed", "message": str(exc)},
                    HTTPStatus.BAD_GATEWAY,
                )
                return
        next_nav_index = len(state.nav_events) + 1
        for offset, waypoint in enumerate(state.route_plan.waypoints):
            store.append_nav_event(
                NavEvent(
                    id=f"NAV-{next_nav_index + offset:03d}",
                    run_id=state.run.id,
                    ts=time.time(),
                    action=NavAction.goto,
                    target_id=waypoint.target_id,
                    success=True,
                    elapsed_s=3.0 + (offset * 0.5),
                    retries=0,
                    guided=False,
                    note=(
                        f"DimOS {self.runtime_mode} goal dispatched"
                        if _uses_dimos_navigation_runtime(self.runtime_mode)
                        else "operator route simulation"
                    ),
                )
            )
        state.nav_summary = summarize_nav_events(state.run.id, state.nav_events)
        if _uses_dimos_navigation_runtime(self.runtime_mode):
            site_map = state.site_map.model_copy(deep=True)
            if site_map.status == "empty":
                site_map.status = "mapping"
            site_map.source = (
                "dimos_simulation" if _is_simulation_runtime(self.runtime_mode) else "dimos_real"
            )
            note = f"DimOS {self.runtime_mode} route goals dispatched."
            if note not in site_map.notes:
                site_map.notes.append(note)
        else:
            site_map = build_simulated_site_map(state.site, state.nav_events)
        store.set_site_map(site_map)
        captures, readings = simulate_poi_captures(
            run_id=state.run.id,
            plan=state.route_plan,
            evidence_dir=self.run_dir / "evidence",
        )
        store.replace_poi_results(captures, readings)
        store.write_state(state.run.id)
        store.write_report(state.run.id)
        command = _write_rerun_command(self.run_dir, "replay_route")
        write_dashboard_html(
            self.run_dir,
            robot_control_token=self.robot_control_token,
            runtime_mode=self.runtime_mode,
        )
        self._send_json(
            {
                "ok": True,
                "mode": self.runtime_mode,
                "rerun": command,
                "dimos_goals": dimos_goals,
                "waypoints_run": len(state.route_plan.waypoints),
                "captures": len(captures),
                "readings": len(readings),
            }
        )

    def _replay_rerun_map(self) -> None:
        command = _write_rerun_command(self.run_dir, "replay_mapping")
        self._send_json({"ok": True, "rerun": command})

    def _robot_jog(self) -> None:
        payload = self._read_body_json()
        command = str(payload.get("command", "stop"))
        if command not in ROBOT_JOG_COMMANDS:
            self._send_json(
                {"ok": False, "error": "unknown_robot_command", "command": command},
                HTTPStatus.BAD_REQUEST,
            )
            return

        robot_ip = self.robot_ip

        try:
            linear_x, linear_y, angular_z, duration_s, profile = _resolve_motion_request(
                command, payload
            )
            if _is_simulation_runtime(self.runtime_mode):
                motion_result = _publish_simulation_jog(
                    linear_x,
                    linear_y,
                    angular_z,
                    0.0 if command in HARD_STOP_COMMANDS else duration_s,
                )
            elif command in HARD_STOP_COMMANDS:
                motion_result = _run_robot_call(lambda: _publish_robot_hard_stop(robot_ip))
            else:
                motion_result = _run_robot_call(
                    lambda: _publish_robot_jog(linear_x, linear_y, angular_z, duration_s, robot_ip)
                )
        except ModuleNotFoundError as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": "dimos_motion_unavailable",
                    "message": str(exc),
                },
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        except TimeoutError as exc:
            self._send_json(
                {"ok": False, "error": "robot_command_timeout", "message": str(exc)},
                HTTPStatus.GATEWAY_TIMEOUT,
            )
            return
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": "robot_command_failed", "message": str(exc)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self._send_json(
            {
                "ok": True,
                "mode": self.runtime_mode,
                "command": command,
                "duration_s": 0.0 if command in HARD_STOP_COMMANDS else duration_s,
                "linear_x": linear_x,
                "linear_y": linear_y,
                "angular_z": angular_z,
                "profile": profile,
                **(motion_result or {}),
            }
        )

    def _robot_posture(self) -> None:
        payload = self._read_body_json()
        command = str(payload.get("command", ""))
        if command not in ROBOT_POSTURE_COMMANDS:
            self._send_json(
                {"ok": False, "error": "unknown_posture_command", "command": command},
                HTTPStatus.BAD_REQUEST,
            )
            return

        robot_ip = self.robot_ip
        try:
            if _is_simulation_runtime(self.runtime_mode):
                ok = _run_simulation_posture(command)
            else:
                ok = _run_robot_call(lambda: _run_robot_posture(command, robot_ip))
        except ModuleNotFoundError as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": "dimos_motion_unavailable",
                    "message": str(exc),
                },
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        except TimeoutError as exc:
            self._send_json(
                {"ok": False, "error": "posture_command_timeout", "message": str(exc)},
                HTTPStatus.GATEWAY_TIMEOUT,
            )
            return
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": "posture_command_failed", "message": str(exc)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self._send_json({"ok": bool(ok), "mode": self.runtime_mode, "command": command})

    def _authorize_robot_control(self) -> bool:
        host = self.headers.get("Host", "")
        if not _is_loopback_host(_host_name(host)):
            self._send_json({"ok": False, "error": "robot_control_local_only"}, HTTPStatus.FORBIDDEN)
            return False

        origin = self.headers.get("Origin")
        if origin and not _origin_matches_host(origin, host):
            self._send_json({"ok": False, "error": "robot_control_bad_origin"}, HTTPStatus.FORBIDDEN)
            return False

        expected = self.robot_control_token
        provided = self.headers.get(ROBOT_CONTROL_TOKEN_HEADER, "")
        if not secrets.compare_digest(provided, expected):
            self._send_json({"ok": False, "error": "robot_control_forbidden"}, HTTPStatus.FORBIDDEN)
            return False

        return True

    def _authorize_dashboard_mutation(self) -> bool:
        host = self.headers.get("Host", "")
        if not _is_loopback_host(_host_name(host)):
            self._send_json({"ok": False, "error": "dashboard_local_only"}, HTTPStatus.FORBIDDEN)
            return False

        origin = self.headers.get("Origin")
        if origin and not _origin_matches_host(origin, host):
            self._send_json({"ok": False, "error": "dashboard_bad_origin"}, HTTPStatus.FORBIDDEN)
            return False

        return True

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._send_json({"error": "missing_file", "path": str(path)}, HTTPStatus.NOT_FOUND)
            return
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_body_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))


def _run_robot_call(fn: Any) -> Any:
    result: dict[str, Any] = {}

    def target() -> None:
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the request thread.
            result["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=ROBOT_CALL_TIMEOUT_S)
    if thread.is_alive():
        raise TimeoutError(f"robot command exceeded {ROBOT_CALL_TIMEOUT_S:.1f}s")
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _dogops_runtime_mode() -> str:
    mode = (os.environ.get("DOGOPS_RUNTIME_MODE") or DEFAULT_DOGOPS_RUNTIME_MODE).strip().lower()
    if mode in SIMULATION_RUNTIME_MODES:
        return "simulation"
    if mode in OFFLINE_RUNTIME_MODES:
        return "offline"
    return "real"


def _is_simulation_runtime(mode: str) -> bool:
    return mode.strip().lower() in SIMULATION_RUNTIME_MODES


def _uses_dimos_navigation_runtime(mode: str) -> bool:
    return mode.strip().lower() not in OFFLINE_RUNTIME_MODES


def _dimos_control_url() -> str:
    raw_url = (
        os.environ.get("DOGOPS_DIMOS_CONTROL_URL")
        or os.environ.get("DOGOPS_DIMOS_WS_URL")
        or "http://127.0.0.1:7779"
    ).strip()
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("DOGOPS_DIMOS_CONTROL_URL must be an http(s) URL")
    if not _is_loopback_host(parsed.hostname) and os.environ.get("DOGOPS_ALLOW_REMOTE_VIEWER") != "1":
        raise ValueError("DimOS control URL must be loopback unless DOGOPS_ALLOW_REMOTE_VIEWER=1")
    return raw_url.rstrip("/")


def _emit_dimos_socket_event(event: str, data: Any | None = None) -> dict[str, Any]:
    try:
        import socketio
        import requests
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency failure path.
        raise ModuleNotFoundError(
            "python-socketio and requests are required for DogOps DimOS simulation/real navigation controls"
        ) from exc

    url = _dimos_control_url()
    session = requests.Session()
    session.trust_env = False
    client = socketio.Client(
        reconnection=False,
        logger=False,
        engineio_logger=False,
        request_timeout=DIMOS_CONTROL_TIMEOUT_S,
        http_session=session,
    )
    try:
        client.connect(url, wait_timeout=DIMOS_CONTROL_TIMEOUT_S)
        if data is None:
            client.emit(event)
        else:
            client.emit(event, data)
    finally:
        if client.connected:
            client.disconnect()
    return {"event": event, "url": url, "sent": True}


def _dimos_start_explore() -> dict[str, Any]:
    return _emit_dimos_socket_event("start_explore")


def _dimos_stop_explore() -> dict[str, Any]:
    return _emit_dimos_socket_event("stop_explore")


def _dimos_click_goal(x: float, y: float) -> dict[str, Any]:
    return _emit_dimos_socket_event("click", [float(x), float(y)])


def _dimos_move_command(linear_x: float, linear_y: float, angular_z: float) -> dict[str, Any]:
    return _emit_dimos_socket_event(
        "move_command",
        {
            "linear": {"x": float(linear_x), "y": float(linear_y), "z": 0.0},
            "angular": {"x": 0.0, "y": 0.0, "z": float(angular_z)},
        },
    )


def _publish_simulation_jog(
    linear_x: float,
    linear_y: float,
    angular_z: float,
    duration_s: float,
) -> dict[str, Any]:
    control = _dimos_move_command(linear_x, linear_y, angular_z)
    stop_sent = False
    if duration_s > 0 and any((linear_x, linear_y, angular_z)):
        time.sleep(duration_s)
        _dimos_move_command(0.0, 0.0, 0.0)
        stop_sent = True
    return {
        "observed": False,
        "dimos": control,
        "simulation_stop_sent": stop_sent,
    }


def _run_simulation_posture(command: str) -> bool:
    if command == "sleep":
        _dimos_move_command(0.0, 0.0, 0.0)
    return True


def _write_rerun_command(run_dir: Path, action: str) -> dict[str, object]:
    command = {
        "id": f"{action}-{time.time_ns()}",
        "action": action,
        "created_at": time.time(),
    }
    (run_dir / RERUN_COMMAND_FILENAME).write_text(
        json.dumps(command, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return command


def _resolve_motion_request(
    command: str,
    payload: dict[str, Any],
) -> tuple[float, float, float, float, str]:
    linear_x, linear_y, angular_z = ROBOT_JOG_COMMANDS[command]
    requested_profile = str(payload.get("profile") or DEFAULT_MOTION_PROFILE)
    profile = requested_profile if requested_profile in MOTION_PROFILES else DEFAULT_MOTION_PROFILE
    profile_duration_s, linear_scale, angular_scale = MOTION_PROFILES[profile]

    try:
        duration_s = float(payload.get("duration_s", profile_duration_s))
    except (TypeError, ValueError):
        duration_s = profile_duration_s
    duration_s = max(0.05, min(duration_s, MAX_JOG_DURATION_S))

    linear_x = _cap(linear_x * linear_scale, MAX_LINEAR_SPEED)
    linear_y = _cap(linear_y * linear_scale, MAX_LINEAR_SPEED)
    angular_z = _cap(angular_z * angular_scale, MAX_ANGULAR_SPEED)
    return linear_x, linear_y, angular_z, duration_s, profile


def _cap(value: float, limit: float) -> float:
    return max(-limit, min(value, limit))


def _host_parts(host_header: str) -> tuple[str, int | None]:
    try:
        parsed = urlparse(f"//{host_header.strip()}")
        return (parsed.hostname or "").lower(), parsed.port
    except ValueError:
        return "", None


def _host_name(host_header: str) -> str:
    return _host_parts(host_header)[0]


def _is_loopback_host(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _origin_matches_host(origin: str, host_header: str) -> bool:
    try:
        parsed_origin = urlparse(origin)
        origin_host = (parsed_origin.hostname or "").lower()
        origin_port = parsed_origin.port
    except ValueError:
        return False

    request_host, request_port = _host_parts(host_header)
    if parsed_origin.scheme not in {"http", "https"}:
        return False
    if not _is_loopback_host(origin_host):
        return False
    return origin_host == request_host and origin_port == request_port


def _resolve_dashboard_asset(path: str) -> tuple[Path, str] | None:
    if path == "/assets/rerun-web-viewer.js":
        return PACKAGE_DIR / "static" / "rerun-web-viewer.js", "application/javascript; charset=utf-8"

    vendor_prefix = "/assets/vendor/@rerun-io/web-viewer/"
    if not path.startswith(vendor_prefix):
        return None

    filename = Path(path).name
    asset_files = {
        "index.js": ("index.js", "application/javascript; charset=utf-8"),
        "re_viewer": ("re_viewer.js", "application/javascript; charset=utf-8"),
        "re_viewer.js": ("re_viewer.js", "application/javascript; charset=utf-8"),
        "re_viewer_bg.wasm": ("re_viewer_bg.wasm", "application/wasm"),
    }
    asset_file = asset_files.get(filename)
    if asset_file is None:
        return None
    asset_name, content_type = asset_file
    return RERUN_WEB_VIEWER_DIR / asset_name, content_type


def _publish_robot_jog(
    linear_x: float,
    linear_y: float,
    angular_z: float,
    duration_s: float,
    robot_ip: str,
) -> dict[str, Any]:
    return _get_robot_session(robot_ip).jog(linear_x, linear_y, angular_z, duration_s)


def _publish_robot_hard_stop(robot_ip: str) -> dict[str, Any]:
    _get_robot_session(robot_ip).hard_stop()
    return {}


def _run_robot_posture(command: str, robot_ip: str) -> bool:
    session = _get_robot_session(robot_ip)
    try:
        return session.posture(command)
    finally:
        if command == "sleep":
            _close_robot_session(robot_ip)


def _get_robot_session(robot_ip: str) -> "_RobotMotionSession":
    with _ROBOT_SESSIONS_LOCK:
        session = _ROBOT_SESSIONS.get(robot_ip)
        if session is None or session.closed:
            session = _RobotMotionSession(robot_ip)
            _ROBOT_SESSIONS[robot_ip] = session
        return session


def _close_robot_session(robot_ip: str) -> None:
    with _ROBOT_SESSIONS_LOCK:
        session = _ROBOT_SESSIONS.pop(robot_ip, None)
    if session is not None:
        session.close()


class _RobotMotionSession:
    def __init__(self, robot_ip: str) -> None:
        from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD

        self.robot_ip = robot_ip
        self.rtc_topic = RTC_TOPIC
        self.sport_cmd = SPORT_CMD
        self.connection = self._make_connection(robot_ip)
        self.lock = threading.RLock()
        self.closed = False
        self.mode = "connected"
        self._latest_pose: tuple[float, float, float] | None = None
        self._odom_subscription = self.connection.raw_odom_stream().subscribe(self._set_pose)

    def _make_connection(self, robot_ip: str) -> Any:
        from dimos.robot.unitree.connection import UnitreeWebRTCConnection

        return UnitreeWebRTCConnection(robot_ip)

    def posture(self, command: str) -> bool:
        with self.lock:
            if command == "wake":
                ok = bool(self._sport("StandUp"))
                time.sleep(3.0)
                self._sport("BalanceStand")
                self.mode = "balance"
                return ok
            if command == "balance":
                self._sport("BalanceStand")
                self.mode = "balance"
                return True
            if command == "sleep":
                self.hard_stop()
                self._sport("StandDown")
                self.mode = "sleep"
                return True
            raise ValueError(f"unknown posture command: {command}")

    def jog(
        self,
        linear_x: float,
        linear_y: float,
        angular_z: float,
        duration_s: float,
    ) -> dict[str, Any]:
        with self.lock:
            restore_obstacles = bool(linear_x or linear_y)
            try:
                self._ensure_motion_ready(disable_obstacles=restore_obstacles)
                before = self._wait_pose()
                self._sport_move(linear_x, linear_y, angular_z)
                time.sleep(duration_s)
                self.hard_stop()
                after = self._wait_pose()
                return _pose_delta(before, after)
            finally:
                if restore_obstacles:
                    self.connection.set_obstacle_avoidance(True)

    def hard_stop(self) -> None:
        with self.lock:
            try:
                self._sport("StopMove")
            except Exception:
                pass
            for _ in range(HARD_STOP_REPEATS):
                self._send_joystick({"lx": 0, "ly": 0, "rx": 0, "ry": 0})
                time.sleep(HARD_STOP_INTERVAL_S)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self._odom_subscription.dispose()
        except Exception:
            pass
        try:
            self.connection.stop()
        except Exception:
            pass

    def _ensure_balance(self) -> None:
        if self.mode != "balance":
            self._sport("BalanceStand")
            self.mode = "balance"

    def _ensure_motion_ready(self, *, disable_obstacles: bool) -> None:
        if disable_obstacles:
            self.connection.set_obstacle_avoidance(False)
        self._ensure_balance()

    def _sport(self, command: str) -> Any:
        return self._request(
            self.rtc_topic["SPORT_MOD"],
            {"api_id": self.sport_cmd[command]},
        )

    def _sport_move(self, linear_x: float, linear_y: float, angular_z: float) -> Any:
        return self._request(
            self.rtc_topic["SPORT_MOD"],
            {
                "api_id": self.sport_cmd["Move"],
                "parameter": {"x": linear_x, "y": linear_y, "z": angular_z},
            },
        )

    def _request(self, topic: str, data: dict[str, Any]) -> Any:
        async def send_request() -> Any:
            return await self.connection.conn.datachannel.pub_sub.publish_request_new(topic, data)

        future = asyncio.run_coroutine_threadsafe(send_request(), self.connection.loop)
        try:
            result = future.result(timeout=WEBRTC_COMMAND_TIMEOUT_S)
        except FutureTimeoutError as exc:
            self.closed = True
            raise TimeoutError(f"WebRTC request timed out after {WEBRTC_COMMAND_TIMEOUT_S:.1f}s") from exc
        status_code = _response_status_code(result)
        if status_code not in {None, 0}:
            raise RuntimeError(f"WebRTC request failed with status code {status_code}")
        return result

    def _send_joystick(self, data: dict[str, float | int]) -> None:
        async def send_joystick() -> None:
            self.connection.conn.datachannel.pub_sub.publish_without_callback(
                self.rtc_topic["WIRELESS_CONTROLLER"],
                data=data,
            )

        future = asyncio.run_coroutine_threadsafe(send_joystick(), self.connection.loop)
        try:
            future.result(timeout=WEBRTC_COMMAND_TIMEOUT_S)
        except FutureTimeoutError as exc:
            self.closed = True
            raise TimeoutError(f"WebRTC joystick timed out after {WEBRTC_COMMAND_TIMEOUT_S:.1f}s") from exc

    def _set_pose(self, msg: Any) -> None:
        self._latest_pose = _pose_xy_yaw(msg)

    def _wait_pose(self) -> tuple[float, float, float] | None:
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if self._latest_pose is not None:
                return self._latest_pose
            time.sleep(0.02)
        return None


def _joystick_payload(linear_x: float, linear_y: float, angular_z: float) -> dict[str, float | int]:
    return {
        "lx": -linear_y,
        "ly": linear_x,
        "rx": -angular_z,
        "ry": 0,
    }


def _pose_xy_yaw(msg: Any) -> tuple[float, float, float]:
    pose = msg["data"]["pose"] if isinstance(msg, dict) else msg
    position = pose["position"] if isinstance(pose, dict) else pose.position
    orientation = pose["orientation"] if isinstance(pose, dict) else pose.orientation
    x = float(position["x"] if isinstance(position, dict) else position.x)
    y = float(position["y"] if isinstance(position, dict) else position.y)
    qx = float(orientation["x"] if isinstance(orientation, dict) else orientation.x)
    qy = float(orientation["y"] if isinstance(orientation, dict) else orientation.y)
    qz = float(orientation["z"] if isinstance(orientation, dict) else orientation.z)
    qw = float(orientation["w"] if isinstance(orientation, dict) else orientation.w)
    yaw = math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))
    return x, y, yaw


def _pose_delta(
    before: tuple[float, float, float] | None,
    after: tuple[float, float, float] | None,
) -> dict[str, Any]:
    if before is None or after is None:
        return {"observed": False}
    dx = after[0] - before[0]
    dy = after[1] - before[1]
    dyaw = after[2] - before[2]
    return {
        "observed": True,
        "observed_dx_m": dx,
        "observed_dy_m": dy,
        "observed_distance_m": math.hypot(dx, dy),
        "observed_dyaw_rad": dyaw,
    }


def _response_status_code(result: Any) -> int | None:
    if not isinstance(result, dict):
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    status = data.get("status")
    if not isinstance(status, dict):
        return None
    code = status.get("code")
    return int(code) if code is not None else None
