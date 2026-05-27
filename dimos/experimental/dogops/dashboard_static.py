from __future__ import annotations

from html import escape
import json
import math
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dimos.experimental.dogops.mapping import decode_dimos_costmap_full


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
    site_map = state.get("site_map") or {}
    route_plan = state.get("route_plan") or {}
    poi_captures = report.get("poi_captures") or []
    sensor_readings = report.get("sensor_readings") or []
    what_changed = report.get("what_changed") or []
    open_incidents = [incident for incident in incidents if str(incident.get("state")) != "resolved"]
    reading_alerts = [
        reading
        for reading in sensor_readings
        if str(reading.get("status", "")).lower() not in {"normal", "ok", "clear", "pass"}
    ]
    target_options = _target_options(state)
    packages_metric = f"{report['packages_observed']}/{report['packages_expected']}"
    nav_metric = f"{nav.get('waypoints_reached', 0)}/{nav.get('waypoints_total', 0)}"
    tag_recovery_metric = (
        f"{nav.get('tag_reacquisition_successes', 0)}/"
        f"{nav.get('tag_reacquisition_attempts', 0)}"
    )
    mean_target_time_metric = f"{nav.get('mean_elapsed_s', 0):.1f}s"
    route_coverage_metric = f"{float(nav.get('route_coverage', 0.0)) * 100:.0f}%"
    coverage_metric = f"{float(site_map.get('coverage_ratio', 0.0)) * 100:.0f}%"
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
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    h1, h2 {{ margin: 0; }}
    h1 {{ font-size: 22px; font-weight: 700; letter-spacing: 0; }}
    h2 {{ font-size: 15px; margin-bottom: 10px; }}
    main {{
      padding: 22px 28px 32px;
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 16px;
      max-width: 1680px;
      margin: 0 auto;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      overflow-wrap: anywhere;
      min-width: 0;
    }}
    .wide {{ grid-column: 1 / -1; }}
    .status-strip {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }}
    .status-pill {{
      min-width: 92px;
      border: 1px solid rgba(255, 255, 255, 0.20);
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.08);
      padding: 6px 8px;
    }}
    .status-pill span {{
      display: block;
      color: #cbd5e1;
      font-size: 11px;
      text-transform: uppercase;
    }}
    .status-pill strong {{
      display: block;
      color: #ffffff;
      font-size: 15px;
    }}
    .operator-console {{
      padding: 0;
      overflow: hidden;
    }}
    .console-header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 14px;
      align-items: start;
      border-bottom: 1px solid var(--line);
      padding: 12px 14px;
    }}
    .console-header p {{
      margin: 4px 0 0;
      color: var(--muted);
    }}
    .console-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(340px, 440px);
      gap: 0;
      align-items: stretch;
    }}
    .map-stage {{
      min-width: 0;
      border-right: 1px solid var(--line);
      background: #070b12;
    }}
    .ops-panel {{
      display: grid;
      align-content: start;
      gap: 12px;
      padding: 14px;
      min-width: 0;
      background: #fbfcfd;
      height: clamp(620px, 72vh, 760px);
      overflow: auto;
    }}
    .panel-block {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 12px;
      min-width: 0;
    }}
    .panel-block h3 {{
      margin: 0 0 8px;
      font-size: 13px;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .attention-list,
    .change-list,
    .route-stepper,
    .reading-cards {{
      display: grid;
      gap: 8px;
    }}
    .attention-item,
    .reading-card,
    .route-step,
    .change-item {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfd;
      padding: 9px;
      min-width: 0;
    }}
    .attention-item.open,
    .reading-card.alert {{
      border-color: #fecaca;
      background: #fff7f7;
    }}
    .attention-item strong,
    .reading-card strong,
    .route-step strong {{
      display: block;
    }}
    .reading-value {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: baseline;
    }}
    .secondary-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 16px;
    }}
    .metric-row {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
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
    table {{ border-collapse: collapse; table-layout: fixed; width: 100%; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 6px; text-align: left; }}
    td, th, li, p {{ overflow-wrap: anywhere; }}
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
    .map-workspace {{
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.65fr);
      gap: 14px;
      align-items: start;
    }}
    .map-viewer {{
      position: relative;
      width: 100%;
      height: clamp(620px, 72vh, 760px);
      min-height: 0;
      border: 1px solid #101827;
      border-radius: 0;
      background: #070b12;
      overflow: hidden;
    }}
    .rerun-canvas {{
      width: 100%;
      height: 100%;
      display: block;
      background: #070b12;
    }}
    .rerun-canvas[hidden] {{ display: none; }}
    .rerun-canvas canvas {{
      width: 100%;
      height: 100%;
      display: block;
    }}
    .viewer-offline {{
      position: absolute;
      inset: 0;
      display: grid;
      align-items: stretch;
      background: #070b12;
    }}
    .viewer-offline[hidden] {{ display: none; }}
    .viewer-offline .map-viz {{
      border: 0;
      border-radius: 0;
      min-height: 100%;
    }}
    .viewer-offline svg {{
      width: 100%;
      height: 100%;
      display: block;
    }}
    .viewer-offline [data-map-target-id] {{
      cursor: pointer;
    }}
    .viewer-offline .map-target-hit {{
      pointer-events: all;
    }}
    .viewer-offline [data-map-target-id]:hover circle {{
      stroke: #111827;
      stroke-width: 3;
    }}
    .map-target-overlay {{
      position: absolute;
      inset: 0;
      z-index: 2;
      pointer-events: none;
    }}
    .map-target-overlay [data-map-target-id] {{
      position: absolute;
      width: 24px;
      height: 24px;
      transform: translate(-50%, -50%);
      border: 2px solid rgba(248, 250, 252, 0.92);
      border-radius: 50%;
      background: rgba(15, 118, 110, 0.80);
      box-shadow: 0 0 0 4px rgba(15, 118, 110, 0.16);
      cursor: crosshair;
      pointer-events: auto;
    }}
    .map-target-overlay [data-map-target-id]:hover,
    .map-target-overlay [data-map-target-id]:focus-visible {{
      outline: 0;
      border-color: #5eead4;
      box-shadow: 0 0 0 5px rgba(94, 234, 212, 0.25);
    }}
    .map-target-overlay [data-map-target-id].is-poi {{
      background: rgba(180, 83, 9, 0.90);
      box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.18);
    }}
    .map-target-overlay [data-map-target-id] span {{
      position: absolute;
      top: -6px;
      left: 20px;
      max-width: 122px;
      border: 1px solid rgba(255, 255, 255, 0.24);
      border-radius: 5px;
      background: rgba(7, 11, 18, 0.82);
      color: #f8fafc;
      font-size: 11px;
      font-weight: 700;
      line-height: 1.1;
      overflow: hidden;
      padding: 3px 5px;
      opacity: 0;
      pointer-events: none;
      transform: translateX(-4px);
      transition: opacity 140ms ease, transform 140ms ease;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .map-target-overlay [data-map-target-id]:hover span,
    .map-target-overlay [data-map-target-id]:focus-visible span {{
      opacity: 1;
      transform: translateX(0);
    }}
    .map-toolbar {{
      position: absolute;
      z-index: 2;
      top: 10px;
      left: 10px;
      right: 10px;
      display: flex;
      justify-content: space-between;
      gap: 10px;
      pointer-events: none;
    }}
    .viewer-chip,
    .viewer-links a {{
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      border: 1px solid rgba(255, 255, 255, 0.22);
      border-radius: 6px;
      background: rgba(7, 11, 18, 0.82);
      color: #f8fafc;
      font-size: 12px;
      padding: 6px 9px;
      text-decoration: none;
      pointer-events: auto;
    }}
    .viewer-links {{
      display: flex;
      gap: 8px;
    }}
    .viewer-hint {{
      position: absolute;
      z-index: 2;
      left: 10px;
      right: 10px;
      bottom: 10px;
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: #e5e7eb;
      font-size: 12px;
      pointer-events: none;
    }}
    .viewer-hint span {{
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 6px;
      background: rgba(7, 11, 18, 0.78);
      padding: 6px 8px;
    }}
    .viewer-hint [data-state="ok"] {{ color: #5eead4; }}
    .viewer-hint [data-state="error"] {{ color: #fecaca; }}
    .map-route-overlay {{
      position: absolute;
      z-index: 3;
      top: 52px;
      left: 10px;
      width: min(390px, calc(100% - 20px));
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 8px;
      background: rgba(7, 11, 18, 0.78);
      color: #f8fafc;
      padding: 10px;
      backdrop-filter: blur(10px);
    }}
    .map-route-overlay label {{
      display: block;
      margin-bottom: 6px;
      color: #cbd5e1;
      font-size: 12px;
    }}
    .map-route-overlay .route-status {{
      color: #cbd5e1;
      margin-top: 6px;
    }}
    .map-route-overlay .route-status.error {{ color: #fecaca; }}
    .map-route-overlay .route-status.ok {{ color: #5eead4; }}
    .map-click-modes {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 8px;
    }}
    .map-click-modes button[aria-pressed="true"] {{
      background: #dff6f1;
      border-color: #5eead4;
      color: #0f766e;
      font-weight: 700;
    }}
    .map-click-hint {{
      margin-top: 6px;
      min-height: 18px;
      color: #cbd5e1;
      font-size: 12px;
    }}
    .map-click-hint.error {{ color: #fecaca; }}
    .map-click-hint.ok {{ color: #5eead4; }}
    .robot-dock {{
      position: absolute;
      z-index: 3;
      right: 10px;
      bottom: 54px;
      width: min(320px, calc(100% - 20px));
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 8px;
      background: rgba(7, 11, 18, 0.80);
      color: #f8fafc;
      padding: 8px;
      backdrop-filter: blur(10px);
    }}
    .robot-dock-bar {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
    }}
    .robot-dock strong {{
      display: block;
      font-size: 13px;
    }}
    .robot-dock summary {{
      cursor: pointer;
      font-weight: 700;
      margin: 8px 0;
    }}
    .robot-dock .robot-status {{
      color: #cbd5e1;
      display: block;
      font-size: 12px;
      min-height: 18px;
    }}
    .robot-dock .robot-status.error {{ color: #fecaca; }}
    .robot-dock .robot-status.ok {{ color: #5eead4; }}
    .robot-dock .hard-stop {{
      background: var(--danger);
      border-color: var(--danger);
      color: #ffffff;
      font-weight: 700;
      min-width: 92px;
    }}
    .offline-snapshot {{
      margin-top: 10px;
      color: var(--muted);
    }}
    .offline-snapshot summary {{
      cursor: pointer;
      margin-bottom: 8px;
    }}
    .map-viz {{
      width: 100%;
      min-height: 300px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f8fafc;
      overflow: hidden;
    }}
    .route-tools {{
      display: grid;
      gap: 10px;
      min-width: 0;
    }}
    .route-controls {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}
    .route-controls select,
    .route-controls button {{
      min-height: 38px;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--ink);
      font: inherit;
      padding: 8px 10px;
    }}
    .map-route-overlay .route-controls select,
    .map-route-overlay .route-controls button,
    .robot-dock button {{
      background: rgba(255, 255, 255, 0.94);
    }}
    .route-controls select {{ grid-column: 1 / -1; width: 100%; }}
    .route-controls button {{ cursor: pointer; }}
    .route-controls button:hover {{ border-color: var(--accent); }}
    .route-status {{ min-height: 20px; color: var(--muted); }}
    .route-status.error {{ color: var(--danger); }}
    .route-status.ok {{ color: var(--accent); }}
    .evidence-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }}
    .evidence-item {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfcfd;
    }}
    .evidence-item img {{
      width: 100%;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #e5e7eb;
    }}
    @media (max-width: 900px) {{
      header {{ align-items: start; flex-direction: column; }}
      main {{ grid-template-columns: 1fr; padding: 14px; }}
      .console-header {{ grid-template-columns: 1fr; }}
      .console-grid {{ grid-template-columns: 1fr; }}
      .map-stage {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .secondary-grid {{ grid-template-columns: 1fr; }}
      .metric-row {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .map-workspace {{ grid-template-columns: 1fr; }}
      .ops-panel {{ height: auto; max-height: none; }}
      .map-viewer, .rerun-canvas {{ min-height: 420px; height: 420px; }}
      .viewer-hint {{ flex-direction: column; }}
      .map-route-overlay,
      .robot-dock {{
        position: static;
        width: auto;
        margin: 10px;
      }}
      .route-controls {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>DogOps SiteOps Agent</h1>
      <div class="muted">Mission {escape(str(run["mission_id"]))} / run {escape(str(run["id"]))}</div>
    </div>
    <div class="status-strip">
      {status_pill("Run", humanize(run["state"]))}
      {status_pill("Packages", packages_metric)}
      {status_pill("Map", f"{escape(str(site_map.get('status', 'empty')))} / {coverage_metric}")}
      {status_pill("Open Issues", len(open_incidents))}
      {status_pill("Readings", f"{len(sensor_readings) - len(reading_alerts)}/{len(sensor_readings) or 1} normal")}
      {status_pill("Route", nav_metric)}
    </div>
  </header>
  <main>
    <section class="operator-console wide">
      <div class="console-header">
        <div>
          <h2>Live Inspection Console</h2>
          <p>Track machine readings, floor changes, route progress, and the live DimOS/Rerun map in one operator view.</p>
        </div>
      </div>
      <div class="console-grid">
        <div class="map-stage">
          {map_viewer_panel(site_map, route_plan, target_options)}
        </div>
        <aside class="ops-panel" aria-label="Inspection status">
          <div class="panel-block">
            <h3>Needs Attention</h3>
            {attention_list(open_incidents)}
          </div>
          <div class="panel-block">
            <h3>Machine Readings</h3>
            {reading_cards(sensor_readings)}
          </div>
          <div class="panel-block">
            <h3>Floor Changes</h3>
            {change_list(what_changed)}
          </div>
          <div class="panel-block">
            <h3>Route</h3>
            {route_stepper(route_plan)}
            {poi_stepper(route_plan)}
          </div>
        </aside>
      </div>
    </section>
    <section class="wide">
      <h2>Inspection Evidence</h2>
      {capture_grid(poi_captures)}
      {reading_table(sensor_readings)}
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
      const routeControls = document.querySelector("[data-route-controls]");
      const routeStatus = document.querySelector("[data-route-status]");
      const mapViewer = document.querySelector("[data-map-viewer]");
      if (mapViewer) {{
        const canvasHost = mapViewer.querySelector("[data-rerun-canvas]");
        const offline = mapViewer.querySelector("[data-viewer-offline]");
        const statusText = mapViewer.querySelector("[data-rerun-status]");
        const showFallback = (message) => {{
          if (canvasHost) canvasHost.hidden = true;
          if (offline) offline.hidden = false;
          if (statusText) {{
            statusText.textContent = message;
            statusText.dataset.state = "error";
          }}
        }};
        const moduleUrl = mapViewer.getAttribute("data-rerun-module-url");
        if (moduleUrl) {{
          import(moduleUrl).then((module) => {{
            if (!module.mountDogOpsRerunViewer) {{
              throw new Error("missing WebViewer mount");
            }}
            window.DogOpsRerunModule = module;
            return module.mountDogOpsRerunViewer(mapViewer);
          }}).catch((error) => {{
            showFallback(`Rerun WebViewer unavailable: ${{error.message}}`);
          }});
        }} else {{
          showFallback("Rerun WebViewer module is not configured.");
        }}
      }}
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
      if (routeControls && routeStatus) {{
        let mapClickMode = "";
        const select = routeControls.querySelector("[data-route-target]");
        const clickModeButtons = Array.from(routeControls.parentElement.querySelectorAll("[data-map-click-mode]"));
        const mapClickStatus = document.querySelector("[data-map-click-status]");
        const setRouteStatus = (text, state) => {{
          routeStatus.textContent = text;
          routeStatus.className = `route-status ${{state || ""}}`;
        }};
        const setMapClickStatus = (text, state) => {{
          if (!mapClickStatus) return;
          mapClickStatus.textContent = text;
          mapClickStatus.className = `map-click-hint ${{state || ""}}`;
        }};
        const setMapClickMode = (mode) => {{
          mapClickMode = mapClickMode === mode ? "" : mode;
          clickModeButtons.forEach((button) => {{
            button.setAttribute(
              "aria-pressed",
              button.getAttribute("data-map-click-mode") === mapClickMode ? "true" : "false",
            );
          }});
          setMapClickStatus(
            mapClickMode ? `${{mapClickMode}} placement active.` : "Map authoring idle.",
            "",
          );
        }};
        const routePost = async (url, body) => {{
          const response = await fetch(url, {{
            method: "POST",
            headers: {{"Content-Type": "application/json"}},
            body: JSON.stringify(body || {{}}),
          }});
          const result = await response.json();
          if (!response.ok || !result.ok) throw new Error(result.error || "route_failed");
          return result;
        }};
        const replayRerunMap = () => {{
          try {{
            window.sessionStorage.setItem("dogops:rerun-replay", "map");
          }} catch (_) {{
            // sessionStorage can be unavailable in stricter browser contexts.
          }}
          if (window.DogOpsRerunWebViewer && window.DogOpsRerunWebViewer.replay && mapViewer) {{
            window.DogOpsRerunWebViewer.replay(mapViewer);
          }}
        }};
        const routeTargetAction = async (mode, targetId) => {{
          if (!targetId) throw new Error("missing_target_id");
          if (select) select.value = targetId;
          if (mode === "waypoint") {{
            return routePost("/api/route/waypoints", {{target_id: targetId}});
          }}
          if (mode === "poi") {{
            return routePost("/api/route/pois", {{target_id: targetId}});
          }}
          throw new Error("unknown_map_mode");
        }};
        clickModeButtons.forEach((button) => {{
          button.addEventListener("click", () => {{
            setMapClickMode(button.getAttribute("data-map-click-mode") || "");
          }});
        }});
        const routeMap = document.querySelector("[data-route-map]");
        if (routeMap) {{
          routeMap.addEventListener("click", async (event) => {{
            if (!mapClickMode) return;
            const target = event.target.closest("[data-map-target-id]");
            if (!target) {{
              setMapClickStatus("No mapped target selected.", "error");
              return;
            }}
            const targetId = target.getAttribute("data-map-target-id");
            setRouteStatus(`Adding ${{mapClickMode}} ${{targetId}}...`, "");
            try {{
              await routeTargetAction(mapClickMode, targetId);
              setMapClickStatus(`Added ${{mapClickMode}} at ${{targetId}}.`, "ok");
              setRouteStatus("Route updated", "ok");
              window.setTimeout(() => window.location.reload(), 450);
            }} catch (error) {{
              setMapClickStatus(`Map edit failed: ${{error.message}}`, "error");
              setRouteStatus(`Route update failed: ${{error.message}}`, "error");
            }}
          }});
        }}
        routeControls.addEventListener("click", async (event) => {{
          const button = event.target.closest("button[data-route-action]");
          if (!button) return;
          const action = button.getAttribute("data-route-action");
          const targetId = select ? select.value : "";
          setRouteStatus(`Running ${{action}}...`, "");
          try {{
            if (action === "explore") {{
              await routePost("/api/map/explore", {{}});
              replayRerunMap();
            }}
            if (action === "replay-map") {{
              await routePost("/api/rerun/replay_map", {{}});
              replayRerunMap();
              setRouteStatus("Replaying Rerun map scan", "ok");
              return;
            }}
            if (action === "run") {{
              await routePost("/api/route/run", {{}});
              replayRerunMap();
            }}
            if (action === "add-waypoint") await routeTargetAction("waypoint", targetId);
            if (action === "add-poi") await routeTargetAction("poi", targetId);
            setRouteStatus("Route updated", "ok");
            window.setTimeout(() => window.location.reload(), 450);
          }} catch (error) {{
            setRouteStatus(`Route update failed: ${{error.message}}`, "error");
          }}
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


def status_pill(label: str, value: object) -> str:
    return (
        '<div class="status-pill">'
        f"<span>{escape(label)}</span>"
        f"<strong>{escape(str(value))}</strong>"
        "</div>"
    )


def humanize(value: object) -> str:
    return str(value).replace("_", " ").strip().title()


def format_reading_value(value: object, unit: object) -> str:
    text = str(value)
    display = humanize(text) if "_" in text else text
    unit_text = str(unit or "")
    return f"{display} {unit_text}".strip()


def attention_list(incidents: list[dict[str, Any]]) -> str:
    if not incidents:
        return '<p class="muted">No open safety or orderliness issues.</p>'
    rows = []
    for incident in incidents:
        state = str(incident.get("state", "open"))
        rows.append(
            f'<div class="attention-item {escape(state)}">'
            f"<strong>{escape(str(incident.get('title', 'Issue')))}</strong>"
            f"<span>{escape(str(incident.get('severity', '')))} / {escape(humanize(state))}</span>"
            f"<p class=\"muted\">{escape(str(incident.get('recommended_action', 'Review issue.')))}</p>"
            "</div>"
        )
    return '<div class="attention-list">' + "".join(rows) + "</div>"


def reading_cards(readings: list[dict[str, Any]]) -> str:
    if not readings:
        return '<p class="muted">No machine readings yet.</p>'
    cards = []
    for reading in readings:
        status = str(reading.get("status", "unknown"))
        is_alert = status.lower() not in {"normal", "ok", "clear", "pass"}
        value = format_reading_value(reading.get("value"), reading.get("unit"))
        cards.append(
            f'<div class="reading-card {"alert" if is_alert else ""}">'
            '<div class="reading-value">'
            f"<strong>{escape(humanize(reading.get('name', 'reading')))}</strong>"
            f"<span>{escape(value)}</span>"
            "</div>"
            f"<span>{escape(humanize(status))}</span>"
            f"<p class=\"muted\">{escape(str(reading.get('notes') or reading.get('source') or ''))}</p>"
            "</div>"
        )
    return '<div class="reading-cards">' + "".join(cards) + "</div>"


def change_list(changes: list[object]) -> str:
    if not changes:
        return '<p class="muted">No floor changes recorded yet.</p>'
    return (
        '<div class="change-list">'
        + "".join(f'<div class="change-item">{escape(str(change))}</div>' for change in changes)
        + "</div>"
    )


def route_stepper(route_plan: dict[str, Any]) -> str:
    waypoints = route_plan.get("waypoints") or []
    if not waypoints:
        return '<p class="muted">No route set.</p>'
    return (
        '<div class="route-stepper">'
        + "".join(
            '<div class="route-step">'
            f"<strong>{escape(str(waypoint.get('order')))}. "
            f"{escape(str(waypoint.get('target_id')))}</strong>"
            f"<span>{escape(humanize(waypoint.get('action', 'go')))} / "
            f"{escape(str(waypoint.get('display_name', '')))}</span>"
            "</div>"
            for waypoint in waypoints
        )
        + "</div>"
    )


def poi_stepper(route_plan: dict[str, Any]) -> str:
    pois = route_plan.get("points_of_interest") or []
    if not pois:
        return '<p class="muted">No photo or reading points set.</p>'
    return (
        '<div class="route-stepper">'
        + "".join(
            '<div class="route-step">'
            f"<strong>{escape(str(poi.get('id')))} / {escape(str(poi.get('target_id')))}</strong>"
            f"<span>{escape(', '.join(str(item) for item in poi.get('reading_keys') or []))}</span>"
            "</div>"
            for poi in pois
        )
        + "</div>"
    )


def map_viewer_panel(
    site_map: dict[str, Any],
    route_plan: dict[str, Any],
    target_options: list[dict[str, str]],
) -> str:
    urls = dimos_viewer_urls()
    rerun_source_url = escape(urls["rerun_source"], quote=True)
    web_viewer_module_url = escape(urls["web_viewer_module"], quote=True)
    web_viewer_asset_base_url = escape(urls["web_viewer_asset_base"], quote=True)
    command_center_url = escape(urls["command_center"], quote=True)
    return (
        "<div>"
        '<div class="map-viewer" data-map-viewer '
        f'data-rerun-source-url="{rerun_source_url}" '
        f'data-rerun-module-url="{web_viewer_module_url}" '
        f'data-rerun-asset-base-url="{web_viewer_asset_base_url}">'
        '<div class="map-toolbar">'
        '<div class="viewer-chip"><span>Rerun WebViewer</span></div>'
        '<div class="viewer-links">'
        f'<a href="{command_center_url}" target="_blank" rel="noreferrer">Open Command Center</a>'
        "</div>"
        "</div>"
        '<div class="map-route-overlay">'
        "<label>Route and inspection points</label>"
        '<div class="route-controls" data-route-controls>'
        f"<select data-route-target>{target_option_html(target_options)}</select>"
        '<button type="button" data-route-action="explore">Map Open Space</button>'
        '<button type="button" data-route-action="replay-map">Replay Map</button>'
        '<button type="button" data-route-action="run">Run Route</button>'
        '<button type="button" data-route-action="add-waypoint">Add Waypoint</button>'
        '<button type="button" data-route-action="add-poi">Add POI</button>'
        "</div>"
        '<div class="map-click-modes" aria-label="Map drawing mode">'
        '<button type="button" data-map-click-mode="waypoint" aria-pressed="false">Waypoint Mode</button>'
        '<button type="button" data-map-click-mode="poi" aria-pressed="false">POI Mode</button>'
        "</div>"
        '<div class="map-click-hint" data-map-click-status>Map authoring idle.</div>'
        '<div class="route-status" data-route-status>Route editor ready</div>'
        "</div>"
        '<div class="robot-dock" data-robot-controls>'
        '<div class="robot-dock-bar">'
        '<div><strong>Robot Control</strong><span class="robot-status" data-robot-status>Idle</span></div>'
        '<button type="button" class="hard-stop" data-command="hard_stop">HARD STOP</button>'
        "</div>"
        '<details>'
        "<summary>Manual motion</summary>"
        '<div class="posture-controls" data-posture-controls>'
        '<button type="button" data-posture="wake">Wake / Stand</button>'
        '<button type="button" data-posture="balance">Balance</button>'
        '<button type="button" data-posture="sleep">Sleep</button>'
        "</div>"
        '<div class="motion-controls" data-motion-controls>'
        '<button type="button" data-motion="nudge" aria-pressed="true">Nudge</button>'
        '<button type="button" data-motion="step" aria-pressed="false">Step</button>'
        '<button type="button" data-motion="walk" aria-pressed="false">Walk</button>'
        "</div>"
        '<div class="robot-controls">'
        "<span></span>"
        '<button type="button" data-command="forward">Forward</button>'
        "<span></span>"
        '<button type="button" data-command="left">Left</button>'
        "<span></span>"
        '<button type="button" data-command="right">Right</button>'
        '<button type="button" data-command="yaw_left">Yaw L</button>'
        '<button type="button" data-command="backward">Back</button>'
        '<button type="button" data-command="yaw_right">Yaw R</button>'
        "</div>"
        "</details>"
        "</div>"
        '<div class="rerun-canvas" data-rerun-canvas></div>'
        f'<div class="map-target-overlay" data-route-map>{map_target_overlay(site_map, route_plan)}</div>'
        '<div class="viewer-offline" data-viewer-offline hidden>'
        f'<div class="map-viz">{map_svg(site_map, route_plan)}</div>'
        "</div>"
        '<div class="viewer-hint">'
        "<span><strong>Rerun</strong> is mounted inside DogOps.</span>"
        "<span data-rerun-status>Connecting to Rerun...</span>"
        "</div>"
        "</div>"
        '<details class="offline-snapshot">'
        "<summary>Offline map artifact</summary>"
        f'<div class="map-viz">{map_svg(site_map, route_plan)}</div>'
        "</details>"
        "</div>"
    )


def map_target_overlay(site_map: dict[str, Any], route_plan: dict[str, Any]) -> str:
    features = site_map.get("features") or []
    if not features:
        return ""
    poi_targets = {poi.get("target_id") for poi in route_plan.get("points_of_interest") or []}
    route_targets = {waypoint.get("target_id") for waypoint in route_plan.get("waypoints") or []}
    rows = []
    for feature in features:
        pose = feature.get("pose") or {}
        if pose.get("x") is None or pose.get("y") is None:
            continue
        x, y = _map_pixel(site_map, float(pose["x"]), float(pose["y"]))
        left_pct = (x / 720) * 100
        top_pct = (y / 420) * 100
        target_id = str(feature.get("id") or "")
        if not target_id:
            continue
        display_name = str(feature.get("display_name") or target_id)
        classes = ["is-poi"] if target_id in poi_targets else []
        if target_id in route_targets:
            classes.append("is-route")
        class_attr = f' class="{" ".join(classes)}"' if classes else ""
        rows.append(
            f'<button type="button"{class_attr} '
            f'data-map-target-id="{escape(target_id, quote=True)}" '
            f'data-map-target-name="{escape(display_name, quote=True)}" '
            f'aria-label="Map target {escape(display_name, quote=True)}" '
            f'style="left:{left_pct:.2f}%;top:{top_pct:.2f}%;">'
            f"<span>{escape(target_id)}</span>"
            "</button>"
        )
    return "".join(rows)


def dimos_viewer_urls() -> dict[str, str]:
    return {
        "rerun_source": _trusted_rerun_source_url(
            os.environ.get("DOGOPS_RERUN_SOURCE_URL") or "rerun+http://127.0.0.1:9877/proxy",
        ),
        "web_viewer_module": _trusted_asset_url(
            os.environ.get("DOGOPS_RERUN_WEB_VIEWER_MODULE_URL") or "/assets/rerun-web-viewer.js",
            "/assets/rerun-web-viewer.js",
        ),
        "web_viewer_asset_base": _trusted_asset_url(
            os.environ.get("DOGOPS_RERUN_WEB_VIEWER_ASSET_BASE_URL")
            or "/assets/vendor/@rerun-io/web-viewer/",
            "/assets/vendor/@rerun-io/web-viewer/",
        ),
        "command_center": _trusted_local_viewer_url(
            os.environ.get("DOGOPS_COMMAND_CENTER_URL") or "http://127.0.0.1:7779/command-center",
            "http://127.0.0.1:7779/command-center",
        ),
    }


def _trusted_asset_url(raw_url: str, fallback: str) -> str:
    if raw_url.startswith("/"):
        return raw_url
    return _trusted_local_viewer_url(raw_url, fallback)


def _trusted_rerun_source_url(raw_url: str) -> str:
    fallback = "rerun+http://127.0.0.1:9877/proxy"
    if not raw_url.startswith("rerun+"):
        return fallback
    parsed = urlparse(raw_url.removeprefix("rerun+"))
    hostname = parsed.hostname or ""
    if parsed.scheme in {"http", "https"} and hostname in {"127.0.0.1", "localhost", "::1"}:
        return raw_url
    if os.environ.get("DOGOPS_ALLOW_REMOTE_VIEWER") == "1":
        return raw_url
    return fallback


def _trusted_local_viewer_url(raw_url: str, fallback: str) -> str:
    parsed = urlparse(raw_url)
    hostname = parsed.hostname or ""
    if parsed.scheme in {"http", "https"} and hostname in {"127.0.0.1", "localhost", "::1"}:
        return raw_url
    if os.environ.get("DOGOPS_ALLOW_REMOTE_VIEWER") == "1":
        return raw_url
    return fallback


def _map_pixel(site_map: dict[str, Any], x: float, y: float) -> tuple[float, float]:
    width = 720
    height = 420
    pad = 34
    map_width_m = float(site_map.get("width_m") or 4.5)
    map_height_m = float(site_map.get("height_m") or 3.0)
    origin = site_map.get("origin") or {}
    origin_x = float(origin.get("x") or 0.0)
    origin_y = float(origin.get("y") or 0.0)
    resolution = float(site_map.get("resolution_m") or 0.5)
    dimos_costmap = site_map.get("dimos_costmap") or {}
    dimos_grid_payload = dimos_costmap.get("grid") if isinstance(dimos_costmap, dict) else None
    grid_rows = (
        decode_dimos_costmap_full(dimos_grid_payload)
        if isinstance(dimos_grid_payload, dict)
        else []
    )
    if grid_rows and isinstance(dimos_costmap, dict):
        origin_vector = (dimos_costmap.get("origin") or {}).get("c") or []
        if len(origin_vector) >= 2:
            origin_x = float(origin_vector[0])
            origin_y = float(origin_vector[1])
        resolution = float(dimos_costmap.get("resolution") or resolution)
        map_width_m = max(resolution, len(grid_rows[0]) * resolution)
        map_height_m = max(resolution, len(grid_rows) * resolution)

    px = pad + ((x - origin_x) / map_width_m) * (width - 2 * pad)
    py = height - pad - ((y - origin_y) / map_height_m) * (height - 2 * pad)
    return px, py


def map_svg(site_map: dict[str, Any], route_plan: dict[str, Any]) -> str:
    width = 720
    height = 420
    pad = 34
    cells = site_map.get("cells") or []
    dimos_costmap = site_map.get("dimos_costmap") or {}
    dimos_grid_payload = dimos_costmap.get("grid") if isinstance(dimos_costmap, dict) else None
    grid_rows = (
        decode_dimos_costmap_full(dimos_grid_payload)
        if isinstance(dimos_grid_payload, dict)
        else []
    )
    map_width_m = float(site_map.get("width_m") or 4.5)
    map_height_m = float(site_map.get("height_m") or 3.0)
    origin = site_map.get("origin") or {}
    origin_x = float(origin.get("x") or 0.0)
    origin_y = float(origin.get("y") or 0.0)
    resolution = float(site_map.get("resolution_m") or 0.5)
    if grid_rows and isinstance(dimos_costmap, dict):
        origin_vector = (dimos_costmap.get("origin") or {}).get("c") or []
        if len(origin_vector) >= 2:
            origin_x = float(origin_vector[0])
            origin_y = float(origin_vector[1])
        resolution = float(dimos_costmap.get("resolution") or resolution)
        map_width_m = max(resolution, len(grid_rows[0]) * resolution)
        map_height_m = max(resolution, len(grid_rows) * resolution)
    features = site_map.get("features") or []
    path = site_map.get("explored_path") or []
    dimos_path = site_map.get("dimos_path") or {}
    dimos_path_points = dimos_path.get("points") if isinstance(dimos_path, dict) else None
    if isinstance(dimos_path_points, list):
        path = [
            {"x": point[0], "y": point[1]}
            for point in dimos_path_points
            if isinstance(point, (list, tuple)) and len(point) >= 2
        ]
    waypoints = route_plan.get("waypoints") or []
    pois = route_plan.get("points_of_interest") or []

    def sx(x: float) -> float:
        return pad + ((x - origin_x) / map_width_m) * (width - 2 * pad)

    def sy(y: float) -> float:
        return height - pad - ((y - origin_y) / map_height_m) * (height - 2 * pad)

    def cell_color(state: str) -> str:
        return {
            "free": "#dbeafe",
            "occupied": "#fecaca",
            "restricted": "#fde68a",
            "unknown": "#f1f5f9",
        }.get(state, "#f1f5f9")

    def cost_color(value: int) -> str:
        if value == -1:
            return "#f1f5f9"
        if value == 0:
            return "#dbeafe"
        return "#fecaca"

    if not cells and not grid_rows:
        return (
            f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="DogOps map">'
            '<rect width="720" height="420" fill="#f8fafc"/>'
            '<text x="48" y="72" fill="#17202a" font-family="Arial, sans-serif" '
            'font-size="24" font-weight="700">Map is empty</text>'
            '<text x="48" y="108" fill="#5b6776" font-family="Arial, sans-serif" '
            'font-size="16">Use Map Open Space to populate the simulated local map.</text>'
            "</svg>"
        )

    cell_w = max(2.0, (resolution / map_width_m) * (width - 2 * pad))
    cell_h = max(2.0, (resolution / map_height_m) * (height - 2 * pad))
    cell_rects = []
    if grid_rows:
        for y_index, row in enumerate(grid_rows):
            for x_index, value in enumerate(row):
                x = origin_x + (x_index * resolution)
                y = origin_y + (y_index * resolution)
                cell_rects.append(
                    f'<rect x="{sx(x):.1f}" y="{sy(y + resolution):.1f}" '
                    f'width="{cell_w + 0.8:.1f}" height="{cell_h + 0.8:.1f}" '
                    f'fill="{cost_color(value)}"/>'
                )
    else:
        for cell in cells:
            x = origin_x + (int(cell["x_index"]) * resolution)
            y = origin_y + (int(cell["y_index"]) * resolution)
            cell_rects.append(
                f'<rect x="{sx(x):.1f}" y="{sy(y + resolution):.1f}" '
                f'width="{cell_w + 0.8:.1f}" height="{cell_h + 0.8:.1f}" '
                f'fill="{cell_color(str(cell.get("state", "unknown")))}"/>'
            )

    path_points = " ".join(
        f"{sx(float(point.get('x') or 0.0)):.1f},{sy(float(point.get('y') or 0.0)):.1f}"
        for point in path
    )
    route_points = " ".join(
        f"{sx(float((waypoint.get('pose') or {}).get('x') or 0.0)):.1f},"
        f"{sy(float((waypoint.get('pose') or {}).get('y') or 0.0)):.1f}"
        for waypoint in waypoints
    )
    feature_marks = []
    poi_targets = {poi.get("target_id") for poi in pois}
    poi_order = {poi.get("target_id"): index + 1 for index, poi in enumerate(pois)}
    for feature in features:
        pose = feature.get("pose") or {}
        x = sx(float(pose.get("x") or 0.0))
        y = sy(float(pose.get("y") or 0.0))
        is_poi = feature.get("id") in poi_targets
        color = "#0f766e" if not is_poi else "#b45309"
        label = str(feature.get("id", ""))
        display_name = str(feature.get("display_name") or label)
        feature_marks.append(
            f'<g data-map-target-id="{escape(label, quote=True)}" '
            f'data-map-target-name="{escape(display_name, quote=True)}">'
            f"<title>{escape(display_name)}</title>"
        )
        feature_marks.append(
            f'<circle class="map-target-hit" cx="{x:.1f}" cy="{y:.1f}" r="18" '
            'fill="#ffffff" opacity="0.01"/>'
        )
        feature_marks.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{7 if is_poi else 5}" fill="{color}"/>'
        )
        if is_poi:
            feature_marks.append(
                f'<text x="{x:.1f}" y="{y + 4:.1f}" fill="#ffffff" '
                'font-family="Arial, sans-serif" font-size="10" font-weight="700" '
                f'text-anchor="middle">{escape(str(poi_order.get(feature.get("id"), "")))}</text>'
            )
        elif feature.get("kind") == "zone" and label != "RACK_ROW_A":
            feature_marks.append(
                f'<text x="{x:.1f}" y="{y - 11:.1f}" fill="#17202a" '
                'font-family="Arial, sans-serif" font-size="12" text-anchor="middle">'
                f"{escape(label)}</text>"
            )
        feature_marks.append("</g>")

    robot_pose = site_map.get("robot_pose") or {}
    robot_mark = ""
    if isinstance(robot_pose, dict) and robot_pose.get("x") is not None and robot_pose.get("y") is not None:
        robot_x = sx(float(robot_pose.get("x") or 0.0))
        robot_y = sy(float(robot_pose.get("y") or 0.0))
        theta = float(robot_pose.get("theta_deg") or 0.0)
        heading_x = robot_x + (16 * math.cos(math.radians(theta)))
        heading_y = robot_y - (16 * math.sin(math.radians(theta)))
        robot_mark = (
            f'<circle cx="{robot_x:.1f}" cy="{robot_y:.1f}" r="10" fill="#111827" '
            'stroke="#ffffff" stroke-width="3"/>'
            f'<line x1="{robot_x:.1f}" y1="{robot_y:.1f}" x2="{heading_x:.1f}" '
            f'y2="{heading_y:.1f}" stroke="#111827" stroke-width="4" stroke-linecap="round"/>'
            f'<text x="{robot_x + 13:.1f}" y="{robot_y - 13:.1f}" fill="#111827" '
            'font-family="Arial, sans-serif" font-size="12" font-weight="700">dog</text>'
        )

    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="DogOps map">'
        '<rect width="720" height="420" fill="#f8fafc"/>'
        + "".join(cell_rects)
        + (
            f'<polyline points="{path_points}" fill="none" stroke="#2563eb" '
            'stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="0.55"/>'
            if path_points
            else ""
        )
        + (
            f'<polyline points="{route_points}" fill="none" stroke="#0f766e" '
            'stroke-width="3" stroke-dasharray="8 7" stroke-linecap="round"/>'
            if route_points
            else ""
        )
        + "".join(feature_marks)
        + robot_mark
        + '<rect x="18" y="18" width="190" height="34" rx="6" fill="#ffffff" stroke="#d7dce3"/>'
        + '<text x="32" y="41" fill="#17202a" font-family="Arial, sans-serif" font-size="14">'
        + f'{escape(str(site_map.get("status", "empty")))} / '
        + f'{float(site_map.get("coverage_ratio", 0.0)) * 100:.0f}% coverage</text>'
        + '<text x="32" y="396" fill="#5b6776" font-family="Arial, sans-serif" font-size="12">'
        + f'{escape(str(site_map.get("dimos_schema", "dimos.web.websocket_vis.v1")))}</text>'
        + "</svg>"
    )


def target_option_html(options: list[dict[str, str]]) -> str:
    return "".join(
        f'<option value="{escape(option["id"])}">{escape(option["label"])}</option>'
        for option in options
    )


def route_table(route_plan: dict[str, Any]) -> str:
    waypoints = route_plan.get("waypoints") or []
    if not waypoints:
        return '<p class="muted">No waypoints set.</p>'
    rows = []
    for waypoint in waypoints:
        rows.append(
            "<tr>"
            f"<td>{escape(str(waypoint.get('order')))}</td>"
            f"<td>{escape(str(waypoint.get('target_id')))}</td>"
            f"<td>{escape(str(waypoint.get('action')))}</td>"
            f"<td>{escape(str(waypoint.get('display_name')))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>#</th><th>Target</th><th>Action</th><th>Name</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def poi_table(route_plan: dict[str, Any]) -> str:
    pois = route_plan.get("points_of_interest") or []
    if not pois:
        return '<p class="muted">No photo points set.</p>'
    rows = []
    for poi in pois:
        rows.append(
            "<tr>"
            f"<td>{escape(str(poi.get('id')))}</td>"
            f"<td>{escape(str(poi.get('target_id')))}</td>"
            f"<td>{escape(', '.join(str(item) for item in poi.get('reading_keys') or []))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>POI</th><th>Target</th><th>Readings</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def capture_grid(captures: list[dict[str, Any]]) -> str:
    if not captures:
        return '<p class="muted">No point-of-interest photos captured yet.</p>'
    items = []
    for capture in captures:
        image_path = Path(str(capture.get("image_path") or ""))
        src = f"/evidence/{escape(image_path.name)}" if image_path.name else ""
        image = f'<img src="{src}" alt="{escape(str(capture.get("poi_id")))} evidence">' if src else ""
        items.append(
            '<div class="evidence-item">'
            f"{image}"
            f"<h3>{escape(str(capture.get('poi_id')))}</h3>"
            f"<p>{escape(str(capture.get('analysis')))}</p>"
            f"<p class=\"muted\">{escape(str(capture.get('vlm_provider')))} analysis</p>"
            "</div>"
        )
    return '<div class="evidence-grid">' + "".join(items) + "</div>"


def reading_table(readings: list[dict[str, Any]]) -> str:
    if not readings:
        return '<p class="muted">No readings analyzed yet.</p>'
    rows = []
    for reading in readings:
        value = format_reading_value(reading.get("value"), reading.get("unit"))
        rows.append(
            "<tr>"
            f"<td>{escape(str(reading.get('poi_id')))}</td>"
            f"<td>{escape(str(reading.get('name')))}</td>"
            f"<td>{escape(value)}</td>"
            f"<td>{escape(str(reading.get('status')))}</td>"
            f"<td>{escape(str(reading.get('source')))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>POI</th><th>Reading</th><th>Value</th>"
        "<th>Status</th><th>Source</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
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


def _target_options(state: dict[str, Any]) -> list[dict[str, str]]:
    site = state.get("site") or {}
    options: list[dict[str, str]] = []
    for collection in ("zones", "assets", "packages"):
        for entity in site.get(collection) or []:
            entity_id = str(entity.get("id"))
            label = f"{entity_id} - {entity.get('display_name', entity_id)}"
            options.append({"id": entity_id, "label": label})
    for entity in (site.get("special_entities") or {}).values():
        entity_id = str(entity.get("id"))
        label = f"{entity_id} - {entity.get('display_name', entity_id)}"
        options.append({"id": entity_id, "label": label})
    return options
