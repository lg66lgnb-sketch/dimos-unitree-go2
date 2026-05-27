# DogOps SiteOps Agent

DogOps turns a Unitree Go2 running on DimOS into a physical SiteOps agent for spaces where software alerts cannot see the real world: warehouses, lab rooms, data-center rows, maker spaces, construction offices, and industrial floors.

The current dashboard combines the DogOps semantic facility view with live DimOS navigation data from the dog: costmap heatmap, odom robot pose, planned path, and target overlays on the same map.

The dashboard does not require Rerun to render these top-map layers. Rerun remains optional as a separate DimOS viewer, while the DogOps map consumes the underlying DimOS messages directly.

## Product Direction

The full DogOps loop is a physical SiteOps workflow: the robot receives a site policy and receiving manifest, maps the demo facility, follows an inspection route, scans AprilTag-labeled packages and assets, reconciles physical state against expected state, opens spatial work orders for exceptions, revisits after human remediation, and produces a dashboard report with package status, incident history, evidence, and navigation metrics.

DogOps is designed to run without cloud API keys or an LLM. The core workflow is deterministic and MCP-callable; Gemini/OpenAI/VLM analysis is optional, server-side, and limited to narration or extra image analysis around the same base product loop.

## Demo Loop

This is the target loop for the product demo and the direction for future hardening:

```text
site policy + receiving manifest
-> autonomous route through a staged facility
-> DimOS-backed map with DogOps semantic overlays
-> AprilTag package/asset inspection
-> manifest reconciliation
-> physical hazard and work-order creation
-> human remediation request
-> robot revisits the same location
-> closure verification
-> dashboard + report + navigation metrics
```

In the default demo scenario, `PKG-104` is placed in the wrong zone and blocks `COOLING_1`. DogOps detects both the logistics exception and the facility hazard, opens `INC-001` / `WO-001`, waits for the package to move to `QA_HOLD`, revisits `COOLING_1`, verifies the fix, and leaves `PKG-103` as the intentional missing-package exception.

## Architecture

Live data flow:

1. `unitree-go2-dogops` runs inside the full DimOS checkout.
2. DimOS Go2 modules publish robot data:
   - `GO2Connection` publishes `/odom` and `/lidar`.
   - `VoxelGridMapper` accumulates lidar into `/global_map`.
   - `CostMapper` converts the global point cloud into `/global_costmap`.
   - `ReplanningAStarPlanner` can publish `/path`, `/target`, and `/navigation_costmap`.
   - DogOps `go_to` publishes `/clicked_point` targets.
3. `DogOpsLiveMapAdapter` subscribes to those DimOS LCM topics directly.
4. `/api/map` merges the semantic facility map with the live DimOS overlay payload.
5. `dashboard_static.py` renders heatmap, robot pose, path, and target as SVG layers on the same DogOps map.

The top map keeps semantic/click projection separate from live overlay projection, so live costmap extents do not break map-click `go_to` coordinates. Live topic snapshots also expire stale data, so disconnected streams do not stay displayed as current.

## Features

Current live map and dashboard capabilities:

- Same-map heatmap layer from DimOS `OccupancyGrid` costmap data.
- Robot pose layer from live Go2 odom.
- Path, route, clicked-point, and planner target overlays from DimOS navigation topics.
- Layer buttons for showing and hiding `Semantic`, `Heatmap`, `Path`, and `Robot`.
- Demo/offline mode for dashboard smoke tests without hardware.
- Live Go2 mode for real odom and costmap data from the dog.
- Optional Rerun Web panel for DimOS visualization without making Rerun the DogOps map renderer.
- Robot Control panel with conservative posture and motion commands.
- Dashboard shutdown closes DogOps-owned Go2 WebRTC sessions so direct Robot Control does not keep stealing the mapping stream.
- DogOps worker modules tolerate full DimOS runtime injection and expose docstrings for MCP skill discovery.

Broader SiteOps capabilities already present or being built toward:

- Site and manifest modeling for zones, packages, assets, policies, incidents, work orders, and navigation events.
- DimOS-backed mapping and route overlays using `global_costmap`, planner `path`, and `odom` streams.
- Operator route planning with waypoints and points of interest for photos or readings.
- AprilTag 36h11 package, zone, and asset identity.
- Deterministic mission engine for receiving, inspection, remediation, verification, and final reporting.
- Dashboard views for map, route, packages, incidents, work orders, POI evidence, readings, and navigation metrics.
- MCP skills for running missions, scanning zones, verifying work orders, mapping open space, executing route plans, and reporting navigation/POI results.
- Real-Go2 path with conservative motion, explicit stop commands, and honest recording of retries, guided interventions, and safety stops.

DogOps does not implement its own SLAM stack. It uses the existing DimOS Go2 map/navigation pipeline and adds the SiteOps product layer on top: semantic zones, policy state, package placement, incident evidence, route progress, and run reports. Rerun remains useful for raw robot telemetry; the DogOps dashboard is the operator-facing workflow.

## Repository Layout

- `dimos/experimental/dogops/` - DogOps models, mission engine, live map adapter, dashboard, CLI, reports, and skills.
- `dimos/experimental/dogops/live_map.py` - DimOS LCM topic adapter for `/api/map`.
- `dimos/experimental/dogops/dashboard.py` - dashboard server, JSON endpoints, and Go2 control endpoints.
- `dimos/experimental/dogops/dashboard_static.py` - static dashboard HTML, SVG map, layer rendering, and client polling.
- `dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py` - Go2 DogOps blueprint.
- `docs/RUNBOOK_MAC_GO2.md` - Mac/Go2 runbook.
- `docs/dogops/HARDWARE_HANDOFF.md` - arena, tags, evidence, and hardware checklist.
- `SPEC.md` - canonical product behavior.
- `STATUS.md` - current implementation and validation ledger.

## Demo / Offline Mode

Demo mode runs without the dog. It creates a deterministic DogOps run and serves the dashboard with the semantic map and simulated mission data.

```bash
cd $DOGOPS_REPO
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --host 127.0.0.1 --port 18769
```

Open:

```text
http://127.0.0.1:18769/
```

## Live Go2 Mode

Live Go2 map mode must run from the full local DimOS checkout/environment, not only an isolated DogOps checkout, because the Unitree WebRTC, LCM, mapping, and navigation stack live in DimOS.

```bash
cd $DIMOS_ROOT

# If macOS multicast routing is pointed at the dog Wi-Fi, route DimOS/LCM multicast locally.
sudo route delete -net 224.0.0.0/4 2>/dev/null || true
sudo route add -net 224.0.0.0/4 -interface lo0
route -n get 224.0.0.1
```

The final command should show `interface: lo0`.

Start the dashboard from a simulated run directory:

```bash
# Prepare a run directory for the dashboard.
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest

# Start the DogOps dashboard.
DOGOPS_ROBOT_IP=192.168.12.1 \
  uv run --no-sync python -m dimos.experimental.dogops.cli serve \
  --run .dogops/runs/latest \
  --host 127.0.0.1 \
  --port 18769
```

In another terminal, start the live DogOps runtime against the dog. For MCP route testing on macOS, prefer foreground mode; in local testing `--daemon` registered in `dimos status` but left the MCP HTTP server unreachable on `127.0.0.1:9990`.

```bash
GO2_IP=192.168.12.1 \
DOGOPS_ROBOT_IP=192.168.12.1 \
DOGOPS_SKIP_GO2_STARTUP_POSTURE=1 \
NO_PROXY=127.0.0.1,localhost \
no_proxy=127.0.0.1,localhost \
  uv run --no-sync dimos \
  --viewer none \
  --rerun-open none \
  --no-rerun-web \
  run unitree-go2-dogops \
  -o "go2connection.ip=192.168.12.1"
```

Open:

```text
http://127.0.0.1:18769/
```

Useful verification:

```bash
uv run --no-sync dimos status

NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  uv run --no-sync dimos mcp list-tools | rg 'go_to|follow_route|stop_route|route_status'

NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  uv run --no-sync dimos mcp call route_status

curl -s http://127.0.0.1:18769/api/map
```

Expected live indicators:

- `live.status` is `receiving`
- `live.topics.odom.received` is `true`
- `live.topics.global_costmap.received` is `true`
- `live.robot_pose` is not `null`
- `layers.heatmap` is `true`
- `layers.robot` is `true`

Before live route movement, author/select a tiny route in clear line of sight and run a dry-run first:

```bash
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  uv run --no-sync dimos mcp call follow_route \
  --json-args '{"route_id":"TEST_STATIONARY","dry_run":true}'
```

Stop command:

```bash
uv run --no-sync dimos stop --force
```

## Hardware Note

Robot Control opens its own direct Go2 WebRTC session. For heatmap validation, avoid clicking Robot Control while DimOS is running, or restart the dashboard server to close that direct session. Otherwise DimOS can be starved of odom/lidar and `/api/map` may remain `waiting_for_topics`.

## Validation

Run the focused DogOps checks:

```bash
uv run ruff check dimos/experimental/dogops
uv run pytest -q dimos/experimental/dogops
```

Useful full-check commands:

```bash
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run dimos list | rg dogops
uv run dimos mcp list-tools | rg 'run_mission|go_to|follow_route|stop_route|route_status|scan_zone|read_gauge|check_clearance|detect_blocked_aisle|scan_receiving_manifest|verify_work_order|nav_eval_report'
```

Local hardware smoke during development confirmed:

- DimOS `unitree-go2-dogops` started from a full DimOS checkout.
- `/api/map` reported `status=receiving`.
- `/api/map` received `odom=True` and `global_costmap=True`.
- Live costmap payload reported `48 x 32` with `1536` cells.
- Top-map layers reported `heatmap=True` and `robot=True`.
