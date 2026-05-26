from __future__ import annotations

import json
import threading
import urllib.request

from dimos.experimental.dogops.dashboard import DogOpsDashboardModule, make_dashboard_server
from dimos.experimental.dogops.dashboard_static import write_dashboard_html
from dimos.experimental.dogops.mission_engine import run_offline_simulation


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def test_dashboard_static_html_contains_closed_loop_result(tmp_path) -> None:
    run_dir = tmp_path / "latest"
    run_offline_simulation(out=run_dir)

    html_path = write_dashboard_html(run_dir)
    content = html_path.read_text(encoding="utf-8")

    assert "DogOps SiteOps Agent" in content
    assert "PKG-104" in content
    assert "INC-001" in content
    assert "Navigation Eval" in content


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
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert "DogOps SiteOps Agent" in html
    assert state["run"]["state"] == "done"  # type: ignore[index]
    assert report["manifest_exceptions"] == 2
    assert nav["waypoints_reached"] == 4
