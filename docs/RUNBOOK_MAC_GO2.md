# RUNBOOK_MAC_GO2.md

## Goal

Build and run DogOps on the Mac against the real Unitree Go2 Air. This is the primary final path.

UTM/Ubuntu is optional for offline development only. Do not require UTM for final validation when the real dog is available.

## Canonical Local Layout

| Path | Purpose |
|---|---|
| `$DIMOS_ROOT` | Full DimOS checkout; primary build/runtime target |
| `$DOGOPS_REPO` | DogOps project files |
| `a separate DimOS PR checkout` | Optional PR comparison only; do not depend on it |

Start from `$DIMOS_ROOT` unless the user explicitly chooses another full DimOS checkout.

## Mac Environment

```bash
brew install gnu-sed gcc portaudio git-lfs libjpeg-turbo python pre-commit jq ripgrep fd uv
cd $DIMOS_ROOT
uv python install 3.12
uv venv --python 3.12
uv sync --extra base --extra unitree --extra apriltag --extra visualization --extra web --group tests --group lint
```

If dependency resolution is slow, keep the same extras and avoid CUDA/full extras until the core works.

If `mjpython` fails with `Library not loaded: @rpath/libpython3.12.dylib`, add venv-local symlinks:

```bash
ln -s "$HOME/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/lib/libpython3.12.dylib" .venv/libpython3.12.dylib
ln -s "$HOME/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/lib/libpython3.12.dylib" .venv/lib/libpython3.12.dylib
```

## Pre-Codex Verification

```bash
cd $DIMOS_ROOT
git status -sb
uv run python --version
uv run dimos list | rg 'unitree-go2'
uv run pytest -q dimos/utils/cli/test_apriltag.py
uv run dimos apriltag --ids '10,20,101-104' --size-mm 100 --family tag36h11 --out /tmp/dogops-tags.pdf
ls -lh /tmp/dogops-tags.pdf
```

If this fails, fix the DimOS environment before asking Codex to implement DogOps.

## Real Go2 Network Check

Set the IP once known:

```bash
export GO2_IP=<GO2_IP>
ping -c 3 "$GO2_IP"
```

Fast preflight before touching the robot:

```bash
cd $DIMOS_ROOT
export GO2_IP=<GO2_IP>
./scripts/dogops_go2_preflight.sh
```

When the route is clear and a human is at the stop terminal, run the base robot smoke:

```bash
RUN_GO2_SMOKE=1 ./scripts/dogops_go2_preflight.sh
```

Only after base `unitree-go2` passes, run the DogOps hardware smoke:

```bash
RUN_DOGOPS_SMOKE=1 ./scripts/dogops_go2_preflight.sh
```

Then prove the base DimOS robot path:

```bash
uv run dimos stop --force || true
uv run dimos run unitree-go2 --robot-ip "$GO2_IP" --viewer none --daemon
uv run dimos status
uv run dimos log -n 100
uv run dimos stop --force
```

If base `unitree-go2` fails, DogOps hardware cannot be final yet. Save the exact logs, ask DimOS mentors/event staff for robot network help, and continue offline/MCP work.

## Generate And Mount Tags

Use large AprilTag 36h11 prints:

```bash
uv run dimos apriltag \
  --ids '10,20,30,40,41,42,43,50,60,70,101-104' \
  --size-mm 140 \
  --family tag36h11 \
  --out dogops-tags-140mm.pdf
```

Mount vertically with clear white margins and large human labels. Minimum route:

```text
HOME -> INBOUND_DOCK -> RACK_ROW_A / COOLING_1 -> QA_HOLD -> HOME
```

Keep the route short, wide, and slow. The human, not the robot, moves `PKG-104`.

## DogOps Registry And MCP Check

After Codex implements DogOps:

```bash
uv run pytest -q dimos/experimental/dogops
uv run pytest dimos/robot/test_all_blueprints_generation.py || true
git diff -- dimos/robot/all_blueprints.py
uv run pytest dimos/robot/test_all_blueprints_generation.py
uv run dimos list | rg dogops
uv run dimos mcp list-tools | rg 'run_mission|scan_zone|read_gauge|check_clearance|detect_blocked_aisle|scan_receiving_manifest|verify_work_order|nav_eval_report'
```

Do not mark DimOS integration complete until `unitree-go2-dogops` appears in `dimos list`.

## DogOps Hardware Smoke

```bash
uv run dimos stop --force || true
uv run dimos run unitree-go2-dogops --robot-ip "$GO2_IP" --viewer none --daemon
uv run dimos status
uv run dimos mcp list-tools | rg 'run_mission|scan_zone|read_gauge|check_clearance|detect_blocked_aisle|scan_receiving_manifest|verify_work_order|nav_eval_report'
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

If navigation is unstable, switch to guided mode and record `guided=true`. If MCP fails but the local product works, use fallback L2/L3 honestly.

## Dashboard Manual Motion Smoke

When using the DogOps dashboard for simple manual control, use the conservative motion profiles and verify movement from odometry, not from button completion alone.

Expected backend behavior:

- movement buttons call the native Go2 Sport `Move` API and then `StopMove`;
- `HARD STOP` calls `StopMove` and sends zero joystick frames;
- `Nudge`, `Step`, and `Walk` are server-capped profiles;
- robot-control POSTs require the dashboard page's per-server token and loopback origin;
- the server chooses the configured robot IP; browser payloads cannot redirect motion to another host;
- each completed move reports observed distance or yaw from Go2 odometry.

Safe smoke sequence in a clear 2 m x 2 m or larger space:

```text
Wake / Stand
Step + Forward  -> expect non-zero observed cm
Step + Left     -> expect non-zero observed cm
Step + Right    -> expect non-zero observed cm
Step + Back     -> expect non-zero observed cm
Yaw L / Yaw R   -> expect non-zero observed deg
HARD STOP
Sleep
```

If the UI says only `Sent ...` without observed movement, treat that as unverified and debug odometry/motion before claiming hardware control works.

## Fallback Levels

| Level | What runs | When to use |
|---|---|---|
| L0 | Full autonomous Go2 + DogOps dashboard + MCP | Ideal final |
| L1 | Go2 scans tags + guided navigation + dashboard | Navigation flaky |
| L2 | Go2 movement/tag video + offline dashboard/report | MCP or real-time streams flaky |
| L3 | Offline product demo + recorded Go2 clip | Robot/network unavailable |

The final report/video must state the fallback level used.

## Evidence To Collect

- `.dogops/runs/latest/report.md`
- `.dogops/runs/latest/report.json`
- dashboard screenshot or screen recording
- terminal output for registry/MCP/hardware commands
- short robot/arena clip
- fallback level and reason
