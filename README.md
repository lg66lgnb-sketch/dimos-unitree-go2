# DogOps Codex Project Pack

This pack is the launch material for building **DogOps: DimOS SiteOps Agent** in a full DimOS checkout with a real Unitree Go2 Air available.

Use it with Codex `/goal` on GPT-5.5 with high reasoning (`xhigh`). The goal prompt is in [codex_goal.txt](codex_goal.txt) and duplicated in [CODEX_GOAL.md](CODEX_GOAL.md).

## What DogOps Must Do

DogOps turns a Go2 into a closed-loop physical operations agent:

```text
manifest + site policy
-> short real-world route through the demo facility
-> scan AprilTag packages/assets
-> reconcile manifest
-> detect PKG-104 blocking COOLING_1
-> open INC-001 / WO-001
-> wait while a human moves PKG-104 to QA_HOLD
-> revisit COOLING_1
-> verify closure
-> dashboard + report + navigation metrics
```

The base demo requires no cloud API keys and no LLM. Optional LLM narration is stretch only.

## Where To Build

Primary target:

```bash
cd $DIMOS_ROOT
```

Copy these project files into the DimOS repo root before starting `/goal`. The final submission must validate against the full DimOS CLI, blueprint registry, and MCP tooling.

UTM/Ubuntu is optional for offline development only. With the real Go2 available, the Mac/full-DimOS path is the source of truth.

## Start Command

In Codex, open a worktree/thread rooted at the full DimOS checkout and paste [codex_goal.txt](codex_goal.txt) into `/goal`.

Before coding, Codex should verify:

```bash
git status -sb
git branch --show-current
uv run dimos list | rg 'unitree-go2'
```

If the Go2 IP is known:

```bash
GO2_IP=<GO2_IP> ./scripts/verify_env.sh
```

## Starter Files

| Path | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | Agent behavior, safety, and Git rules |
| [SPEC.md](SPEC.md) | Canonical product and acceptance criteria |
| [STATUS.md](STATUS.md) | Build phase ledger |
| [codex_goal.txt](codex_goal.txt) | Prompt to paste into `/goal` |
| [CODEX_GOAL.md](CODEX_GOAL.md) | Markdown duplicate of the goal prompt |
| [config/](config) | Demo site, manifest, mission, and policy inputs |
| [docs/RUNBOOK_MAC_GO2.md](docs/RUNBOOK_MAC_GO2.md) | Primary real-Go2 runbook |
| [docs/TEST_LOOPS.md](docs/TEST_LOOPS.md) | Required local, DimOS, and hardware checks |
| [docs/SAFETY.md](docs/SAFETY.md) | Robot safety and stop commands |
| [docs/dogops/HARDWARE_HANDOFF.md](docs/dogops/HARDWARE_HANDOFF.md) | Video/evidence checklist |
| [scripts/verify_env.sh](scripts/verify_env.sh) | Full-DimOS and optional Go2 preflight |

## Required Final Checks

The build is not complete until these are true in `$DIMOS_ROOT`:

```bash
uv run pytest -q dimos/experimental/dogops
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run ruff check dimos/experimental/dogops dimos/robot || true
uv run dimos list | rg dogops
uv run dimos mcp list-tools | rg 'run_mission|scan_zone|verify_work_order|nav_eval_report'
```

And with the real Go2:

```bash
uv run dimos stop --force || true
uv run dimos run unitree-go2 --robot-ip <GO2_IP> --viewer none --daemon
uv run dimos status
uv run dimos stop --force
```

Then run the DogOps blueprint or an explicitly documented guided fallback and capture the 90-second demo video.
