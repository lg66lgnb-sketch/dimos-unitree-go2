# Core subagent prompt

Read `AGENTS.md`, `SPEC.md`, `STATUS.md`, and `docs/FAILURE_MEMORY.md` first.

Own only:

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

Goal: complete Part A offline core. Do not edit dashboard, blueprint, or perception files.

Success:

```bash
uv run pytest -q dimos/experimental/dogops/test_config_loader.py dimos/experimental/dogops/test_store.py dimos/experimental/dogops/test_mission_engine.py
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
```

If stuck twice, update `docs/FAILURE_MEMORY.md` and `STATUS.md`, then use the Part A fallback from `SPEC.md`.
