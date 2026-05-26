You are building DogOps in a full DimOS checkout using Codex GPT-5.5 with high reasoning (`xhigh`).

Primary workspace:

```text
$DIMOS_ROOT
```

The real Unitree Go2 Air is available. Do not treat hardware as hypothetical. Offline simulation is still required, but the final build must attempt full DimOS registry/MCP validation and a real-Go2 dry run.

Use these Mac/full-DimOS environment guards for local dashboard/MCP checks:

```bash
export PYTHONPATH=$DIMOS_ROOT
export PYTEST_VERSION=codex
export UV_CACHE_DIR=${TMPDIR:-/tmp}/dimos-uv-cache
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
```

First read these files in order:

1. `AGENTS.md`
2. `SPEC.md`
3. `STATUS.md`
4. `docs/FAILURE_MEMORY.md`
5. `docs/RUNBOOK_MAC_GO2.md`
6. `docs/TEST_LOOPS.md`
7. `docs/SAFETY.md`

Product: **DogOps — DimOS SiteOps Agent for Unitree Go2 Air**.

Canonical behavior:

```text
manifest + site policy
-> short route through staged facility
-> scan AprilTag packages/assets
-> reconcile manifest
-> detect PKG-104 in wrong zone and blocking COOLING_1
-> open INC-001 / WO-001
-> wait for human remediation
-> robot revisits COOLING_1
-> verify closure
-> report + dashboard + navigation/relocalization metrics
```

## Non-Negotiables

- `SPEC.md` is canonical. If direction changes, update `SPEC.md` first.
- Build in the full DimOS checkout so registry, CLI, MCP, and hardware checks are real.
- The base demo must run without cloud API keys and without an LLM.
- Do not include `McpClient` in the base DogOps blueprint.
- Do not implement a new monocular SLAM system. Use DimOS primitives and add SiteOps eval/reporting.
- Do not fake autonomy. Guided/teleop fallback is allowed only when recorded in nav metrics and demo narration.
- Do not make the robot push packages. A human moves `PKG-104`; the robot observes and verifies.
- Keep the route short, slow, and safe. Always know the stop command.
- After two failed fixes on one issue, update `docs/FAILURE_MEMORY.md` and choose a fallback.
- Do not push, open PRs, or mutate GitHub unless the active thread explicitly approves that exact action and GitHub auth/account checks pass.

## Part 0 — Full DimOS And Real-Go2 Preflight

Success criteria:

- Current checkout is a full DimOS repo.
- Existing Go2 blueprints are visible.
- Base Go2 hardware smoke is attempted if `GO2_IP` is known.
- Any blocker is recorded in `STATUS.md`.

Run:

```bash
git status -sb
git branch --show-current
uv run dimos list | rg 'unitree-go2'
uv run pytest -q dimos/utils/cli/test_apriltag.py
uv run dimos apriltag --ids '10,20,101-104' --size-mm 100 --family tag36h11 --out /tmp/dogops-tags.pdf
```

If `GO2_IP` is available:

```bash
uv run dimos stop --force || true
uv run dimos run unitree-go2 --robot-ip "$GO2_IP" --viewer none --daemon
uv run dimos status
uv run dimos log -n 100
uv run dimos stop --force
```

If base `unitree-go2` fails, DogOps hardware cannot be final yet. Document the exact logs and continue offline/MCP work.

## Part A — Offline Core

Implement:

- `dimos/experimental/dogops` package.
- `examples/dogops/*.yaml` copied from `config/*.yaml`.
- Models, config loader, store, mission engine, nav eval, report, and CLI.
- Deterministic simulated mission for `receiving_sre_demo`.

Make this work:

```bash
uv run python -m dimos.experimental.dogops.cli validate \
  --site examples/dogops/site_demo.yaml \
  --manifest examples/dogops/manifest_demo.yaml \
  --mission examples/dogops/mission_demo.yaml
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
cat .dogops/runs/latest/report.md
uv run pytest -q dimos/experimental/dogops
```

Report must include `PKG-104`, `COOLING_1`, `INC-001`, `WO-001`, `PKG-103 missing`, work-order closure after human remediation, and nav metrics.

## Part B — Dashboard

Implement a low-dependency dashboard first:

- Static `dashboard.html` generated into the run directory.
- Local server command.
- JSON endpoints for state, report, and nav metrics.

Verify:

```bash
uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765
curl -fsS http://127.0.0.1:8765/api/state | jq .
curl -fsS http://127.0.0.1:8765/api/report | jq .
curl -fsS http://127.0.0.1:8765/api/nav | jq .
```

If port `8765` is busy, use another port and record it.

## Part C — DimOS Registry And MCP

Do this before spending time on polish.

Implement:

- `DogOpsSkillContainer` with `@skill` methods from `SPEC.md`.
- `unitree_go2_dogops` blueprint without `McpClient`.
- Registry entry generated through DimOS test tooling.
- DogOps modules that tolerate DimOS worker-injected kwargs such as `g=`.
- A real module-level blueprint in `dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py`; fallback metadata is only for import tests outside full DimOS.

Verify:

```bash
uv run --no-sync pytest -q -o addopts='' dimos/experimental/dogops
CI=1 uv run --no-sync pytest -q -o addopts='' dimos/robot/test_all_blueprints_generation.py || true
git diff -- dimos/robot/all_blueprints.py
CI=1 uv run --no-sync pytest -q -o addopts='' dimos/robot/test_all_blueprints_generation.py
uv run --no-sync dimos list | rg dogops
uv run --no-sync dimos --replay --viewer none run unitree-go2-dogops --daemon || true
uv run --no-sync dimos status || true
uv run --no-sync dimos mcp list-tools | rg 'run_mission|scan_zone|verify_work_order|nav_eval_report'
uv run --no-sync dimos stop --force || true
```

If replay deploys modules but `dimos status` or `dimos mcp list-tools` cannot see a running instance, document the exact blocker, check for lingering replay processes, and keep direct CLI/skill fallback working. Do not let this break Part A/B.

## Part D — AprilTag Observation

Implement:

- Tag registry for zones/assets/packages/dock/portal.
- Optional OpenCV `cv2.aruco` detector for tag36h11.
- Simulated tag input for deterministic tests.
- Observation module facade that can consume image frames when DimOS streams are available.

Verify:

```bash
uv run dimos apriltag --ids '10,20,30,40,41,42,43,50,60,70,101-104' --size-mm 140 --family tag36h11 --out .dogops/apriltags.pdf
uv run pytest -q dimos/experimental/dogops/test_detector.py
uv run pytest -q dimos/experimental/dogops
```

## Part E — Real-Go2 DogOps Dry Run

After Parts A-D pass, attempt the hardware path.

First print/mount tags using `docs/RUNBOOK_MAC_GO2.md` and `docs/SAFETY.md`.

Then:

```bash
uv run dimos stop --force || true
uv run dimos run unitree-go2-dogops --robot-ip "$GO2_IP" --viewer none --daemon
uv run dimos status
uv run dimos mcp list-tools | rg 'run_mission|scan_zone|verify_work_order|nav_eval_report'
uv run dimos mcp call run_mission --json-args '{"mission_id":"receiving_sre_demo"}'
uv run dimos mcp call scan_zone --json-args '{"zone_id":"INBOUND_DOCK"}'
uv run dimos mcp call nav_eval_report
uv run dimos stop --force
```

If autonomous navigation is unstable, use guided mode and record `guided=true`. If MCP is unstable, use CLI/dashboard plus real Go2 footage and record fallback level.

## Part F — Demo Hardening

Required before final:

- Three local dry runs in a row.
- One real-Go2 or guided rehearsal attempt.
- 90-second script checked against `docs/DEMO.md`.
- Evidence collected: report markdown, report JSON, dashboard screenshot/recording, terminal logs, robot clip, fallback level.

## Final Handoff

Before final response:

```bash
uv run pytest -q dimos/experimental/dogops
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run ruff check dimos/experimental/dogops dimos/robot || true
uv run dimos list | rg dogops
git diff --check
git status -sb
```

If `ruff` is unavailable in the full DimOS venv, record that explicitly and rely on tests plus `git diff --check` until lint tooling is installed.

Final response must state:

- changed files;
- commands run and results;
- hardware command results;
- whether `unitree-go2-dogops` appears in `dimos list`;
- whether MCP tools are visible;
- exact fallback level, if any;
- remaining risks.
