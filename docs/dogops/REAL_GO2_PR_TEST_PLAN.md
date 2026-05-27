# DogOps Real-Go2 PR Test Plan

This is the PR handoff for the workflow that was validated offline and through the OrbStack web simulation path. It is written for the final real Unitree Go2 test from a full DimOS checkout.

## What This PR Proves

DogOps adds a deterministic SiteOps workflow on top of the existing DimOS Go2 stack:

```text
site policy + receiving manifest
-> generate run data
-> map and route plan
-> inspect AprilTag-labeled packages/assets
-> detect PKG-104 blocking COOLING_1
-> open INC-001 / WO-001
-> human moves PKG-104 to QA_HOLD
-> revisit/verify closure
-> dashboard + report + navigation/POI evidence
```

The workflow does not require cloud API keys. Rerun is used for robot telemetry. The DogOps dashboard is the operator-facing evidence and report surface.

## Already Validated Before Real-Go2 Test

Run these from the full DimOS checkout:

```bash
uv run --no-sync python --version
uv run --no-sync dimos list | rg 'unitree-go2-dogops'
uv run --no-sync pytest -q -o addopts='' dimos/experimental/dogops
uv run --no-sync python -m dimos.experimental.dogops.cli validate
uv run --no-sync python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run --no-sync python -m dimos.experimental.dogops.cli report --run .dogops/runs/latest
uv run --no-sync python -m dimos.experimental.dogops.cli map --run .dogops/runs/latest
uv run --no-sync python -m dimos.experimental.dogops.cli plan --run .dogops/runs/latest --add-waypoint TEMP_1 --add-poi TEMP_1
uv run --no-sync python -m dimos.experimental.dogops.cli run-plan --run .dogops/runs/latest
```

Expected run artifacts:

```text
.dogops/runs/latest/state.json
.dogops/runs/latest/report.md
.dogops/runs/latest/report.json
.dogops/runs/latest/map.json
.dogops/runs/latest/route_plan.json
.dogops/runs/latest/poi_captures.jsonl
.dogops/runs/latest/sensor_readings.jsonl
```

Dashboard API smoke:

```bash
uv run --no-sync python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --host 0.0.0.0 --port 8765
curl -fsS http://127.0.0.1:8765/api/state | python -m json.tool
curl -fsS http://127.0.0.1:8765/api/report | python -m json.tool
curl -fsS http://127.0.0.1:8765/api/nav | python -m json.tool
curl -fsS http://127.0.0.1:8765/api/map | python -m json.tool
curl -fsS http://127.0.0.1:8765/api/route | python -m json.tool
curl -fsS http://127.0.0.1:8765/api/poi | python -m json.tool
```

## OrbStack Web Simulation Recheck

Use this only to reproduce the web workflow without touching the real dog:

```bash
bash scripts/run_dogops_orbstack_web.sh
```

The script prints the Ubuntu `eth0` URLs. Open only these pages from the Mac browser:

```text
Rerun Web Viewer:
http://<UBUNTU_IP>:9878/?url=rerun%2Bhttp%3A%2F%2F<UBUNTU_IP>%3A9877%2Fproxy

DimOS WebSocket UI:
http://<UBUNTU_IP>:7779

DogOps Dashboard:
http://<UBUNTU_IP>:8765
```

Do not open port `3030` directly; it is the Rerun viewer websocket endpoint, not a webpage.

Pass criteria:

- `9877`, `9878`, `7779`, `3030`, and `8765` are listening.
- Rerun opens through the encoded `rerun+http://<UBUNTU_IP>:9877/proxy` source URL and shows at least one local entity.
- DogOps Dashboard shows the latest run state, report, map, route, POI, and navigation data.

## Real-Go2 Test Sequence

Start with the base robot path. Do not run DogOps hardware until base `unitree-go2` is healthy.

```bash
cd $DIMOS_ROOT
export GO2_IP=<GO2_IP>
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
ping -c 3 "$GO2_IP"
uv run --no-sync dimos stop --force || true
uv run --no-sync dimos run unitree-go2 --robot-ip "$GO2_IP" --viewer none --daemon
uv run --no-sync dimos status
uv run --no-sync dimos log -n 100
uv run --no-sync dimos stop --force
```

Then run the DogOps blueprint:

```bash
uv run --no-sync dimos stop --force || true
uv run --no-sync dimos run unitree-go2-dogops --robot-ip "$GO2_IP" --viewer none --daemon
uv run --no-sync dimos status
uv run --no-sync dimos mcp list-tools | rg 'run_mission|scan_zone|verify_work_order|nav_eval_report|map_open_space|run_route_plan|poi_report'
uv run --no-sync dimos mcp call run_mission --json-args '{"mission_id":"receiving_sre_demo"}'
uv run --no-sync dimos mcp call scan_zone --json-args '{"zone_id":"INBOUND_DOCK"}'
uv run --no-sync dimos mcp call nav_eval_report
uv run --no-sync dimos log -n 200
uv run --no-sync dimos stop --force
```

Keep the route short and slow:

```text
HOME -> INBOUND_DOCK -> RACK_ROW_A / COOLING_1 -> QA_HOLD -> HOME
```

The human moves `PKG-104`; the robot verifies the result. Record guided movement honestly if used.

## Fallbacks That Still Make A Valid Demo

- L0: autonomous Go2 + DogOps dashboard + MCP.
- L1: real Go2 scan/motion with guided navigation, dashboard and MCP live.
- L2: real Go2 movement or tag evidence plus deterministic dashboard/report fallback.
- L3: offline product demo plus recorded Go2 clip when robot/network is unavailable.

If base `unitree-go2` fails, stop and record the exact robot network/WebRTC/log blocker. Do not claim DogOps hardware validation.

## PR Evidence To Attach

- Command output from the local validation block.
- Dashboard screenshot or recording.
- `.dogops/runs/latest/report.md` and `report.json`.
- Port/status output from OrbStack simulation if used.
- Short arena video showing tags, `PKG-104` at `COOLING_1`, human move to `QA_HOLD`, and final report.
- Fallback level used, with reason.

## Suggested PR Description

Summary:

- Adds the DogOps SiteOps workflow for Unitree Go2 in DimOS.
- Adds CLI commands for validate, simulate, report, map, plan, run-plan, and dashboard serve.
- Adds dashboard API endpoints for state, report, nav, map, route, and POI evidence.
- Adds the `unitree-go2-dogops` DimOS blueprint path and a one-command OrbStack web simulation runner.
- Documents the exact real-Go2 validation sequence and honest fallback levels.

Tests:

```text
uv run --no-sync python --version
uv run --no-sync dimos list | rg 'unitree-go2-dogops'
uv run --no-sync pytest -q -o addopts='' dimos/experimental/dogops
uv run --no-sync python -m dimos.experimental.dogops.cli validate
uv run --no-sync python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run --no-sync python -m dimos.experimental.dogops.cli report --run .dogops/runs/latest
uv run --no-sync python -m dimos.experimental.dogops.cli map --run .dogops/runs/latest
uv run --no-sync python -m dimos.experimental.dogops.cli plan --run .dogops/runs/latest --add-waypoint TEMP_1 --add-poi TEMP_1
uv run --no-sync python -m dimos.experimental.dogops.cli run-plan --run .dogops/runs/latest
bash scripts/run_dogops_orbstack_web.sh
```

Not yet claimed until run on hardware:

- autonomous real-Go2 route completion;
- calibrated thermal sensing;
- self-charging or elevator behavior.
