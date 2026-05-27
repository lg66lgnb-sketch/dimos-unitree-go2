# TEST_LOOPS.md

## Principle

Use fast, narrow checks, but do not defer DimOS registry or real-Go2 validation until the end. The real dog is available, so hardware readiness is part of the core loop.

After two failed corrections on the same issue, stop and write a failure-memory entry before continuing.

## Part 0: Full DimOS Preflight

```bash
git status -sb
uv run python --version
uv run dimos list | rg 'unitree-go2'
uv run pytest -q dimos/utils/cli/test_apriltag.py
uv run dimos apriltag --ids '10,20,101-104' --size-mm 100 --family tag36h11 --out /tmp/dogops-tags.pdf
```

Optional when `GO2_IP` is known:

```bash
uv run dimos stop --force || true
uv run dimos --viewer none run unitree-go2 -o "go2connection.ip=${GO2_IP}" --daemon
uv run dimos status
uv run dimos log -n 100
uv run dimos stop --force
```

## Part A: Offline Core

```bash
uv run pytest -q dimos/experimental/dogops/test_config_loader.py
uv run pytest -q dimos/experimental/dogops/test_store.py
uv run pytest -q dimos/experimental/dogops/test_mission_engine.py
uv run pytest -q dimos/experimental/dogops/test_nav_eval.py
uv run pytest -q dimos/experimental/dogops/test_report.py
uv run python -m dimos.experimental.dogops.cli validate \
  --site examples/dogops/site_demo.yaml \
  --manifest examples/dogops/manifest_demo.yaml \
  --mission examples/dogops/mission_demo.yaml
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
cat .dogops/runs/latest/report.md
```

Expected report facts:

```text
PKG-104 wrong zone
PKG-104 blocks COOLING_1
INC-001 P1 opened
WO-001 ready/verified closed after human fix
PKG-103 missing/open
nav metrics present
```

## Part B: Dashboard

```bash
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765 &
DASH_PID=$!
sleep 2
curl -fsS http://127.0.0.1:8765/api/state | jq .
curl -fsS http://127.0.0.1:8765/api/report | jq .
curl -fsS http://127.0.0.1:8765/api/nav | jq .
kill "$DASH_PID"
```

If port `8765` is busy, use another port and record it.

Dashboard manual control has a separate regression contract because the dashboard UI can change while the basic movement capability should persist:

```bash
uv run pytest -q dimos/experimental/dogops/test_dashboard.py \
  -k 'robot_motion_session or motion_profile or response_status_code'
```

These tests must prove the underlying path still uses native Go2 Sport `Move` plus `StopMove`, applies server-side profile caps, parses Go2 response status codes, restores obstacle avoidance after linear movement, and rejects unauthenticated or non-local robot-control requests. They are CI-safe and do not require hardware.

## Part C: DimOS Registry And MCP

Run this as soon as the blueprint exists:

```bash
uv run pytest -q dimos/experimental/dogops
CI=1 uv run pytest -q -o addopts='' dimos/robot/test_all_blueprints_generation.py || true
git diff -- dimos/robot/all_blueprints.py
CI=1 uv run pytest -q -o addopts='' dimos/robot/test_all_blueprints_generation.py
uv run dimos list | rg dogops
uv run dimos --replay --viewer none run unitree-go2-dogops --daemon || true
uv run dimos status || true
uv run dimos mcp list-tools | rg 'run_mission|go_to|scan_zone|read_gauge|check_clearance|detect_blocked_aisle|scan_receiving_manifest|verify_work_order|nav_eval_report'
uv run dimos stop --force || true
```

If replay deploys modules but `dimos status` or MCP discovery cannot see a running instance, document the exact blocker, check for lingering replay processes, and keep direct skill/CLI fallback working.

## Part D: AprilTag Detector

```bash
uv run dimos apriltag --ids '10,20,30,40,41,42,43,50,60,70,101-104' --size-mm 140 --family tag36h11 --out .dogops/apriltags.pdf
uv run pytest -q dimos/experimental/dogops/test_detector.py
uv run pytest -q dimos/experimental/dogops/test_observation_module.py
```

Generated tag images are enough for CI; real camera/tag visibility is validated during the Go2 rehearsal.

## Part E: Real-Go2 DogOps Smoke

Only run after the route is physically clear and the stop command is known.

```bash
uv run dimos stop --force || true
uv run dimos --viewer none run unitree-go2-dogops -o "go2connection.ip=${GO2_IP}" --daemon
uv run dimos status
uv run dimos mcp list-tools | rg 'run_mission|go_to|scan_zone|read_gauge|check_clearance|detect_blocked_aisle|scan_receiving_manifest|verify_work_order|nav_eval_report'
uv run dimos mcp call run_mission --json-args '{"mission_id":"receiving_sre_demo"}'
uv run dimos mcp call scan_zone --json-args '{"zone_id":"INBOUND_DOCK"}'
uv run dimos mcp call scan_receiving_manifest --json-args '{"zone_id":"INBOUND_DOCK"}'
uv run dimos mcp call read_gauge --json-args '{"asset_id":"TEMP_1"}'
uv run dimos mcp call check_clearance --json-args '{"asset_id":"COOLING_1"}'
uv run dimos mcp call detect_blocked_aisle --json-args '{"zone_id":"AISLE_1"}'
uv run dimos mcp call nav_eval_report
uv run dimos log -n 200
uv run dimos stop --force
```

If navigation is unsafe, use guided mode and record `guided=true`. If MCP is unavailable, run the CLI/dashboard fallback and collect Go2 movement/tag footage separately.

For the real dashboard manual-control smoke, use the profile controls in order:

```text
Wake / Stand
Step + Forward
Step + Left
Step + Right
Step + Back
Yaw L
Yaw R
HARD STOP
Sleep
```

Each movement must report observed odometry (`cm` or `deg`). A successful HTTP response without observed odometry is not enough evidence.

## Commit-Ready Check

```bash
git status --short
uv run pytest -q dimos/experimental/dogops
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run ruff check dimos/experimental/dogops dimos/robot || true
uv run dimos list | rg dogops
git diff --check
```

If ruff is unavailable, record that and rely on tests plus `git diff --check` until lint tooling is installed. Do not commit `.dogops/`, generated tags, screenshots, videos, local logs, private IPs, or device IDs.
