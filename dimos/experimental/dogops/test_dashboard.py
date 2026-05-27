from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Any
import urllib.request

import pytest

from dimos.experimental.dogops import dashboard
from dimos.experimental.dogops.dashboard import DogOpsDashboardModule, make_dashboard_server
from dimos.experimental.dogops.dashboard_static import dimos_viewer_urls, write_dashboard_html
from dimos.experimental.dogops.mission_engine import run_offline_simulation
from dimos.experimental.dogops.store import DogOpsStore


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
    assert "PKG-104" in content
    assert "INC-001" in content
    assert "Live Inspection Console" in content
    assert "Needs Attention" in content
    assert "Machine Readings" in content
    assert "Floor Changes" in content
    assert "Inspection points" in content
    assert "<span>Mode</span><strong>Real dog</strong>" in content
    assert 'data-map-viewer' in content
    assert 'data-rerun-source-url="rerun+http://127.0.0.1:9877/proxy"' in content
    assert 'data-rerun-view-mode="dogops-2d"' in content
    assert 'data-rerun-embed-url=""' in content
    assert "DimOS/Rerun top-down map" in content
    assert 'data-rerun-module-url="/assets/rerun-web-viewer.js"' in content
    assert 'data-rerun-asset-base-url="/assets/vendor/@rerun-io/web-viewer/"' in content
    assert 'data-rerun-canvas' in content
    assert 'data-viewer-offline' in content
    assert 'class="map-target-overlay" data-route-map' in content
    assert "data-viewer-offline data-route-map" not in content
    assert "Offline map artifact" in content
    assert "Inspection Evidence" in content
    assert 'data-route-action="explore"' in content
    assert 'data-route-action="stop-explore"' in content
    assert 'data-route-action="replay-map"' in content
    assert "Inspection points (3/3)" in content
    assert 'data-route-action="add-inspection"' in content
    assert 'data-route-action="clear-inspection"' in content
    assert 'data-route-action="add-waypoint"' not in content
    assert 'data-route-action="add-poi"' not in content
    assert 'data-map-click-mode="inspection"' in content
    assert 'data-map-click-mode="waypoint"' not in content
    assert 'data-map-click-mode="poi"' not in content
    assert "dogops:map-click-mode" in content
    assert "Rerun WebViewer unavailable; showing offline map artifact." in Path(
        "dimos/experimental/dogops/static/rerun-web-viewer.js"
    ).read_text(encoding="utf-8")
    assert 'data-map-target-id="COOLING_1"' in content
    assert "/evidence/" in content
    assert "Navigation Eval" in content
    assert "Robot Control" in content
    assert "Real dog" in content
    assert 'data-command="forward"' in content
    assert 'data-command="hard_stop"' in content
    assert 'data-posture="wake"' in content
    assert 'data-posture="sleep"' in content
    assert 'data-motion="nudge"' in content
    assert 'data-motion="step"' in content
    assert 'data-motion="walk"' in content
    assert "X-DogOps-Control-Token" in content


def test_dashboard_static_html_surfaces_planned_route_before_run(tmp_path) -> None:
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    store = DogOpsStore.load_existing(run_dir)
    state = store.state
    assert state is not None
    state.nav_events = []
    state.nav_summary.waypoints_total = 0
    state.nav_summary.waypoints_reached = 0
    store.write_state(state.run.id)
    store.write_report(state.run.id)
    write_dashboard_html(run_dir)

    content = (run_dir / "dashboard.html").read_text(encoding="utf-8")

    assert "<span>Route</span><strong>6 planned</strong>" in content


def test_dashboard_rerun_sim_mode_keeps_rerun_as_primary_map(tmp_path) -> None:
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)

    html_path = write_dashboard_html(run_dir, runtime_mode="rerun-sim")
    content = html_path.read_text(encoding="utf-8")

    assert "<span>Mode</span><strong>Rerun sim</strong>" in content
    assert "Offline map artifact." in content
    assert 'if (dogopsRuntimeMode === "offline")' in content
    assert 'data-rerun-canvas' in content
    assert 'data-viewer-offline hidden' in content


def test_dashboard_viewer_urls_default_local_and_remote_gated(monkeypatch) -> None:
    monkeypatch.setenv("DOGOPS_RERUN_SOURCE_URL", "rerun+http://10.0.0.5:9877/proxy")
    monkeypatch.setenv("DOGOPS_RERUN_WEB_VIEWER_MODULE_URL", "https://cdn.example/viewer.js")
    monkeypatch.setenv("DOGOPS_RERUN_WEB_VIEWER_ASSET_BASE_URL", "https://cdn.example/assets/")
    monkeypatch.setenv("DOGOPS_COMMAND_CENTER_URL", "http://10.0.0.5:7779/command-center")
    monkeypatch.setenv("DOGOPS_RERUN_EMBED_URL", "http://10.0.0.5:9878")

    assert dimos_viewer_urls() == {
        "rerun_source": "rerun+http://127.0.0.1:9877/proxy",
        "web_viewer_module": "/assets/rerun-web-viewer.js",
        "web_viewer_asset_base": "/assets/vendor/@rerun-io/web-viewer/",
        "command_center": "http://127.0.0.1:7779/command-center",
        "rerun_view_mode": "dogops-2d",
        "rerun_embed": "",
    }

    monkeypatch.setenv("DOGOPS_ALLOW_REMOTE_VIEWER", "1")
    monkeypatch.setenv("DOGOPS_RERUN_VIEW_MODE", "native-3d")
    assert dimos_viewer_urls() == {
        "rerun_source": "rerun+http://10.0.0.5:9877/proxy",
        "web_viewer_module": "https://cdn.example/viewer.js",
        "web_viewer_asset_base": "https://cdn.example/assets/",
        "command_center": "http://10.0.0.5:7779/command-center",
        "rerun_view_mode": "native-3d",
        "rerun_embed": "http://10.0.0.5:9878",
    }


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
        site_map = _get_json(f"{base_url}/api/map")
        route = _get_json(f"{base_url}/api/route")
        poi = _get_json(f"{base_url}/api/poi")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert "DogOps SiteOps Agent" in html
    assert state["run"]["state"] == "done"  # type: ignore[index]
    assert report["manifest_exceptions"] == 2
    assert nav["waypoints_reached"] == 4
    assert site_map["status"] == "mapped"
    assert site_map["dimos_schema"] == "dimos.web.websocket_vis.v1"
    assert site_map["dimos_costmap"]["type"] == "costmap"  # type: ignore[index]
    assert site_map["dimos_path"]["type"] == "path"  # type: ignore[index]
    assert site_map["robot_pose"]["source"] in {"nav_event", "dimos_odom"}  # type: ignore[index]
    assert len(route["waypoints"]) >= 5  # type: ignore[arg-type]
    assert len(poi["captures"]) == 3  # type: ignore[arg-type]


def test_dashboard_route_editor_mutates_local_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DOGOPS_RUNTIME_MODE", "offline")
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        map_status, map_result = _post_json(f"{base_url}/api/map/explore", {})
        replay_status, replay_result = _post_json(f"{base_url}/api/rerun/replay_map", {})
        clear_status, clear_result = _post_json(f"{base_url}/api/route/inspection_points/clear", {})
        first_status, first_result = _post_json(
            f"{base_url}/api/route/inspection_points",
            {"target_id": "COOLING_1"},
        )
        duplicate_status, duplicate_result = _post_json(
            f"{base_url}/api/route/inspection_points",
            {"target_id": "COOLING_1"},
        )
        second_status, second_result = _post_json(
            f"{base_url}/api/route/inspection_points",
            {"target_id": "TEMP_1"},
        )
        third_status, third_result = _post_json(
            f"{base_url}/api/route/inspection_points",
            {"target_id": "QA_HOLD"},
        )
        limit_status, limit_result = _post_json(
            f"{base_url}/api/route/inspection_points",
            {"target_id": "INBOUND_DOCK"},
        )
        run_status, run_result = _post_json(f"{base_url}/api/route/run", {})
        poi = _get_json(f"{base_url}/api/poi")
        rerun_command = json.loads((run_dir / "rerun_command.json").read_text(encoding="utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert map_status == 200
    assert map_result["map"]["status"] == "mapped"  # type: ignore[index]
    assert map_result["rerun"]["action"] == "replay_mapping"  # type: ignore[index]
    assert replay_status == 200
    assert replay_result["rerun"]["action"] == "replay_mapping"  # type: ignore[index]
    assert clear_status == 200
    assert clear_result["inspection_points"] == 0
    assert first_status == 200
    assert first_result["inspection_points"] == 1
    assert duplicate_status == 200
    assert duplicate_result["inspection_points"] == 1
    assert second_status == 200
    assert second_result["inspection_points"] == 2
    assert third_status == 200
    assert third_result["inspection_points"] == 3
    assert limit_status == 400
    assert limit_result["error"] == "inspection_point_limit"
    assert run_status == 200
    assert run_result["captures"] == 3
    assert run_result["rerun"]["action"] == "replay_route"  # type: ignore[index]
    assert rerun_command["action"] == "replay_route"
    assert len(poi["readings"]) >= 4  # type: ignore[arg-type]


def test_dashboard_simulation_runtime_dispatches_dimos_controls(tmp_path, monkeypatch) -> None:
    events: list[tuple[str, dict[str, Any] | None]] = []

    def fake_emit(event: str, data: dict[str, Any] | None = None) -> dict[str, object]:
        events.append((event, data))
        return {"event": event, "data": data, "sent": True}

    monkeypatch.setenv("DOGOPS_RUNTIME_MODE", "simulation")
    monkeypatch.setattr(dashboard, "_emit_dimos_socket_event", fake_emit)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        explore_status, explore_result = _post_json(f"{base_url}/api/map/explore", {})
        stop_status, stop_result = _post_json(f"{base_url}/api/map/stop_explore", {})
        jog_status, jog_result = _post_json(
            f"{base_url}/api/robot/jog",
            {"command": "hard_stop"},
            headers=_robot_headers(server),
        )
        posture_status, posture_result = _post_json(
            f"{base_url}/api/robot/posture",
            {"command": "sleep"},
            headers=_robot_headers(server),
        )
        run_status, run_result = _post_json(f"{base_url}/api/route/run", {})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert explore_status == 200
    assert explore_result["mode"] == "simulation"
    assert explore_result["map"]["status"] == "mapping"  # type: ignore[index]
    assert stop_status == 200
    assert stop_result["mode"] == "simulation"
    assert jog_status == 200
    assert jog_result["mode"] == "simulation"
    assert posture_status == 200
    assert posture_result["mode"] == "simulation"
    assert run_status == 200
    assert run_result["mode"] == "simulation"
    assert [event for event, _ in events].count("start_explore") == 1
    assert [event for event, _ in events].count("stop_explore") == 1
    assert [event for event, _ in events].count("move_command") >= 2
    assert [event for event, _ in events].count("click") >= 1


def test_dashboard_rerun_sim_runtime_uses_replay_without_dimos_control(tmp_path, monkeypatch) -> None:
    def fail_emit(event: str, data: dict[str, Any] | None = None) -> dict[str, object]:
        raise AssertionError(f"rerun-sim mode must not emit DimOS socket event {event}: {data}")

    monkeypatch.setenv("DOGOPS_RUNTIME_MODE", "rerun-sim")
    monkeypatch.setattr(dashboard, "_emit_dimos_socket_event", fail_emit)
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)
    server = make_dashboard_server(run_dir, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        explore_status, explore_result = _post_json(f"{base_url}/api/map/explore", {})
        stop_status, stop_result = _post_json(f"{base_url}/api/map/stop_explore", {})
        run_status, run_result = _post_json(f"{base_url}/api/route/run", {})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert explore_status == 200
    assert explore_result["mode"] == "rerun-sim"
    assert explore_result["rerun"]["action"] == "replay_mapping"  # type: ignore[index]
    assert stop_status == 200
    assert stop_result["mode"] == "rerun-sim"
    assert run_status == 200
    assert run_result["mode"] == "rerun-sim"
    assert run_result["rerun"]["action"] == "replay_route"  # type: ignore[index]


def test_dimos_control_url_rejects_remote_by_default(monkeypatch) -> None:
    monkeypatch.setenv("DOGOPS_DIMOS_CONTROL_URL", "http://10.0.0.5:7779")
    monkeypatch.delenv("DOGOPS_ALLOW_REMOTE_VIEWER", raising=False)

    with pytest.raises(ValueError, match="loopback"):
        dashboard._dimos_control_url()

    monkeypatch.setenv("DOGOPS_ALLOW_REMOTE_VIEWER", "1")
    assert dashboard._dimos_control_url() == "http://10.0.0.5:7779"


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
    assert result["linear_x"] == pytest.approx(0.2025)
    assert result["duration_s"] == 1.2
    assert calls == [(0.2025, 0.0, 0.0, 1.2, "192.168.12.1")]


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


@pytest.mark.parametrize(
    ("command", "linear_x", "linear_y", "angular_z"),
    [
        ("forward", 0.15, 0.0, 0.0),
        ("backward", -0.15, 0.0, 0.0),
        ("left", 0.0, 0.15, 0.0),
        ("right", 0.0, -0.15, 0.0),
        ("yaw_left", 0.0, 0.0, 0.30),
        ("yaw_right", 0.0, 0.0, -0.30),
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
