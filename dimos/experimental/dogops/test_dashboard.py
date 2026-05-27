from __future__ import annotations

import json
import threading
from typing import Any
import urllib.request

import pytest

from dimos.experimental.dogops import dashboard, dashboard_static
from dimos.experimental.dogops.dashboard import DogOpsDashboardModule, make_dashboard_server
from dimos.experimental.dogops.dashboard_static import (
    build_map_data,
    build_poi_data,
    build_route_data,
    write_dashboard_html,
)
from dimos.experimental.dogops.mission_engine import run_offline_simulation


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.status, json.loads(exc.read().decode("utf-8"))


def _robot_headers(server) -> dict[str, str]:
    return {
        dashboard.ROBOT_CONTROL_TOKEN_HEADER: server.RequestHandlerClass.robot_control_token,
    }


def test_dashboard_static_html_contains_closed_loop_result(tmp_path) -> None:
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)

    html_path = write_dashboard_html(run_dir)
    content = html_path.read_text(encoding="utf-8")

    assert "DogOps SiteOps Agent" in content
    assert "Mission Map" in content
    assert 'data-map-surface' in content
    assert "map-route" in content
    assert "map-free-cell" in content
    assert "map-point" in content
    assert "map-robot-core" in content
    assert "free grid" in content
    assert "tag return" in content
    assert "no-go cost" in content
    assert 'data-rerun-surface' in content
    assert 'data-rerun-connect' in content
    assert 'data-rerun-frame' in content
    assert 'data-rerun-url=' in content
    assert 'data-rerun-web-link' in content
    assert "Rerun Web Visualization" in content
    assert "connectRerunSurface" in content
    assert 'data-map-command-status' in content
    assert 'data-map-action="arm_go_to"' in content
    assert 'data-go-to-marker' in content
    assert "/api/robot/go_to" in content
    assert "worldFromSvgEvent" in content
    assert "map-zone no-go" not in content
    assert "OBS-003" in content
    assert "PKG-104" in content
    assert "INC-001" in content
    assert "Navigation Eval" in content
    assert "Route / POI Evidence" in content
    assert "Route Stops" in content
    assert "POI Evidence" in content
    assert "Robot Control" in content
    assert "Checkpoint Sign-In" in content
    assert "Tag Sign-In" in content
    assert "OBS-005" in content
    assert 'data-command="forward"' in content
    assert 'data-command="hard_stop"' in content
    assert 'data-command="yaw_left" data-key-hint="Q"' in content
    assert 'data-command="yaw_right" data-key-hint="E"' in content
    assert 'data-key-hint="W / Up"' in content
    assert 'data-key-hint="Space / Esc"' in content
    assert 'data-keyboard-map' in content
    assert '["KeyW", "forward"]' in content
    assert '["KeyQ", "yaw_left"]' in content
    assert '["KeyE", "yaw_right"]' in content
    assert '["ArrowDown", "backward"]' in content
    assert '["Space", "hard_stop"]' in content
    assert '["Escape", "hard_stop"]' in content
    assert "shouldIgnoreKeyboardEvent" in content
    assert 'data-posture="wake"' in content
    assert 'data-posture="sleep"' in content
    assert 'data-motion="nudge"' in content
    assert 'data-motion="step"' in content
    assert 'data-motion="walk"' in content
    assert "X-DogOps-Control-Token" in content


def test_dashboard_rerun_web_url_stays_loopback_only() -> None:
    fallback = "http://127.0.0.1:9877"

    assert dashboard_static._trusted_rerun_web_url(None) == fallback
    assert dashboard_static._trusted_rerun_web_url("http://127.0.0.1:9877") == fallback
    assert (
        dashboard_static._trusted_rerun_web_url("http://localhost:9877/?dataset=dogops")
        == "http://localhost:9877/?dataset=dogops"
    )
    assert (
        dashboard_static._trusted_rerun_web_url("https://[::1]:9877")
        == "https://[::1]:9877"
    )
    assert dashboard_static._trusted_rerun_web_url("https://rerun.example.com") == fallback
    assert dashboard_static._trusted_rerun_web_url("javascript:alert(1)") == fallback


def test_dashboard_module_writes_dashboard_and_reports_status(tmp_path) -> None:
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    module = DogOpsDashboardModule(run_dir=run_dir, port=18765)

    html_path = module.write_dashboard()
    status = module.status()

    assert html_path.endswith("dashboard.html")
    assert status["exists"] is True
    assert status["port"] == 18765


def test_dashboard_api_serves_state_report_and_nav(tmp_path) -> None:
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urllib.request.urlopen(f"{base_url}/", timeout=5) as response:
            html = response.read().decode("utf-8")
        state = _get_json(f"{base_url}/api/state")
        report = _get_json(f"{base_url}/api/report")
        nav = _get_json(f"{base_url}/api/nav")
        map_data = _get_json(f"{base_url}/api/map")
        route = _get_json(f"{base_url}/api/route")
        poi = _get_json(f"{base_url}/api/poi")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert "DogOps SiteOps Agent" in html
    assert state["run"]["state"] == "done"  # type: ignore[index]
    assert report["manifest_exceptions"] == 2
    assert report["checkpoints_verified"] == 4
    assert report["checkpoint_verifications"][2]["target_id"] == "COOLING_1"  # type: ignore[index]
    assert report["checkpoint_verifications"][2]["expected_tag_id"] == 41  # type: ignore[index]
    assert nav["waypoints_reached"] == 4
    assert [stop["target_id"] for stop in map_data["route"]] == [
        "HOME",
        "INBOUND_DOCK",
        "COOLING_1",
        "QA_HOLD",
    ]
    assert [stop["target_id"] for stop in route["stops"]] == [
        "HOME",
        "INBOUND_DOCK",
        "COOLING_1",
        "QA_HOLD",
    ]
    assert route["stops"][2]["tag_verified"] is True  # type: ignore[index]
    assert any(capture["id"] == "OBS-003" for capture in poi["captures"])  # type: ignore[index]
    assert any(reading["asset_id"] == "TEMP_1" for reading in poi["readings"])  # type: ignore[index]
    assert any(package["id"] == "PKG-104" for package in map_data["packages"])


def test_dashboard_map_data_projects_site_route_and_observations(tmp_path) -> None:
    run_dir = tmp_path / "latest"
    state = run_offline_simulation(out=run_dir)
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))

    map_data = build_map_data(state.model_dump(mode="json"), report)

    assert map_data["site_id"] == "dogops_demo_site"
    assert {zone["id"] for zone in map_data["zones"]} >= {"HOME", "INBOUND_DOCK", "QA_HOLD"}
    assert [stop["target_id"] for stop in map_data["route"]] == [
        "HOME",
        "INBOUND_DOCK",
        "COOLING_1",
        "QA_HOLD",
    ]
    assert any(observation["id"] == "OBS-003" for observation in map_data["observations"])
    assert any(incident["id"] == "INC-001" for incident in map_data["incidents"])


def test_dashboard_route_and_poi_data_project_evidence(tmp_path) -> None:
    run_dir = tmp_path / "latest"
    state = run_offline_simulation(out=run_dir)
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))

    route = build_route_data(state.model_dump(mode="json"), report)
    poi = build_poi_data(state.model_dump(mode="json"), report)

    assert route["route_coverage"] == 1.0
    assert route["stops"][2]["target_id"] == "COOLING_1"  # type: ignore[index]
    assert route["stops"][2]["expected_tag_id"] == 41  # type: ignore[index]
    assert route["stops"][2]["tag_verified"] is True  # type: ignore[index]
    assert any(capture["id"] == "OBS-003" for capture in poi["captures"])  # type: ignore[index]
    assert any(
        reading["asset_id"] == "COOLING_1" and reading["clearance_clear"] is True
        for reading in poi["readings"]  # type: ignore[index]
    )
    assert any(
        reading["asset_id"] == "TEMP_1" and reading["within_threshold"] is True
        for reading in poi["readings"]  # type: ignore[index]
    )


def test_dashboard_robot_jog_sends_low_speed_bounded_pulse(tmp_path, monkeypatch) -> None:
    calls: list[tuple[float, float, float, float, str]] = []

    def fake_publish(
        linear_x: float,
        linear_y: float,
        angular_z: float,
        duration_s: float,
        robot_ip: str,
    ) -> None:
        calls.append((linear_x, linear_y, angular_z, duration_s, robot_ip))

    monkeypatch.setattr(dashboard, "_publish_robot_jog", fake_publish)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(
            f"{base_url}/api/robot/jog",
            {"command": "forward", "duration_s": 99},
            headers=_robot_headers(server),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert result["ok"] is True
    assert result["linear_x"] == 0.15
    assert result["duration_s"] == dashboard.MAX_JOG_DURATION_S
    assert result["profile"] == "nudge"
    assert calls == [(0.15, 0.0, 0.0, dashboard.MAX_JOG_DURATION_S, "192.168.12.1")]


def test_dashboard_robot_jog_applies_motion_profile(tmp_path, monkeypatch) -> None:
    calls: list[tuple[float, float, float, float, str]] = []

    def fake_publish(
        linear_x: float,
        linear_y: float,
        angular_z: float,
        duration_s: float,
        robot_ip: str,
    ) -> None:
        calls.append((linear_x, linear_y, angular_z, duration_s, robot_ip))

    monkeypatch.setattr(dashboard, "_publish_robot_jog", fake_publish)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(
            f"{base_url}/api/robot/jog",
            {"command": "forward", "profile": "walk"},
            headers=_robot_headers(server),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert result["ok"] is True
    assert result["profile"] == "walk"
    assert result["linear_x"] == pytest.approx(0.6)
    assert result["duration_s"] == 2.0
    assert calls == [(0.6, 0.0, 0.0, 2.0, "192.168.12.1")]


def test_dashboard_robot_jog_ignores_payload_robot_ip(tmp_path, monkeypatch) -> None:
    calls: list[str] = []

    def fake_publish(
        linear_x: float,
        linear_y: float,
        angular_z: float,
        duration_s: float,
        robot_ip: str,
    ) -> None:
        calls.append(robot_ip)

    monkeypatch.setattr(dashboard, "_publish_robot_jog", fake_publish)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(
            f"{base_url}/api/robot/jog",
            {"command": "forward", "robot_ip": "10.0.0.99"},
            headers=_robot_headers(server),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert result["ok"] is True
    assert "robot_ip" not in result
    assert calls == ["192.168.12.1"]


def test_dashboard_robot_control_requires_token(tmp_path, monkeypatch) -> None:
    def fail_publish(*_: object) -> None:
        raise AssertionError("unauthorized robot control must not publish")

    monkeypatch.setattr(dashboard, "_publish_robot_jog", fail_publish)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(f"{base_url}/api/robot/jog", {"command": "forward"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 403
    assert result["ok"] is False
    assert result["error"] == "robot_control_forbidden"


def test_dashboard_robot_control_rejects_non_loopback_host(tmp_path, monkeypatch) -> None:
    def fail_publish(*_: object) -> None:
        raise AssertionError("non-local robot control must not publish")

    monkeypatch.setattr(dashboard, "_publish_robot_jog", fail_publish)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(
            f"{base_url}/api/robot/jog",
            {"command": "forward"},
            headers={
                **_robot_headers(server),
                "Host": "192.168.1.10:8765",
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 403
    assert result["ok"] is False
    assert result["error"] == "robot_control_local_only"


def test_dashboard_robot_control_rejects_cross_origin(tmp_path, monkeypatch) -> None:
    def fail_publish(*_: object) -> None:
        raise AssertionError("cross-origin robot control must not publish")

    monkeypatch.setattr(dashboard, "_publish_robot_jog", fail_publish)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(
            f"{base_url}/api/robot/jog",
            {"command": "forward"},
            headers={
                **_robot_headers(server),
                "Origin": "https://example.com",
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 403
    assert result["ok"] is False
    assert result["error"] == "robot_control_bad_origin"


def test_motion_profile_falls_back_and_caps_speed() -> None:
    linear_x, linear_y, angular_z, duration_s, profile = dashboard._resolve_motion_request(
        "forward",
        {"profile": "too_fast", "duration_s": 99},
    )

    assert profile == "nudge"
    assert linear_x == 0.15
    assert linear_y == 0.0
    assert angular_z == 0.0
    assert duration_s == dashboard.MAX_JOG_DURATION_S


def test_dashboard_robot_hard_stop_uses_hard_stop_publisher(tmp_path, monkeypatch) -> None:
    jog_calls: list[tuple[float, float, float, float, str]] = []
    hard_stop_calls: list[str] = []

    def fake_publish(
        linear_x: float,
        linear_y: float,
        angular_z: float,
        duration_s: float,
        robot_ip: str,
    ) -> None:
        jog_calls.append((linear_x, linear_y, angular_z, duration_s, robot_ip))

    def fake_hard_stop(robot_ip: str) -> None:
        hard_stop_calls.append(robot_ip)

    monkeypatch.setattr(dashboard, "_publish_robot_jog", fake_publish)
    monkeypatch.setattr(dashboard, "_publish_robot_hard_stop", fake_hard_stop)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(
            f"{base_url}/api/robot/jog",
            {"command": "hard_stop"},
            headers=_robot_headers(server),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert result["ok"] is True
    assert result["duration_s"] == 0.0
    assert jog_calls == []
    assert hard_stop_calls == ["192.168.12.1"]


def test_dashboard_robot_jog_rejects_unknown_command(tmp_path, monkeypatch) -> None:
    def fail_publish(*_: object) -> None:
        raise AssertionError("unknown commands must not publish")

    monkeypatch.setattr(dashboard, "_publish_robot_jog", fail_publish)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(
            f"{base_url}/api/robot/jog",
            {"command": "sprint"},
            headers=_robot_headers(server),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 400
    assert result["ok"] is False
    assert result["error"] == "unknown_robot_command"


def test_dashboard_robot_posture_wake_calls_posture_runner(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_posture(command: str, robot_ip: str) -> bool:
        calls.append((command, robot_ip))
        return True

    monkeypatch.setattr(dashboard, "_run_robot_posture", fake_posture)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(
            f"{base_url}/api/robot/posture",
            {"command": "wake", "robot_ip": "192.168.12.1"},
            headers=_robot_headers(server),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert result["ok"] is True
    assert result["command"] == "wake"
    assert "robot_ip" not in result
    assert calls == [("wake", "192.168.12.1")]


def test_dashboard_robot_posture_rejects_unknown_command(tmp_path, monkeypatch) -> None:
    def fail_posture(*_: object) -> bool:
        raise AssertionError("unknown posture commands must not run")

    monkeypatch.setattr(dashboard, "_run_robot_posture", fail_posture)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(
            f"{base_url}/api/robot/posture",
            {"command": "dance"},
            headers=_robot_headers(server),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 400
    assert result["ok"] is False
    assert result["error"] == "unknown_posture_command"


def test_dashboard_robot_go_to_calls_dimos_bridge(tmp_path, monkeypatch) -> None:
    calls: list[tuple[float, float]] = []

    def fake_go_to(x: float, y: float) -> dict[str, object]:
        calls.append((x, y))
        return {"transport": "dimos_mcp", "skill": "go_to"}

    monkeypatch.setattr(dashboard, "_run_robot_go_to", fake_go_to)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(
            f"{base_url}/api/robot/go_to",
            {"command": "go_to", "x": 1.25, "y": -0.5, "source": "map_click"},
            headers=_robot_headers(server),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert result["ok"] is True
    assert result["command"] == "go_to"
    assert result["source"] == "map_click"
    assert result["transport"] == "dimos_mcp"
    assert result["skill"] == "go_to"
    assert calls == [(1.25, -0.5)]


def test_dashboard_robot_go_to_rejects_bad_target(tmp_path, monkeypatch) -> None:
    def fail_go_to(*_: object) -> dict[str, object]:
        raise AssertionError("bad go_to targets must not run")

    monkeypatch.setattr(dashboard, "_run_robot_go_to", fail_go_to)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, result = _post_json(
            f"{base_url}/api/robot/go_to",
            {"command": "go_to", "x": "nan", "y": 0.0},
            headers=_robot_headers(server),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 400
    assert result["ok"] is False
    assert result["error"] == "invalid_go_to_target"


def test_dimos_mcp_call_command_prefers_configured_prefix(monkeypatch) -> None:
    monkeypatch.setenv("DOGOPS_DIMOS_MCP_CALL", "python -m dimos mcp call")

    command = dashboard._dimos_mcp_call_command("go_to", {"x": 1.0, "y": 2.0})

    assert command == [
        "python",
        "-m",
        "dimos",
        "mcp",
        "call",
        "go_to",
        "--json-args",
        '{"x":1.0,"y":2.0}',
    ]


def test_dimos_mcp_call_skill_treats_tool_error_as_failure(monkeypatch) -> None:
    class _Result:
        returncode = 0
        stdout = '{"ok":false,"error":"navigation_stream_unavailable"}'
        stderr = ""

    monkeypatch.setattr(dashboard.subprocess, "run", lambda *_, **__: _Result())
    monkeypatch.setattr(dashboard, "_dimos_mcp_call_command", lambda *_: ["dimos", "mcp"])

    with pytest.raises(RuntimeError, match="navigation_stream_unavailable"):
        dashboard._call_dimos_mcp_skill("go_to", {"x": 1.0, "y": 2.0})


@pytest.mark.parametrize(
    ("command", "linear_x", "linear_y", "angular_z"),
    [
        ("forward", 0.15, 0.0, 0.0),
        ("backward", -0.15, 0.0, 0.0),
        ("left", 0.0, 0.15, 0.0),
        ("right", 0.0, -0.15, 0.0),
        ("yaw_left", 0.0, 0.0, 0.35),
        ("yaw_right", 0.0, 0.0, -0.35),
        ("hard_stop", 0.0, 0.0, 0.0),
        ("stop", 0.0, 0.0, 0.0),
    ],
)
def test_dashboard_robot_jog_command_caps(
    command: str,
    linear_x: float,
    linear_y: float,
    angular_z: float,
) -> None:
    assert dashboard.ROBOT_JOG_COMMANDS[command] == (linear_x, linear_y, angular_z)


def test_robot_motion_session_uses_sport_move_for_linear_jog(monkeypatch) -> None:
    monkeypatch.setattr(dashboard, "HARD_STOP_REPEATS", 1)
    session = object.__new__(dashboard._RobotMotionSession)
    session.lock = threading.RLock()
    session.mode = "connected"
    sport_calls: list[str] = []
    move_calls: list[tuple[float, float, float]] = []
    joystick_calls: list[dict[str, float | int]] = []
    obstacle_calls: list[bool] = []
    session.connection = type(
        "FakeConnection",
        (),
        {"set_obstacle_avoidance": lambda self, enabled: obstacle_calls.append(enabled)},
    )()

    session._sport = sport_calls.append
    session._sport_move = lambda x, y, z: move_calls.append((x, y, z))
    session._send_joystick = lambda data: joystick_calls.append(data)
    session._wait_pose = lambda: (0.0, 0.0, 0.0)

    result = session.jog(0.15, 0.0, 0.0, 0.0)

    assert obstacle_calls == [False, True]
    assert sport_calls == ["BalanceStand", "StopMove"]
    assert session.mode == "balance"
    assert move_calls == [(0.15, 0.0, 0.0)]
    assert joystick_calls == [{"lx": 0, "ly": 0, "rx": 0, "ry": 0}]
    assert result["observed"] is True


def test_robot_motion_session_uses_sport_move_for_yaw_jog(monkeypatch) -> None:
    monkeypatch.setattr(dashboard, "HARD_STOP_REPEATS", 1)
    session = object.__new__(dashboard._RobotMotionSession)
    session.lock = threading.RLock()
    session.mode = "connected"
    sport_calls: list[str] = []
    move_calls: list[tuple[float, float, float]] = []
    joystick_calls: list[dict[str, float | int]] = []

    session._sport = sport_calls.append
    session._sport_move = lambda x, y, z: move_calls.append((x, y, z))
    session._send_joystick = lambda data: joystick_calls.append(data)
    session._wait_pose = lambda: (0.0, 0.0, 0.0)

    session.jog(0.0, 0.0, 0.30, 0.0)

    assert sport_calls == ["BalanceStand", "StopMove"]
    assert session.mode == "balance"
    assert move_calls == [(0.0, 0.0, 0.30)]
    assert joystick_calls == [{"lx": 0, "ly": 0, "rx": 0, "ry": 0}]


def test_robot_motion_session_sport_move_builds_native_go2_request() -> None:
    session = object.__new__(dashboard._RobotMotionSession)
    session.rtc_topic = {"SPORT_MOD": "rt/api/sport/request"}
    session.sport_cmd = {"Move": 1008}
    requests: list[tuple[str, dict[str, object]]] = []
    session._request = lambda topic, data: requests.append((topic, data))

    session._sport_move(0.15, -0.1, 0.3)

    assert requests == [
        (
            "rt/api/sport/request",
            {"api_id": 1008, "parameter": {"x": 0.15, "y": -0.1, "z": 0.3}},
        )
    ]


def test_robot_motion_session_hard_stop_uses_stopmove_and_zero_joystick(monkeypatch) -> None:
    monkeypatch.setattr(dashboard, "HARD_STOP_REPEATS", 1)
    session = object.__new__(dashboard._RobotMotionSession)
    session.lock = threading.RLock()
    sport_calls: list[str] = []
    joystick_calls: list[dict[str, float | int]] = []
    session._sport = sport_calls.append
    session._send_joystick = lambda data: joystick_calls.append(data)

    session.hard_stop()

    assert sport_calls == ["StopMove"]
    assert joystick_calls == [{"lx": 0, "ly": 0, "rx": 0, "ry": 0}]


def test_response_status_code_extracts_go2_sport_response() -> None:
    response = {
        "type": "res",
        "topic": "rt/api/sport/response",
        "data": {"header": {"identity": {"api_id": 1008}}, "status": {"code": 0}},
    }

    assert dashboard._response_status_code(response) == 0
    assert dashboard._response_status_code({"data": {"status": {"code": 3203}}}) == 3203
    assert dashboard._response_status_code({}) is None
