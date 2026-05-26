# Dashboard subagent prompt

Read `AGENTS.md`, `SPEC.md`, `STATUS.md`, and `docs/FAILURE_MEMORY.md` first.

Own only:

```text
dimos/experimental/dogops/report.py
dimos/experimental/dogops/dashboard.py
dimos/experimental/dogops/dashboard_static.py
dimos/experimental/dogops/test_report.py
dimos/experimental/dogops/test_cli_smoke.py
```

Goal: complete Part B dashboard/report layer after Part A works.

Success:

```bash
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765
curl -fsS http://127.0.0.1:8765/api/state | jq .
curl -fsS http://127.0.0.1:8765/api/report | jq .
```

If FastAPI/server fails twice, generate static `dashboard.html` and document fallback.
