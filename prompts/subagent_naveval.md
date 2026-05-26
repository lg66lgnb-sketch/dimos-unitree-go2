# NavEval subagent prompt

Read `AGENTS.md`, `SPEC.md`, `STATUS.md`, and `docs/FAILURE_MEMORY.md` first.

Own only:

```text
dimos/experimental/dogops/nav_eval.py
dimos/experimental/dogops/test_nav_eval.py
```

Goal: produce honest navigation/relocalization metrics for every DogOps run.

Metrics must include waypoint success, retries, guided interventions, tag reacquisition, elapsed time, and notes.

Success:

```bash
uv run pytest -q dimos/experimental/dogops/test_nav_eval.py
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
jq .nav_summary .dogops/runs/latest/report.json
```
