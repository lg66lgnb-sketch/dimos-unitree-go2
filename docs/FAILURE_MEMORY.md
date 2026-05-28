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
Later Ubuntu-side verification showed the minimal MCP control plane works after adding docstrings to all DogOps `@skill` methods:
`dimos --viewer none run dog-ops-skill-container mcp-server --daemon`,
`dimos mcp list-tools`, and
`dimos mcp call go_to --json-args '{"x":1.25,"y":-0.5}'`
all succeeded, returning `transport: clicked_point`.
After fixing `DogOpsDashboardModule`, `DogOpsObservationModule`, and `DogOpsNavEvalModule` to initialize the DimOS `Module` base when worker kwargs are injected, the full DogOps blueprint with `--disable go2-connection` daemonized and MCP `go_to` returned `transport: clicked_point`.
Running without `--disable go2-connection` then failed in `GO2Connection.start()` while opening replay SQLite data because `/tmp/dimos-full-dogops-venv/lib/python3.12/site-packages/sqlite_vec/vec0.so` had `wrong ELF class: ELFCLASS32` on Ubuntu aarch64. Inspection showed the `sqlite-vec==0.1.6` wheel installed a 32-bit ARM shared object. Installing `sqlite-vec==0.1.9` into the same temp venv installed a 64-bit AArch64 shared object and unblocked full replay.
With that temp-venv fix, `dimos --replay --viewer none run unitree-go2-dogops --daemon` started all 14 modules, `dimos status` reported run `20260527-175301-unitree-go2-dogops`, and `dimos mcp call go_to --json-args '{"x":0.5,"y":0.75}'` returned `{"ok": true, "transport": "clicked_point"}`.

Fallback:
On Ubuntu aarch64, do not retry full replay with `sqlite-vec==0.1.6`; use a clean temp venv with `sqlite-vec==0.1.9` or persist the dependency bump before rerunning. After `dimos stop`, check for lingering temp-venv forkserver/resource-tracker processes and clean only the processes created by the run.

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
