# DogOps - DimOS SiteOps Agent

DogOps turns a Unitree Go2 running on DimOS into a physical SiteOps agent for spaces where
software alerts cannot see the real world: warehouses, lab rooms, data-center rows, maker
spaces, construction offices, and industrial floors.

The robot receives a site policy and receiving manifest, maps the demo facility, follows an
inspection route, scans AprilTag-labeled packages and assets, reconciles physical state against
expected state, opens spatial work orders for exceptions, revisits after human remediation, and
produces a dashboard report with package status, incident history, evidence, and navigation
metrics.

DogOps is designed to run without cloud API keys or an LLM. The core workflow is deterministic
and MCP-callable; Gemini/OpenAI/VLM analysis is optional, server-side, and limited to narration
or extra image analysis around the same base product loop.

## Demo Loop

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

In the default demo, `PKG-104` is placed in the wrong zone and blocks `COOLING_1`. DogOps
detects both the logistics exception and the facility hazard, opens `INC-001` / `WO-001`, waits
for the package to move to `QA_HOLD`, revisits `COOLING_1`, verifies the fix, and leaves
`PKG-103` as the intentional missing-package exception.

## Product Capabilities

- Site and manifest modeling for zones, packages, assets, policies, incidents, work orders, and
  navigation events.
- DimOS-backed mapping and route overlays using `global_costmap`, planner `path`, and `odom`
  streams.
- Operator route planning with waypoints and points of interest for photos or readings.
- AprilTag 36h11 package, zone, and asset identity.
- Deterministic mission engine for receiving, inspection, remediation, verification, and final
  reporting.
- Dashboard views for map, route, packages, incidents, work orders, POI evidence, readings, and
  navigation metrics.
- MCP skills for running missions, scanning zones, verifying work orders, mapping open space,
  executing route plans, and reporting navigation/POI results.
- Real-Go2 path with conservative motion, explicit stop commands, and honest recording of
  retries, guided interventions, and safety stops.

DogOps does not implement its own SLAM stack. It uses the existing DimOS Go2 map/navigation
pipeline and adds the SiteOps product layer on top: semantic zones, policy state, package
placement, incident evidence, route progress, and run reports. Rerun remains useful for raw robot
telemetry; the DogOps dashboard is the operator-facing workflow.

## Repository Layout

- [dimos/experimental/dogops](dimos/experimental/dogops) - DogOps models, mission engine,
  mapping bridge, dashboard, CLI, reports, and MCP skills.
- [dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py](dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py)
  - Go2 blueprint hook for DimOS registry/runtime integration.
- [config](config) - demo site, manifest, mission, and policy YAML.
- [docs/dogops/DEMO.md](docs/dogops/DEMO.md) - demo script and local run flow.
- [docs/RUNBOOK_MAC_GO2.md](docs/RUNBOOK_MAC_GO2.md) - real-Go2 runbook.
- [docs/dogops/HARDWARE_HANDOFF.md](docs/dogops/HARDWARE_HANDOFF.md) - arena, tags,
  evidence, and video checklist.
- [SPEC.md](SPEC.md) - canonical product behavior and acceptance criteria.
- [STATUS.md](STATUS.md) - project status and validation notes.

## Quick Start

Requirements:

- Python 3.12
- `uv`
- A DimOS checkout with this package available

Install dependencies and run the local checks:

```bash
uv sync --group dev
uv run pytest -q dimos/experimental/dogops
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run ruff check dimos/experimental/dogops dimos/robot
uv run dimos list | rg dogops
uv run dimos mcp list-tools | rg 'run_mission|scan_zone|read_gauge|check_clearance|detect_blocked_aisle|scan_receiving_manifest|verify_work_order|nav_eval_report'
```

Validate the demo configuration:

```bash
uv run python -m dimos.experimental.dogops.cli validate
```

Run the deterministic demo mission:

```bash
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
```

Generate the local facility map, add a waypoint and POI, then execute the route plan:

```bash
uv run python -m dimos.experimental.dogops.cli map --run .dogops/runs/latest
uv run python -m dimos.experimental.dogops.cli plan \
  --run .dogops/runs/latest \
  --add-waypoint TEMP_1 \
  --add-poi TEMP_1
uv run python -m dimos.experimental.dogops.cli run-plan --run .dogops/runs/latest
```

The run directory contains the full audit trail:

```text
.dogops/runs/latest/
  state.json
  report.md
  report.json
  map.json
  route_plan.json
  poi_captures.jsonl
  sensor_readings.jsonl
  evidence/
```

## Dashboard

Serve the latest run:

```bash
uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765
```

Open <http://127.0.0.1:8765/>.

The dashboard shows the mapped site, route plan, robot/route progress, package state, incident
timeline, work-order state, POI captures, readings, navigation summary, and final run report.

Useful JSON endpoints:

```bash
curl -fsS http://127.0.0.1:8765/api/state
curl -fsS http://127.0.0.1:8765/api/report
curl -fsS http://127.0.0.1:8765/api/nav
curl -fsS http://127.0.0.1:8765/api/map
curl -fsS http://127.0.0.1:8765/api/route
curl -fsS http://127.0.0.1:8765/api/poi
```

## DimOS And Go2

Verify that DogOps is registered in DimOS and exposes its MCP tools:

```bash
uv run dimos list | rg dogops
uv run dimos mcp list-tools | rg 'run_mission|map_open_space|run_route_plan|poi_report|nav_eval_report'
```

Smoke-test the base Go2 path before a DogOps run:

```bash
uv run dimos stop --force
uv run dimos --viewer none run unitree-go2 -o go2connection.ip=<GO2_IP> --daemon
uv run dimos status
uv run dimos stop --force
```

Run DogOps through the `unitree-go2-dogops` blueprint once the base robot path is healthy. Keep
routes conservative indoors, verify `unitree-go2` before `unitree-go2-dogops`, and keep
`uv run dimos stop --force` ready.

## AprilTag Vision

The deterministic demo accepts simulated observations, and hardware runs use AprilTag 36h11
detections for packages, zones, and assets. To check the optional OpenCV detector path:

```bash
uv run --extra vision python -c "import cv2; print(cv2.__version__); print(hasattr(cv2, 'aruco'))"
uv run pytest -q dimos/experimental/dogops/test_detector.py
```

Tag IDs and physical setup guidance are in [docs/dogops/TAGS.md](docs/dogops/TAGS.md) and
[docs/dogops/HARDWARE_HANDOFF.md](docs/dogops/HARDWARE_HANDOFF.md).

## Safety

DogOps is a robot workflow, so every hardware run should start from a known safe state:

```bash
uv run dimos stop --force
```

Use conservative indoor routes, keep people clear of the robot path, record guided movement
honestly in navigation metrics, and follow [docs/SAFETY.md](docs/SAFETY.md).
