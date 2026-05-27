# SUBAGENTS.md

Use this only if the work is split across Codex subagents/worktrees.

## Rules

- Every subagent reads `AGENTS.md`, `SPEC.md`, `STATUS.md`, and `docs/FAILURE_MEMORY.md` first.
- Every subagent states success criteria before coding.
- Every subagent owns specific files.
- No two subagents edit the same file at the same time.
- Each subagent returns changed files, commands run, failures, and remaining risks.
- Merge only after targeted checks pass.

## Suggested subagents

### Core subagent

Owns:

```text
dimos/experimental/dogops/models.py
dimos/experimental/dogops/config_loader.py
dimos/experimental/dogops/store.py
dimos/experimental/dogops/mission_engine.py
dimos/experimental/dogops/test_config_loader.py
dimos/experimental/dogops/test_store.py
dimos/experimental/dogops/test_mission_engine.py
examples/dogops/*.yaml
```

Success:

```bash
uv run pytest -q dimos/experimental/dogops/test_config_loader.py dimos/experimental/dogops/test_store.py dimos/experimental/dogops/test_mission_engine.py
```

### Dashboard subagent

Owns:

```text
dimos/experimental/dogops/report.py
dimos/experimental/dogops/dashboard.py
dimos/experimental/dogops/dashboard_static.py
dimos/experimental/dogops/test_report.py
dimos/experimental/dogops/test_cli_smoke.py
```

Success:

```bash
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765
```

### DimOS integration subagent

Owns:

```text
dimos/experimental/dogops/skills.py
dimos/experimental/dogops/blueprints.py
dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py
dimos/robot/all_blueprints.py
```

Success:

```bash
uv run dimos list | rg dogops
uv run pytest dimos/robot/test_all_blueprints_generation.py
uv run dimos mcp list-tools | rg 'run_mission|scan_zone|read_gauge|check_clearance|detect_blocked_aisle|scan_receiving_manifest|verify_work_order|nav_eval_report'
```

### Perception subagent

Owns:

```text
dimos/experimental/dogops/detector.py
dimos/experimental/dogops/observation_module.py
dimos/experimental/dogops/test_detector.py
```

Success:

```bash
uv run dimos apriltag --ids '10,20,101-104' --size-mm 100 --family tag36h11 --out /tmp/dogops-tags.pdf
uv run pytest -q dimos/experimental/dogops/test_detector.py
```

### NavEval subagent

Owns:

```text
dimos/experimental/dogops/nav_eval.py
dimos/experimental/dogops/test_nav_eval.py
```

Success:

```bash
uv run pytest -q dimos/experimental/dogops/test_nav_eval.py
```

### Demo docs subagent

Owns:

```text
docs/dogops/*.md
README.md
STATUS.md
```

Success:

- Docs match implemented behavior.
- No private data.
- 90-second script is ready.

### Hardware subagent

Owns:

```text
docs/RUNBOOK_MAC_GO2.md
docs/SAFETY.md
docs/dogops/HARDWARE_HANDOFF.md
docs/dogops/TAGS.md
```

Success:

```bash
uv run dimos list | rg 'unitree-go2'
uv run dimos run unitree-go2 --robot-ip "$GO2_IP" --viewer none --daemon
uv run dimos status
uv run dimos stop --force
```

After DogOps registry passes, also verify `unitree-go2-dogops` or document the exact blocker and fallback level.
