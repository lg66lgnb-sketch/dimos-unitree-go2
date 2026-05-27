from __future__ import annotations

import asyncio
from collections import deque
from concurrent.futures import TimeoutError as FutureTimeoutError
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import threading
import time
from typing import Any
from urllib.parse import urlparse

from dimos.experimental.dogops.dashboard_static import (
    build_map_data,
    build_poi_data,
    build_route_data,
    write_dashboard_html,
)
from dimos.experimental.dogops.live_map import DogOpsLiveMapAdapter
from dimos.experimental.dogops.store import DogOpsStore

try:  # pragma: no cover - exercised only inside a full DimOS checkout.
    from dimos.core.module import Module
except ModuleNotFoundError:

    class Module:
        @classmethod
        def blueprint(cls, **kwargs: object) -> dict[str, object]:
            return {"module": cls.__name__, "kwargs": kwargs}


DEFAULT_JOG_DURATION_S = 0.35
MAX_JOG_DURATION_S = 2.00
MAX_LINEAR_SPEED = 0.65
MAX_ANGULAR_SPEED = 1.10
ROBOT_CALL_TIMEOUT_S = 8.0
DIMOS_MCP_CALL_TIMEOUT_S = 12.0
WEBRTC_COMMAND_TIMEOUT_S = 2.0
HARD_STOP_REPEATS = 6
HARD_STOP_INTERVAL_S = 0.05
ROBOT_POSE_HISTORY_LIMIT = 240
MOTION_PROFILES: dict[str, tuple[float, float, float]] = {
    "nudge": (0.35, 1.0, 1.0),
    "step": (1.00, 2.3, 2.0),
    "walk": (2.00, 4.0, 3.0),
}
DEFAULT_MOTION_PROFILE = "nudge"
ROBOT_JOG_COMMANDS: dict[str, tuple[float, float, float]] = {
    "forward": (0.15, 0.0, 0.0),
    "backward": (-0.15, 0.0, 0.0),
    "left": (0.0, 0.15, 0.0),
    "right": (0.0, -0.15, 0.0),
    "yaw_left": (0.0, 0.0, 0.35),
    "yaw_right": (0.0, 0.0, -0.35),
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
_ROBOT_SESSIONS: dict[str, _RobotMotionSession] = {}
_ROBOT_SESSIONS_LOCK = threading.Lock()
_LIVE_MAP_ADAPTER = DogOpsLiveMapAdapter()


def make_dashboard_server(run_dir: str | Path, host: str, port: int) -> ThreadingHTTPServer:
    root = Path(run_dir)
    robot_control_token = secrets.token_urlsafe(32)
    write_dashboard_html(root, robot_control_token=robot_control_token)
    token = robot_control_token

    class Handler(DogOpsDashboardHandler):
        run_dir = root
        robot_control_token = token
        robot_ip = DEFAULT_ROBOT_IP

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
        return str(write_dashboard_html(self.run_dir))

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

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/dashboard.html"}:
            self._send_file(self.run_dir / "dashboard.html", "text/html; charset=utf-8")
        elif path == "/api/state":
            self._send_file(self.run_dir / "state.json", "application/json")
        elif path == "/api/report":
            self._send_file(self.run_dir / "report.json", "application/json")
        elif path == "/api/nav":
            report = self._read_json(self.run_dir / "report.json")
            self._send_json(report.get("nav_summary") or {})
        elif path == "/api/map":
            state = self._read_json(self.run_dir / "state.json")
            report = self._read_json(self.run_dir / "report.json")
            self._send_json(build_map_data(state, report, live_overlay=_LIVE_MAP_ADAPTER.snapshot()))
        elif path == "/api/robot/pose":
            if self._authorize_local_read():
                self._send_json(_robot_pose_snapshot(self.robot_ip))
        elif path == "/api/route":
            state = self._read_json(self.run_dir / "state.json")
            report = self._read_json(self.run_dir / "report.json")
            self._send_json(build_route_data(state, report))
        elif path == "/api/poi":
            state = self._read_json(self.run_dir / "state.json")
            report = self._read_json(self.run_dir / "report.json")
            self._send_json(build_poi_data(state, report))
        else:
            self._send_json({"error": "not_found", "path": path}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/work_orders/") and path.endswith("/ready_to_verify"):
            work_order_id = path.split("/")[3]
            self._mark_work_order_ready(work_order_id)
        elif path == "/api/operator/event":
            self._record_operator_event()
        elif path == "/api/robot/jog":
            if self._authorize_robot_control():
                self._robot_jog()
        elif path == "/api/robot/posture":
            if self._authorize_robot_control():
                self._robot_posture()
        elif path == "/api/robot/go_to":
            if self._authorize_robot_control():
                self._robot_go_to()
        elif path == "/api/robot/map_start":
            if self._authorize_robot_control():
                self._robot_map_start()
        elif path == "/api/robot/map_origin":
            if self._authorize_robot_control():
                self._robot_map_origin()
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
                write_dashboard_html(self.run_dir)
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
            if command in HARD_STOP_COMMANDS:
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

        self._send_json({"ok": bool(ok), "command": command})

    def _robot_go_to(self) -> None:
        payload = self._read_body_json()
        try:
            x, y = _go_to_target(payload)
        except ValueError as exc:
            self._send_json(
                {"ok": False, "error": "invalid_go_to_target", "message": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
            return

        source = str(payload.get("source") or "dashboard")
        try:
            result = _run_robot_call(lambda: _run_robot_go_to(x, y))
        except ModuleNotFoundError as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": "dimos_mcp_unavailable",
                    "message": str(exc),
                },
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        except TimeoutError as exc:
            self._send_json(
                {"ok": False, "error": "go_to_timeout", "message": str(exc)},
                HTTPStatus.GATEWAY_TIMEOUT,
            )
            return
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": "go_to_failed", "message": str(exc)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self._send_json(
            {
                "ok": True,
                "command": "go_to",
                "x": x,
                "y": y,
                "source": source,
                **(result or {}),
            }
        )

    def _robot_map_start(self) -> None:
        robot_ip = self.robot_ip
        try:
            result = _run_robot_call(lambda: _start_robot_map(robot_ip))
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
                {"ok": False, "error": "map_start_timeout", "message": str(exc)},
                HTTPStatus.GATEWAY_TIMEOUT,
            )
            return
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": "map_start_failed", "message": str(exc)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self._send_json({"ok": True, "command": "map_start", **result})

    def _robot_map_origin(self) -> None:
        robot_ip = self.robot_ip
        try:
            result = _run_robot_call(lambda: _reset_robot_map_origin(robot_ip))
        except TimeoutError as exc:
            self._send_json(
                {"ok": False, "error": "map_origin_timeout", "message": str(exc)},
                HTTPStatus.GATEWAY_TIMEOUT,
            )
            return
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": "map_origin_failed", "message": str(exc)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self._send_json({"ok": bool(result), "command": "map_origin"})

    def _authorize_local_read(self) -> bool:
        host = self.headers.get("Host", "")
        if not _is_loopback_host(_host_name(host)):
            self._send_json({"ok": False, "error": "local_read_only"}, HTTPStatus.FORBIDDEN)
            return False
        return True

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
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=ROBOT_CALL_TIMEOUT_S)
    if thread.is_alive():
        raise TimeoutError(f"robot command exceeded {ROBOT_CALL_TIMEOUT_S:.1f}s")
    if "error" in result:
        raise result["error"]
    return result.get("value")


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


def _go_to_target(payload: dict[str, Any]) -> tuple[float, float]:
    try:
        x = float(payload["x"])
        y = float(payload["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("go_to requires numeric x and y") from exc
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("go_to target must be finite")
    return x, y


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


def _run_robot_go_to(x: float, y: float) -> dict[str, Any]:
    return _call_dimos_mcp_skill("go_to", {"x": x, "y": y})


def _call_dimos_mcp_skill(skill_name: str, args: dict[str, Any]) -> dict[str, Any]:
    command = _dimos_mcp_call_command(skill_name, args)
    try:
        result = subprocess.run(
            command,
            cwd=_dimos_command_cwd(),
            env=_dimos_command_env(),
            capture_output=True,
            check=False,
            text=True,
            timeout=DIMOS_MCP_CALL_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise ModuleNotFoundError(
            f"DimOS MCP command is unavailable: {command[0]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"dimos mcp call {skill_name} timed out after {DIMOS_MCP_CALL_TIMEOUT_S:.1f}s"
        ) from exc

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode != 0:
        detail = stderr or stdout or "no output"
        raise RuntimeError(f"dimos mcp call {skill_name} failed: {detail}")
    payload: dict[str, Any] = {
        "transport": "dimos_mcp",
        "skill": skill_name,
    }
    if stdout:
        try:
            decoded = json.loads(stdout)
        except json.JSONDecodeError:
            payload["stdout"] = stdout
        else:
            if isinstance(decoded, dict):
                if decoded.get("ok") is False:
                    detail = decoded.get("error") or decoded.get("message") or decoded
                    raise RuntimeError(f"dimos mcp call {skill_name} returned error: {detail}")
                payload["mcp_result"] = decoded
            else:
                payload["mcp_result"] = {"value": decoded}
    return payload


def _dimos_mcp_call_command(skill_name: str, args: dict[str, Any]) -> list[str]:
    encoded_args = json.dumps(args, separators=(",", ":"))
    raw_prefix = os.environ.get("DOGOPS_DIMOS_MCP_CALL")
    if raw_prefix:
        return [*shlex.split(raw_prefix), skill_name, "--json-args", encoded_args]
    if shutil.which("uv") is not None:
        return ["uv", "run", "dimos", "mcp", "call", skill_name, "--json-args", encoded_args]
    return ["dimos", "mcp", "call", skill_name, "--json-args", encoded_args]


def _dimos_command_cwd() -> str | None:
    for name in ("DOGOPS_DIMOS_ROOT", "DIMOS_ROOT"):
        root = os.environ.get(name)
        if root and Path(root).exists():
            return root
    return None


def _dimos_command_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("NO_PROXY", "no_proxy"):
        existing = env.get(key, "")
        entries = [item.strip() for item in existing.split(",") if item.strip()]
        for host in ("127.0.0.1", "localhost"):
            if host not in entries:
                entries.append(host)
        env[key] = ",".join(entries)
    return env


def _get_robot_session(robot_ip: str) -> _RobotMotionSession:
    with _ROBOT_SESSIONS_LOCK:
        session = _ROBOT_SESSIONS.get(robot_ip)
        if session is not None and not session.closed:
            return session

    new_session = _RobotMotionSession(robot_ip)
    with _ROBOT_SESSIONS_LOCK:
        session = _ROBOT_SESSIONS.get(robot_ip)
        if session is not None and not session.closed:
            new_session.close()
            return session
        _ROBOT_SESSIONS[robot_ip] = new_session
        return new_session


def _close_robot_session(robot_ip: str) -> None:
    with _ROBOT_SESSIONS_LOCK:
        session = _ROBOT_SESSIONS.pop(robot_ip, None)
    if session is not None:
        session.close()


def _robot_pose_snapshot(robot_ip: str) -> dict[str, Any]:
    with _ROBOT_SESSIONS_LOCK:
        session = _ROBOT_SESSIONS.get(robot_ip)
    if session is None or session.closed:
        return {
            "ok": False,
            "connected": False,
            "source": "unitree_go2_odom",
            "robot_ip": robot_ip,
            "error": "robot_session_not_started",
        }
    return session.pose_snapshot()


def _start_robot_map(robot_ip: str) -> dict[str, Any]:
    return _get_robot_session(robot_ip).pose_snapshot()


def _reset_robot_map_origin(robot_ip: str) -> bool:
    with _ROBOT_SESSIONS_LOCK:
        session = _ROBOT_SESSIONS.get(robot_ip)
    if session is None or session.closed:
        return False
    return session.reset_map_origin()


class _RobotMotionSession:
    def __init__(self, robot_ip: str) -> None:
        from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD

        self.robot_ip = robot_ip
        self.rtc_topic = RTC_TOPIC
        self.sport_cmd = SPORT_CMD
        self.connection = self._make_connection(robot_ip)
        self.lock = threading.RLock()
        self.pose_lock = threading.RLock()
        self.closed = False
        self.mode = "connected"
        self._latest_pose: tuple[float, float, float] | None = None
        self._latest_pose_ts: float | None = None
        self._map_origin_pose: tuple[float, float, float] | None = None
        self._pose_history: deque[tuple[float, float, float, float]] = deque(
            maxlen=ROBOT_POSE_HISTORY_LIMIT
        )
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

    def pose_snapshot(self) -> dict[str, Any]:
        with self.pose_lock:
            latest = self._latest_pose
            latest_ts = self._latest_pose_ts
            origin = self._map_origin_pose
            history = list(self._pose_history)
        if latest is None or latest_ts is None or origin is None:
            return {
                "ok": False,
                "connected": not self.closed,
                "source": "unitree_go2_odom",
                "robot_ip": self.robot_ip,
                "error": "waiting_for_odom",
            }
        x, y, yaw = _relative_map_pose(latest, origin)
        return {
            "ok": True,
            "connected": not self.closed,
            "source": "unitree_go2_odom",
            "robot_ip": self.robot_ip,
            "ts": latest_ts,
            "pose": {"x": x, "y": y, "yaw_rad": yaw},
            "raw_pose": {"x": latest[0], "y": latest[1], "yaw_rad": latest[2]},
            "origin_raw_pose": {"x": origin[0], "y": origin[1], "yaw_rad": origin[2]},
            "trajectory": [
                {"x": item[0], "y": item[1], "yaw_rad": item[2], "ts": item[3]}
                for item in history
            ],
        }

    def reset_map_origin(self) -> bool:
        with self.pose_lock:
            if self._latest_pose is None:
                return False
            now = self._latest_pose_ts or time.time()
            self._map_origin_pose = self._latest_pose
            x, y, yaw = _relative_map_pose(self._latest_pose, self._map_origin_pose)
            self._pose_history.clear()
            self._pose_history.append((x, y, yaw, now))
            return True

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
        pose = _pose_xy_yaw(msg)
        now = time.time()
        with self.pose_lock:
            if self._map_origin_pose is None:
                self._map_origin_pose = pose
            self._latest_pose = pose
            self._latest_pose_ts = now
            x, y, yaw = _relative_map_pose(pose, self._map_origin_pose)
            self._pose_history.append((x, y, yaw, now))

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


def _relative_map_pose(
    pose: tuple[float, float, float],
    origin: tuple[float, float, float],
) -> tuple[float, float, float]:
    dx = pose[0] - origin[0]
    dy = pose[1] - origin[1]
    heading = -origin[2]
    cos_h = math.cos(heading)
    sin_h = math.sin(heading)
    x = (dx * cos_h) - (dy * sin_h)
    y = (dx * sin_h) + (dy * cos_h)
    yaw = _wrap_angle(pose[2] - origin[2])
    return x, y, yaw


def _wrap_angle(value: float) -> float:
    return math.atan2(math.sin(value), math.cos(value))


def _pose_delta(
    before: tuple[float, float, float] | None,
    after: tuple[float, float, float] | None,
) -> dict[str, Any]:
    if before is None or after is None:
        return {"observed": False}
    dx = after[0] - before[0]
    dy = after[1] - before[1]
    dyaw = _wrap_angle(after[2] - before[2])
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
