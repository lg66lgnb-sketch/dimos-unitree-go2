# FAILURE_MEMORY.md

Use this file to prevent repeated dead ends during the hackathon.

## Rules

- After two failed fixes on the same issue, stop and write an entry here.
- Include the exact command, error summary, what was tried, what was learned, and the fallback.
- Do not delete entries during the hackathon.
- Do not continue retrying a recorded failed approach unless a new fact changes the situation.

## Template

```markdown
## YYYY-MM-DD HH:MM — short issue title

Command:
`...`

Error summary:
`...`

Tried:
1. ...
2. ...

Learned:
- ...

Decision / fallback:
- ...

Status impact:
- ...
```

## Known likely failures and default fallbacks

### Go2 simulation starts but route execution has no odom feedback

Command:
`PYTEST_VERSION=codex PYTHONPATH=<full-dimos-validation-checkout> <full-dimos-venv>/bin/dimos --simulation --viewer rerun --rerun-open none --rerun-web run unitree-go2-dogops`

Follow-up command:
`POST /api/map/routes/follow {"route_id":"SIM_POI_ROUTE_2","dry_run":false}`

Observed on 2026-05-27:
The blueprint deployed `GO2Connection`, `ReplanningAStarPlanner`, `DogOpsSkillContainer`, `RerunBridgeModule`, `VoxelGridMapper`, and Rerun Web. The route API published goals through `clicked_point`, but live route execution failed after retry with `last_error: "no odom received"`. DimOS logs also reported `Cannot handle goal request: missing odometry.`

Tried:
1. Running the dashboard from the project-pack venv, which could not import full DimOS topic dependencies.
2. Running the dashboard from a disposable full-DimOS worktree and venv.
3. Wiring `DogOpsSkillContainer` to subscribe to the blueprint `odom` stream directly.

Learned:
- The route authoring, route selection, dry-run, `clicked_point` publish path, Rerun Web, camera, LiDAR, and pointcloud topic wiring are present.
- The current local Go2 MuJoCo simulation did not produce odometry to the planner or DogOps route feedback path during this run.

Decision / fallback:
- Do not claim live route completion in this simulator state.
- Use real-Go2 or a known-good sim odom source to validate full autonomous POI routing; keep dry-run and command-publish tests as the local fallback.

Status impact:
- Real-dog readiness still needs one odom-backed route test from lower-map POI selection to return-home completion.

### DogOps tests pass but full DimOS registry is missing

Command:
`uv run dimos list | rg dogops`

Fallback:
Do not claim final integration. Build DogOps in the full DimOS checkout, run blueprint registry generation, then rerun `dimos list` and MCP checks.

### DimOS worker injects unexpected constructor kwargs

Symptom:
DogOps modules deploy through a blueprint but fail with an unexpected keyword argument such as `g`.

Fallback:
Keep DogOps module constructors strict for known config fields but tolerant of framework kwargs, for example `**_: object`, and add direct module tests.

### Replay deploys modules but MCP is not discoverable

Commands:
`uv run dimos --replay --viewer none run unitree-go2-dogops --daemon`
`uv run dimos status`
`uv run dimos mcp list-tools`

Symptom:
Replay logs show DogOps modules and `McpServer` deploying, but `dimos status` reports no running instance or `dimos mcp list-tools` reports no running MCP server.

Observed on 2026-05-27 in the full DimOS checkout:
normal replay was blocked by non-interactive sudo for `route add -net 224.0.0.0/4 -interface lo0`.
Using `PYTEST_VERSION=8.3.5` skipped the configurator and deployed the DogOps modules plus `McpServer`, but daemon discovery still returned no running instance.

Fallback:
Do not claim MCP validation. Try a different documented DimOS launch mode or real hardware run, check for lingering replay processes, stop with `uv run dimos stop --force`, and ask before killing OS processes directly. Use direct DogOps CLI/skill tests and dashboard/report output as fallback evidence.

### Localhost dashboard or MCP calls use a proxy

Symptom:
Localhost API checks fail even though the server is running.

Fallback:
Run with:

```bash
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
```

### Full DimOS venv has no ruff executable

Command:
`uv run ruff check ...`

Fallback:
Run ruff where available, or record that the full DimOS venv lacks `ruff` and rely on tests plus `git diff --check` until lint tooling is installed.

### Blueprint registry updates file and test fails

Command:
`uv run pytest dimos/robot/test_all_blueprints_generation.py`

Expected behavior:
The command can update `dimos/robot/all_blueprints.py` and fail because the file changed.

Fallback:
Inspect diff, keep the generated change if correct, rerun the same command.

### Replay data missing

Command:
`uv run dimos --replay --viewer none run unitree-go2-dogops --daemon`

Fallback:
Use offline CLI and direct skill tests. Do not block offline/dashboard work on LFS replay data.

### Dashboard dependency problem

Command:
`uv run python -m dimos.experimental.dogops.cli serve ...`

Fallback:
Generate static `dashboard.html`, `state.json`, and `report.json`; skip live server until later.

### Real Go2 base smoke fails

Command:
`uv run dimos --viewer none run unitree-go2 -o go2connection.ip=<GO2_IP> --daemon`

Fallback:
Stop with `uv run dimos stop --force`, save `dimos log -n 200`, ask DimOS/event staff for network/WebRTC help, and continue offline/MCP work. Do not run `unitree-go2-dogops` until base `unitree-go2` is healthy.

### AprilTag detector cannot use camera stream

Fallback:
Keep direct generated-image detector tests. Add guided `simulated_tag_ids` argument to `scan_zone`. Continue with product demo and return to real stream later.

### Full DimOS venv has empty dist-info packages

Commands:
`uv sync`
`uv pip install click==8.3.1`
`uv run --no-sync dimos list`

Symptom:
The full checkout `.venv` can contain empty `*.dist-info` directories after a failed or partial install. `dimos list` then fails on missing imports such as `click` or `pydantic`, even though `uv tree` resolves them.

Fallback:
Do not keep patching one dependency at a time. Create a clean temporary run environment, for example with `UV_PROJECT_ENVIRONMENT=/private/tmp/dimos-go2-venv`, and run hardware commands through that venv. Rebuild the full checkout `.venv` later when the robot run is not time-sensitive.
