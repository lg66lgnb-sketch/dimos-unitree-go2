# STATUS.md

This file is the DogOps implementation ledger. It should be copied into a full DimOS checkout before starting Codex `/goal`.

`SPEC.md` is canonical. Update this file whenever a phase changes state or a fallback becomes necessary.

## Current Decision

Build **DogOps — DimOS SiteOps Agent** from `$DOGOPS_REPO`, with final registry/MCP and hardware validation against the full DimOS checkout at `$DIMOS_ROOT`.

The real Unitree Go2 Air is available. Offline simulation remains the first safety net, but the build is not final until full DimOS registry/MCP validation and a real-Go2 demo path are attempted and documented.

## Known Environment

| Item | Current value |
|---|---|
| Robot | Unitree Go2 Air available |
| Primary build host | offboard host, full DimOS checkout |
| Project repo | `$DOGOPS_REPO` |
| Full DimOS target | `$DIMOS_ROOT` |
| Ubuntu/UTM | Optional only; do not make it required for final validation |
| Python env | `uv`, Python 3.12 |
| Internet | Somewhat reliable; base demo must not depend on it |
| API keys | None required; LLM/Gemini/OpenAI stretch only |
| Demo space | Indoor/office, about 10 m x 10 m |
| Demo type | 90-second video plus live demo |
| Human remediation | Required and allowed: human moves `PKG-104` |

## Materials Available

- Unitree Go2 Air.
- Offboard host running DimOS.
- Paper boxes.
- PVC barrier tape.
- AprilTag 36h11 prints.
- Quick clamps.
- Small traffic cones.
- Sticky A4 paper and pens.
- Power bank.
- Thermometer for optional manual reading only.

## Implementation Guardrails

- Offline tests and dry runs are not enough. The product must be integrated into the full DimOS checkout so `dimos list | rg dogops` works.
- Do not postpone DimOS registry/MCP validation to the end. Add the blueprint early and keep it importable while the package evolves.
- DogOps modules used as DimOS workers should tolerate framework-injected kwargs such as `g=`.
- Prefer a real module-level `unitree_go2_dogops` blueprint in `dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py`; keep fallback metadata only for non-full-DimOS import tests.
- Use `NO_PROXY=127.0.0.1,localhost` and `no_proxy=127.0.0.1,localhost` around localhost dashboard/MCP checks.
- Direct skill/CLI fallback is useful, but the base goal is full `unitree-go2-dogops` registry and MCP visibility.
- OpenCV AprilTag detection works as an optional dependency; simulated tag input must remain available for deterministic tests.
- The dashboard should stay static/low-dependency first, with JSON endpoints for state/report/nav.
- Real-Go2 testing must start with base `unitree-go2` smoke before DogOps-specific runs.
- Guided navigation is acceptable only when recorded honestly in nav metrics and demo narration.

## Phase Ledger

| Phase | Status | Success criteria |
|---|---|---|
| Part 0 — full DimOS preflight | Not started | `uv run dimos list` works; base `unitree-go2` is listed; Go2 network smoke attempted if `GO2_IP` known |
| Part A — offline core | Not started | simulated mission opens/verifies incidents and writes report |
| Part B — dashboard | In progress | dashboard shows run state/report/nav metrics; manual Go2 controls use Sport `Move`/`StopMove` and report odometry |
| Part C — DimOS registry/MCP | Not started | `unitree-go2-dogops` appears in `dimos list`; DogOps MCP tools visible or exact blocker documented |
| Part D — AprilTag observation | Not started | detector reads generated tags and supports simulated/real image observations |
| Part E — real-Go2 dry run | Not started | base `unitree-go2` smoke passes; DogOps blueprint starts or documented blocker exists |
| Part F — demo hardening | Not started | 3 stable local dry runs plus at least one hardware/guided rehearsal |
| Part G — 90-second video | Not started | video shows closed loop, dashboard, report, and fallback level if any |
| Part H — stretch | Deferred | dock alignment and portal simulation only after core works |

## Recent Hardware Notes

- Dashboard manual controls were validated against the real Go2 through WebRTC on the local robot network.
- The reliable basic-control path is native Go2 Sport `Move` (`api_id=1008`) followed by `StopMove` (`api_id=1003`), not wireless-controller joystick emulation.
- The dashboard now exposes `Nudge`, `Step`, and `Walk` motion profiles and reports observed odometry after each move.
- Latest measured profile smoke: `Step + Forward` observed about 9 cm; `Walk + Forward` observed about 14 cm. Use odometry output as the feedback signal, not HTTP success alone.

## Required Acceptance Checklist

- `uv run pytest -q dimos/experimental/dogops` passes.
- `uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest` produces a coherent report.
- Dashboard opens and shows report/state/nav metrics.
- `uv run dimos list | rg dogops` shows `unitree-go2-dogops`.
- `uv run dimos mcp list-tools` exposes `run_mission`, `scan_zone`, `verify_work_order`, and `nav_eval_report`, or an exact blocker plus direct fallback is documented.
- Base `unitree-go2` hardware smoke is attempted against the real robot.
- DogOps hardware/guided run is attempted, or a specific DimOS/robot blocker is documented.
- 90-second demo video shows the closed loop.
- README explains offline and Go2 paths.
- `STATUS.md` accurately states what is complete, guided, stretch, or blocked.

## Failure Memory Pointer

Repeated failures must be recorded in `docs/FAILURE_MEMORY.md` before changing strategy. Do not retry the same failing path more than twice without a new fact.
