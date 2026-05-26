from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Any


def render_dashboard_html(
    state: dict[str, Any],
    report: dict[str, Any],
    *,
    robot_control_token: str | None = None,
) -> str:
    run = state["run"]
    nav = report.get("nav_summary") or {}
    packages = report.get("packages") or []
    incidents = report.get("incidents") or []
    work_orders = report.get("work_orders") or []
    what_changed = report.get("what_changed") or []
    packages_metric = f"{report['packages_observed']}/{report['packages_expected']}"
    nav_metric = f"{nav.get('waypoints_reached', 0)}/{nav.get('waypoints_total', 0)}"
    tag_recovery_metric = (
        f"{nav.get('tag_reacquisition_successes', 0)}/"
        f"{nav.get('tag_reacquisition_attempts', 0)}"
    )
    mean_target_time_metric = f"{nav.get('mean_elapsed_s', 0):.1f}s"
    route_coverage_metric = f"{float(nav.get('route_coverage', 0.0)) * 100:.0f}%"
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
    h2 {{ font-size: 15px; margin-bottom: 10px; }}
    main {{
      padding: 22px 28px 32px;
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 16px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .wide {{ grid-column: 1 / -1; }}
    .metric-row {{
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 10px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      background: #fbfcfd;
    }}
    .metric strong {{ display: block; font-size: 20px; }}
    .muted {{ color: var(--muted); }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 6px; text-align: left; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .state-resolved, .state-verified_closed, .state-found_ok {{ color: var(--accent); font-weight: 700; }}
    .state-open, .state-missing {{ color: var(--danger); font-weight: 700; }}
    .severity-P1 {{ color: var(--danger); font-weight: 700; }}
    .timeline {{ display: grid; gap: 8px; }}
    .timeline div {{ border-left: 3px solid var(--accent); padding-left: 10px; }}
    .robot-controls {{
      display: grid;
      grid-template-columns: repeat(3, minmax(72px, 1fr));
      gap: 8px;
      max-width: 360px;
    }}
    .posture-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }}
    .posture-controls button {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      color: var(--ink);
      cursor: pointer;
      font: inherit;
      min-height: 38px;
      padding: 8px 12px;
    }}
    .posture-controls button:hover {{ border-color: var(--accent); }}
    .posture-controls button:disabled {{ cursor: wait; opacity: 0.65; }}
    .motion-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
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
      min-height: 42px;
      padding: 8px 10px;
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
      min-height: 20px;
      margin-top: 10px;
      color: var(--muted);
    }}
    .robot-status.error {{ color: var(--danger); }}
    .robot-status.ok {{ color: var(--accent); }}
    @media (max-width: 900px) {{
      header {{ align-items: start; flex-direction: column; }}
      main {{ grid-template-columns: 1fr; padding: 14px; }}
      .metric-row {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
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
    <section class="wide">
      <h2>Run Summary</h2>
      <div class="metric-row">
        {metric("Packages", packages_metric)}
        {metric("Manifest Exceptions", report["manifest_exceptions"])}
        {metric("Incidents", report["incidents_opened"])}
        {metric("Verified Work Orders", report["work_orders_verified_closed"])}
        {metric("Nav", nav_metric)}
      </div>
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
    <section class="wide">
      <h2>Robot Control</h2>
      <div class="posture-controls" data-posture-controls>
        <button type="button" data-posture="wake">Wake / Stand</button>
        <button type="button" data-posture="balance">Balance</button>
        <button type="button" data-posture="sleep">Sleep</button>
      </div>
      <div class="motion-controls" data-motion-controls>
        <button type="button" data-motion="nudge" aria-pressed="true">Nudge</button>
        <button type="button" data-motion="step" aria-pressed="false">Step</button>
        <button type="button" data-motion="walk" aria-pressed="false">Walk</button>
      </div>
      <div class="robot-controls" data-robot-controls>
        <span></span>
        <button type="button" data-command="forward">Forward</button>
        <span></span>
        <button type="button" data-command="left">Left</button>
        <button type="button" class="hard-stop" data-command="hard_stop">HARD STOP</button>
        <button type="button" data-command="right">Right</button>
        <button type="button" data-command="yaw_left">Yaw L</button>
        <button type="button" data-command="backward">Back</button>
        <button type="button" data-command="yaw_right">Yaw R</button>
      </div>
      <div class="robot-status" data-robot-status>Idle</div>
    </section>
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
  </main>
  <script>
    (() => {{
      const controls = document.querySelector("[data-robot-controls]");
      const postureControls = document.querySelector("[data-posture-controls]");
      const motionControls = document.querySelector("[data-motion-controls]");
      const status = document.querySelector("[data-robot-status]");
      if (!controls || !status) return;
      let motionProfile = "nudge";
      const robotControlToken = {json.dumps(robot_control_token)};
      const buttons = Array.from(document.querySelectorAll("[data-command], [data-posture], [data-motion]"));
      const setBusy = (busy) => buttons.forEach((button) => {{ button.disabled = busy; }});
      const setStatus = (text, state) => {{
        status.textContent = text;
        status.className = `robot-status ${{state || ""}}`;
      }};
      const sendRobotAction = async (url, body, successText) => {{
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
        }} catch (error) {{
          setStatus(`Robot command failed: ${{error.message}}`, "error");
        }} finally {{
          setBusy(false);
        }}
      }};
      controls.addEventListener("click", async (event) => {{
        const button = event.target.closest("button[data-command]");
        if (!button) return;
        const command = button.getAttribute("data-command");
        const motionText = (result) => {{
          if (command === "hard_stop") return "Hard stop sent";
          if (!result.observed) return `Sent ${{command}}`;
          const distanceCm = Math.round((result.observed_distance_m || 0) * 1000) / 10;
          const yawDeg = Math.round(Math.abs(result.observed_dyaw_rad || 0) * 1800 / Math.PI) / 10;
          if (distanceCm >= 0.5) return `Sent ${{command}} / observed ${{distanceCm}} cm`;
          if (yawDeg >= 0.5) return `Sent ${{command}} / observed ${{yawDeg}} deg`;
          return `Sent ${{command}} / no clear odom movement`;
        }};
        await sendRobotAction(
          "/api/robot/jog",
          {{command, profile: motionProfile}},
          motionText
        );
      }});
      if (motionControls) {{
        motionControls.addEventListener("click", (event) => {{
          const button = event.target.closest("button[data-motion]");
          if (!button) return;
          motionProfile = button.getAttribute("data-motion") || "nudge";
          motionControls.querySelectorAll("[data-motion]").forEach((item) => {{
            item.setAttribute("aria-pressed", item === button ? "true" : "false");
          }});
        }});
      }}
      if (postureControls) {{
        postureControls.addEventListener("click", async (event) => {{
          const button = event.target.closest("button[data-posture]");
          if (!button) return;
          const command = button.getAttribute("data-posture");
          await sendRobotAction(
            "/api/robot/posture",
            {{command}},
            () => command === "wake" ? "Wake / stand complete" : `Sent ${{command}}`
          );
        }});
      }}
    }})();
  </script>
</body>
</html>
"""


def metric(label: str, value: object) -> str:
    return (
        '<div class="metric">'
        f"<span class=\"muted\">{escape(label)}</span>"
        f"<strong>{escape(str(value))}</strong>"
        "</div>"
    )


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


def write_dashboard_html(run_dir: str | Path, *, robot_control_token: str | None = None) -> Path:
    root = Path(run_dir)
    state = _read_json(root / "state.json")
    report = _read_json(root / "report.json")
    html_path = root / "dashboard.html"
    html_path.write_text(
        render_dashboard_html(state, report, robot_control_token=robot_control_token),
        encoding="utf-8",
    )
    return html_path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
