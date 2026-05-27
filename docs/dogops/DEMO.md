# DogOps Demo

## Real Go2 Air Target

The real Unitree Go2 Air is available. Use the offline demo as a safety net, but final evidence should include L0 or L1 hardware whenever possible:

```text
L0: full autonomous Go2 Air + dashboard + MCP
L1: Go2 Air scans tags + guided navigation + dashboard
L2: Go2 Air movement/tag video + offline dashboard/report
L3: offline product demo + recorded Go2 Air clip only
```

Run the hardware sequence from [HARDWARE_HANDOFF.md](HARDWARE_HANDOFF.md) after registry/MCP validation passes.

## Part A Offline Demo

Run the deterministic offline mission:

```bash
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
cat .dogops/runs/latest/report.md
```

The offline run demonstrates the core closed loop without robot hardware, cloud APIs, or an LLM:

1. Load the demo site, manifest, policy, and mission.
2. Build a local open-space map from the route and site landmarks using the DimOS-compatible costmap/path contract.
3. Create an operator route plan with waypoints and photo/readings POIs.
4. Scan `INBOUND_DOCK` and find `PKG-101` and `PKG-102`.
5. Inspect `COOLING_1` and find `PKG-104` in the wrong zone blocking cooling.
6. Open `INC-001` / `WO-001`.
7. Simulate human remediation by moving `PKG-104` to `QA_HOLD`.
8. Verify `COOLING_1` clear and close `INC-001`.
9. Capture simulated POI evidence at `COOLING_1`, `TEMP_1`, and `QA_HOLD`.
10. Leave `PKG-103` as the open missing-package issue.
11. Write the run report, map, route plan, POI analysis, readings, and navigation metrics.

Map/route commands:

```bash
uv run python -m dimos.experimental.dogops.cli map --run .dogops/runs/latest
uv run python -m dimos.experimental.dogops.cli plan \
  --run .dogops/runs/latest \
  --add-waypoint TEMP_1 \
  --add-poi TEMP_1
uv run python -m dimos.experimental.dogops.cli run-plan --run .dogops/runs/latest
```

Generated POI analysis is deterministic and local. Gemini/OpenAI image recognition is not required for the base demo; if a future VLM path is added, keep the API key in `.env` and call it only from server-side code.

The dashboard standard map panel embeds the real Rerun WebViewer from local npm assets and connects to the local DimOS Rerun bridge by default:

- Rerun WebViewer: primary map viewport for camera, point cloud/global map, TF/base link, nav costmap, planned path, odom, and debug evidence.
- DimOS Command Center: adjacent link for live nav/costmap controls when the DimOS web visualization module is running.
- DogOps dashboard: product workflow around the live viewer, including package/asset labels, semantic zones, incidents, operator route, waypoints, POIs, readings, and run report.
- Bridge: `DogOpsLiveMapModule` consumes shared DimOS streams `global_costmap`, planner `path`, and `odom`, then writes `dimos_costmap`, `dimos_path`, robot pose, and coverage stats for the dashboard.
- Offline artifact: `map.json` remains available as a fallback snapshot for reports/tests, but it is not the standard operator map view.
- Simulator bridge: when the real Go2 Air is unavailable, `dogops rerun-sim` publishes incremental 2D lidar-style mapping, odom/path, route/POI overlays, demo cones/boxes, and simulated POI camera frames into the same local Rerun source URL.
- Native 3D simulation: for real DimOS/MuJoCo-style 3D mapping visuals, run the existing DimOS Go2 Air simulator path, for example `uv run dimos --simulation --viewer rerun --rerun-open none --rerun-web run unitree-go2`, and bridge DogOps overlays with `dogops rerun-sim --view-mode native-3d`. Native 3D mode now requires that DimOS Rerun stream to already exist; the lightweight `dogops rerun-sim` fallback is not a replacement for the native 3D simulator.

Live Go2 Air mapping should swap in real `global_costmap`/`Path`/`PoseStamped` source messages without changing the dashboard workflow contract. Route execution should send DogOps waypoints as planner goals through DimOS, wait for `goal_reached`, record `NavEvent`, then run scan/inspect/photo actions.

Future alternative: make the DimOS/Rerun page the parent shell and embed DogOps as a side panel.

## Part B Dashboard Demo

Serve the latest run. Keep `rerun-sim` running in one terminal, then start the dashboard in another:

```bash
npm install
# Terminal A
uv run python -m dimos.experimental.dogops.cli rerun-sim --run .dogops/runs/latest
# Terminal B
uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765
```

Open <http://127.0.0.1:8765/> to view the dashboard.

`rerun-sim` needs `rerun-sdk`; use the full DimOS environment or install the optional DogOps `rerun` extra.

For the native 3D mapping view, start `uv run dimos --simulation --viewer rerun --rerun-open none --rerun-web run unitree-go2` first and run Terminal A with `--view-mode native-3d` so DogOps attaches overlays to the DimOS 3D Rerun stream instead of replacing the native simulator view. When DimOS serves its own Rerun web viewer, start the dashboard with `DOGOPS_RERUN_EMBED_URL=http://127.0.0.1:9878` to embed that native viewer page directly while keeping DogOps route/POI controls over it.

API checks:

```bash
curl -fsS http://127.0.0.1:8765/api/state
curl -fsS http://127.0.0.1:8765/api/report
curl -fsS http://127.0.0.1:8765/api/nav
curl -fsS http://127.0.0.1:8765/api/map
curl -fsS http://127.0.0.1:8765/api/route
curl -fsS http://127.0.0.1:8765/api/poi
```

## Part D Tag Detector Demo

Base simulated detector path:

```bash
uv run pytest -q dimos/experimental/dogops/test_detector.py
```

Optional OpenCV path:

```bash
uv run --extra vision python -c "import cv2; print(cv2.__version__); print(hasattr(cv2, 'aruco'))"
```

The detector uses AprilTag 36h11 IDs from `examples/dogops/site_demo.yaml`.

## Local Dry Run

```bash
PORT=8765 ./scripts/dogops_demo_dry_run.sh
```

Use `PORT=18765` or another port if `8765` is already in use.
