# DogOps Hardware Handoff

This is the Mac/Go2 handoff checklist. The real Go2 is available, so final validation should happen from the full DimOS checkout at `$DIMOS_ROOT`.

Do not use UTM unless the active thread is explicitly a VM-only development thread.

## 1. Full DimOS Sanity Check

```bash
cd $DIMOS_ROOT
export PYTHONPATH=$DIMOS_ROOT
export PYTEST_VERSION=codex
export UV_CACHE_DIR=${TMPDIR:-/tmp}/dimos-uv-cache
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
uv run --no-sync python --version
uv run --no-sync dimos list | rg 'unitree-go2'
uv run --no-sync pytest -q -o addopts='' dimos/utils/cli/test_apriltag.py
uv run --no-sync dimos apriltag --ids '10,20,101-104' --size-mm 100 --family tag36h11 --out /tmp/dogops-tags.pdf
```

Fast path when the robot is in front of you:

```bash
cd $DIMOS_ROOT
export GO2_IP=<GO2_IP>
./scripts/dogops_go2_preflight.sh
RUN_GO2_SMOKE=1 ./scripts/dogops_go2_preflight.sh
RUN_DOGOPS_SMOKE=1 ./scripts/dogops_go2_preflight.sh
```

Keep this command visible before starting any hardware smoke:

```bash
uv run dimos stop --force
```

After DogOps is implemented:

```bash
uv run --no-sync pytest -q -o addopts='' dimos/experimental/dogops
uv run --no-sync python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run --no-sync ruff check dimos/experimental/dogops dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py || true
uv run --no-sync dimos list | rg dogops
uv run --no-sync dimos mcp list-tools | rg 'run_mission|scan_zone|read_gauge|check_clearance|detect_blocked_aisle|scan_receiving_manifest|verify_work_order|nav_eval_report'
```

If ruff is unavailable in the full DimOS venv, record that and continue with tests plus `git diff --check`. If replay deploys DogOps modules plus `McpServer` but `dimos status` and `dimos mcp list-tools` do not see a running instance, treat MCP exposure as unvalidated until the hardware run or a corrected DimOS launch mode proves it.

## 2. Print Tags

```bash
cd $DIMOS_ROOT
uv run --no-sync dimos apriltag \
  --ids '10,20,30,40,41,42,43,50,60,70,101-104' \
  --size-mm 140 \
  --family tag36h11 \
  --out dogops-tags-140mm.pdf
```

Mount tags vertically with white margin and large human-readable labels. See [TAGS.md](TAGS.md).

## 3. Arena Checklist

Minimum route:

```text
HOME -> INBOUND_DOCK -> RACK_ROW_A / COOLING_1 -> QA_HOLD -> HOME
```

Checklist:

- Tag 10 at `HOME`.
- Tag 20 at `INBOUND_DOCK`.
- Tags 101 and 102 on visible inbound packages.
- Do not place tag/package 103; it is intentionally missing.
- Tag 40 at `RACK_ROW_A`.
- Tag 41 at `COOLING_1`.
- Put `PKG-104` near/on `COOLING_1` before first inspection.
- Tag 30 at `QA_HOLD`.
- Keep lanes wide and speeds low.
- Human, not robot, moves `PKG-104` to `QA_HOLD`.
- Keep a terminal ready with `uv run dimos stop --force`.

## 4. Base Go2 Smoke

```bash
cd $DIMOS_ROOT
export GO2_IP=<GO2_IP>
ping -c 3 "$GO2_IP"
uv run --no-sync dimos stop --force || true
uv run --no-sync dimos --viewer none run unitree-go2 -o "go2connection.ip=${GO2_IP}" --daemon
uv run --no-sync dimos status
uv run --no-sync dimos log -n 100
uv run --no-sync dimos stop --force
```

If this fails, stop DogOps hardware work and record the exact network/WebRTC/log blocker.

## 5. DogOps Dry Run

```bash
uv run --no-sync dimos stop --force || true
uv run --no-sync dimos --viewer none run unitree-go2-dogops -o "go2connection.ip=${GO2_IP}" --daemon
uv run --no-sync dimos status
uv run --no-sync dimos mcp list-tools | rg 'run_mission|scan_zone|read_gauge|check_clearance|detect_blocked_aisle|scan_receiving_manifest|verify_work_order|nav_eval_report'
uv run --no-sync dimos mcp call run_mission --json-args '{"mission_id":"receiving_sre_demo"}'
uv run --no-sync dimos mcp call scan_zone --json-args '{"zone_id":"INBOUND_DOCK"}'
uv run --no-sync dimos mcp call scan_receiving_manifest --json-args '{"zone_id":"INBOUND_DOCK"}'
uv run --no-sync dimos mcp call read_gauge --json-args '{"asset_id":"TEMP_1"}'
uv run --no-sync dimos mcp call check_clearance --json-args '{"asset_id":"COOLING_1"}'
uv run --no-sync dimos mcp call detect_blocked_aisle --json-args '{"zone_id":"AISLE_1"}'
uv run --no-sync dimos mcp call nav_eval_report
uv run --no-sync dimos log -n 200
uv run --no-sync dimos stop --force
```

If autonomous navigation is unsafe, stop and use guided mode. If MCP is blocked, use CLI/dashboard fallback plus robot footage and record fallback level.

CLI/dashboard fallback if MCP is blocked:

```bash
uv run --no-sync python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run --no-sync python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 18765
open http://127.0.0.1:18765
```

## 6. Video Capture Checklist

Capture:

1. Dashboard title: `DogOps SiteOps Agent`.
2. Arena wide shot with tags and boxes.
3. Mission start command or dashboard run state.
4. Go2 at/near inbound dock.
5. Inbound scan showing `PKG-101` and `PKG-102`.
6. `PKG-104` at `COOLING_1`.
7. `INC-001` / `WO-001` P1 work order.
8. Human moving `PKG-104` to `QA_HOLD`.
9. Verification result: `WO-001 verified_closed`.
10. Final report with `PKG-103` still missing/open.
11. Nav eval panel with autonomous/guided metrics visible.

Collect:

- terminal output from commands;
- `.dogops/runs/latest/report.md`;
- `.dogops/runs/latest/report.json`;
- dashboard screenshot or screen recording;
- short Go2 camera/arena clip;
- exact fallback level: L0, L1, L2, or L3.

## 7. Honest Fallback Language

If guided navigation is used:

> This is running on the Go2 with guided navigation for safety. DogOps records that intervention in the nav metrics while the SiteOps loop, work-order lifecycle, verification, and report run live.

If MCP or real-time streams fail:

> This run uses the deterministic DogOps dashboard/report fallback with real Go2 movement evidence. Guided or offline steps are recorded honestly in the navigation metrics.
