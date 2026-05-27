# SiteOps Skills Validation

This is the no-dog validation loop for the issue #2 SiteOps skill surface and
the PR #11 MCP surface. It must pass before treating DogOps as ready for a real
Go2 run.

## Local Deterministic Check

```bash
export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/dogops-uv-cache}"
export UV_RUN_ARGS="${UV_RUN_ARGS:---no-sync}"

uv run ${UV_RUN_ARGS} pytest -q dimos/experimental/dogops/test_skills.py
uv run ${UV_RUN_ARGS} python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
```

The direct skill container must cover:

- `scan_zone("INBOUND_DOCK")`: sees tags `20`, `101`, and `102`.
- `scan_receiving_manifest("INBOUND_DOCK")`: reports `PKG-103` missing.
- `read_gauge("TEMP_1")`: returns the deterministic below-threshold fallback.
- `check_clearance("COOLING_1")`: returns clear after the simulated human fix.
- `detect_blocked_aisle("AISLE_1")`: returns not blocked for the demo aisle.
- `verify_work_order("WO-001")`: is idempotent once closed.
- `nav_eval_report()`: reports `4/4` route targets reached.

## Full DimOS MCP Check

Run this in the full DimOS checkout, not just the project pack:

```bash
uv run dimos list | rg dogops
uv run dimos mcp list-tools | rg 'run_mission|go_to|scan_zone|read_gauge|check_clearance|detect_blocked_aisle|scan_receiving_manifest|verify_work_order|nav_eval_report'
```

If replay/MCP startup asks for macOS multicast configuration, apply the DimOS
recommended route manually in a terminal before claiming MCP validation:

```bash
sudo route add -net 224.0.0.0/4 -interface lo0
```

In non-interactive Codex runs, skipping the configurator with `PYTEST_VERSION`
can confirm module deployment, but it is not enough to claim MCP is validated.

When `GO2_IP` is known and the route is clear, prefer the scripted path:

```bash
RUN_GO2_SMOKE=1 RUN_DOGOPS_SMOKE=1 GO2_IP=<GO2_IP> scripts/dogops_go2_preflight.sh
```

The preflight script checks every required MCP tool name individually and saves
logs under `.dogops/preflight/`.
