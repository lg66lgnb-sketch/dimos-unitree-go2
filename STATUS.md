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
| Part 0 — full DimOS preflight | Partial | full checkout lists `unitree-go2` and `unitree-go2-dogops`; Go2 network smoke still requires `GO2_IP` and the real robot |
| Part A — offline core | Done | simulated mission opens/verifies incidents and writes report |
| Part B — dashboard | Done | first screen shows rerun-style mission map plus DogOps run metrics; manual Go2 controls use Sport `Move`/`StopMove`, map `go_to`, authored route run/stop/status controls, and report odometry |
| Part C — DimOS registry/MCP | Partial | full checkout registry passes; replay deploys DogOps modules plus `McpServer`, but MCP discovery still reports no running server |
| Part D — AprilTag observation | Done | detector reads generated tags and supports simulated/real image observations |
| Part E — real-Go2 dry run | Not started | base `unitree-go2` smoke passes; DogOps blueprint starts or documented blocker exists |
| Part F — demo hardening | Not started | 3 stable local dry runs plus at least one hardware/guided rehearsal |
| Part G — 90-second video | Not started | video shows closed loop, dashboard, report, and fallback level if any |
| Part H — stretch | Deferred | dock alignment and portal simulation only after core works |

## Recent Hardware Notes

- Dashboard manual controls were validated against the real Go2 through WebRTC on the local robot network.
- The reliable basic-control path is native Go2 Sport `Move` (`api_id=1008`) followed by `StopMove` (`api_id=1003`), not wireless-controller joystick emulation.
- The dashboard now exposes `Nudge`, `Step`, and `Walk` motion profiles and reports observed odometry after each move.
- Latest measured profile smoke: `Step + Forward` observed about 9 cm; `Walk + Forward` observed about 14 cm. Use odometry output as the feedback signal, not HTTP success alone.
- The dashboard first screen now splits into a mission map and DogOps/Go2 control surface. The map uses demo site poses, nav route, observations, packages, incidents, and no-go zones from the run state.
- `scripts/dogops_go2_preflight.sh` is the reconnect checklist script. It validates DogOps tests/sim, DimOS registry, MCP tools, and optional `GO2_IP` ping before any explicit hardware smoke.
- Local project-pack verification on 2026-05-27: DogOps tests, simulate, ruff, dashboard visual check, and script syntax passed. The project pack still lacks a `dimos` console script, so full registry checks must run from the full DimOS checkout.
- Full DimOS verification on 2026-05-27 from `/Users/uiye2048/OrbStack/dimos-dev/home/uiye2048/dimos`: copied DogOps runtime files into the full checkout, regenerated `dimos/robot/all_blueprints.py`, and confirmed `uv run --no-sync dimos list | rg 'unitree-go2$|unitree-go2-dogops'` prints both `unitree-go2` and `unitree-go2-dogops`.
- Full DimOS DogOps tests passed on 2026-05-27: `uv run --no-sync pytest -q dimos/experimental/dogops` reported 45 passed, 1 skipped. Full checkout dry run also passed via `PORT=18767 RUN_DIR=/private/tmp/dogops-full-dry-run scripts/dogops_demo_dry_run.sh`.
- Full DimOS replay/MCP smoke on 2026-05-27: production replay is blocked by non-interactive sudo for `route add -net 224.0.0.0/4 -interface lo0`; with `PYTEST_VERSION=8.3.5` to skip system configuration, replay deployed `DogOpsDashboardModule`, `DogOpsObservationModule`, `DogOpsSkillContainer`, `DogOpsNavEvalModule`, and `McpServer`, but `dimos status` still reported no running instance and `dimos mcp list-tools` reported no running MCP server. Do not claim MCP validated until a real run or corrected launch mode proves it.
- Fake-data dashboard rehearsal on 2026-05-27: local dashboard opened at `http://127.0.0.1:18765` with a rerun-style occupancy/trajectory/tag-return map on the left and DogOps/Go2 controls on the right; 3 repeated dry runs passed and the dry-run script now checks `/api/map`.
- GitHub issue #10 is the current dashboard architecture track: rerun-style visualization stays separate from the DogOps control shell, while robot commands go through DimOS endpoints/skills. Keyboard jog shortcuts are now part of that control shell.
- Issue #10 follow-up from PR #14 guidance: the 18765 dashboard keeps Rerun Web as the visualization surface with an embedded loopback-only connect panel plus launch link, and adds armed map click-to-go through the local/token-protected `/api/robot/go_to` endpoint, which forwards to the DogOps MCP `go_to(x, y)` skill and publishes a DimOS `clicked_point` navigation target instead of sending commands through Rerun.
- Full DimOS Issue #10 sync on 2026-05-27: copied the dashboard/MCP `go_to` changes into `/Users/uiye2048/OrbStack/dimos-dev/home/uiye2048/dimos`; `UV_PROJECT_ENVIRONMENT=/private/tmp/dimos-full-dogops-venv uv run dimos list | rg 'unitree-go2$|unitree-go2-dogops'` printed both entries, and full checkout DogOps tests reported 53 passed, 1 skipped. `dimos mcp list-tools` still reports no running MCP server until a DogOps runtime is started successfully.
- GitHub issue #7 checkpoint sign-in is partially implemented in the offline path: the report/dashboard now verifies route checkpoints by expected AprilTag observation (`HOME` 10, `INBOUND_DOCK` 20, `COOLING_1` 41, `QA_HOLD` 30).
- GitHub issue #2 / PR #11 SiteOps skill surface is implemented in the deterministic path: `read_gauge`, `check_clearance`, `detect_blocked_aisle`, and `scan_receiving_manifest` now run without cloud keys or the real dog, and `scripts/dogops_go2_preflight.sh` checks each required MCP tool individually.
- GitHub issue #19 editable map authoring is implemented in the offline dashboard path: `map_authoring.json` persists home/entity/no-go/route/incident/tag edits, `/api/map` composes authored semantic state with live DimOS overlays, the dashboard supports select/delete/drag, observation-based placement, route selection/reorder/delete, no-go publish fallback, and run-local YAML export writes `exports/site_authoring.yaml` plus selected-route `exports/mission_authoring.yaml`. Full `dimos list | rg dogops` still requires the full DimOS checkout because this project-pack worktree has no `dimos` console script.
- GitHub issue #23 QR cargo bridge integration is implemented in the offline dashboard path: protected `/api/qr/events` ingestion persists run-local `qr_events.jsonl`, `/api/map` exposes a report-only `qr_cargo_events` overlay, the dashboard renders a QR Cargo panel/markers, and optional QR promotions write only `map_authoring.json`. Full DimOS registry/MCP validation still requires the full checkout.
- Live authored-route following is implemented in the offline/MCP surface: `route_execution.json` records `follow_route` progress, `follow_route`/`stop_route`/`route_status` are exposed by `DogOpsSkillContainer`, dashboard endpoints and controls are present, and completed live/fake runs append NavEvent evidence into `state.json`, `report.json`, and `report.md`. Real Go2 multi-waypoint route following still requires a cleared route and supervised live movement before claiming autonomous hardware success.
- Local project-pack verification on 2026-05-27 for live authored-route following: focused executor/skills/dashboard tests passed (`71 passed`), full DogOps tests passed (`92 passed, 2 skipped`), ruff passed, simulation wrote `.dogops/runs/latest/report.md`, and `git diff --check` passed. The project pack still lacks a `dimos` console script.
- Full DimOS live setup on 2026-05-27 from `/Users/chris/Documents/Workspace/dimos`: after syncing branch files into the full checkout and fixing macOS multicast with `sudo route delete -net 224.0.0.0/4 2>/dev/null || true && sudo route add -net 224.0.0.0/4 -interface lo0`, the foreground `unitree-go2-dogops` runtime connected to the Go2 over WebRTC, `dimos status` showed run `20260527-211618-unitree-go2-dogops`, MCP listened on `127.0.0.1:9990`, and `dimos mcp list-tools` exposed `follow_route`, `stop_route`, and `route_status`.
- Live dashboard/MCP smoke on 2026-05-27: dashboard served on `http://127.0.0.1:18771/`, `/api/map` reported `live.status=receiving`, fresh odom, a non-null robot pose, and a 1536-cell costmap. A selected stationary route `TEST_STATIONARY` at the current odom pose passed both direct MCP `follow_route(... dry_run=true)` and dashboard `/api/map/routes/follow` dry-run. In this local setup, `--daemon` made `dimos status` work but left the MCP HTTP server unreachable; use foreground mode for MCP route testing until that DimOS launch issue is understood.
- Deep review fixes on 2026-05-27: route following now rejects missing selected routes instead of falling back to the first route, serializes route execution with a run-local lock, publishes authored waypoints in the persisted authoring frame, requires live target/path evidence before declaring odom reach, records no-progress failures, preserves repeated-run nav evidence, and makes stop behavior explicit. Dashboard `Stop Route` now attempts a local hard stop before the MCP stop call; MCP-only stop marks DogOps state stopped but reports missing nav-stop handler unless one is injected. Full DimOS navigation cancellation still needs runtime-specific integration/validation.
- Route-run history/action planning is tracked in `docs/dogops/ROUTE_RUN_HISTORY_IMPLEMENTATION_PLAN.md`. Implementation now creates global local SQLite route-run history across DogOps runs, mirrors per-run JSON/JSONL exports, creates one historical route run per `Run Route` execution, supports waypoint actions in authored routes, derives richer mission-YAML default actions, records QR/AprilTag/image evidence, persists unified timeline rows for route events/observations/incidents/work orders/verifications, and adds dashboard route-run history/current timeline endpoints and tables. Full live-Go2 validation and wiring a real camera stream/frame source into the configured image-capture hook remain hardware follow-ups.
- Live dashboard route-history test on 2026-05-28: Go2 odom was reachable on the dog Wi-Fi, but dashboard dry-run route follow returned `dimos_mcp_unavailable` because the DimOS MCP server timed out/disappeared. The dashboard now exposes a separate safe `Dry Run Route` control, keeps `Run Live Route` explicit, marks route history as Dry run vs Live, and surfaces MCP availability errors directly.
- Live half-meter route attempt on 2026-05-28 stopped before movement: the Go2 answered ping and TCP port 80, but Go2 WebRTC control ports refused connections. `unitree-go2` passed DimOS module health only with the macOS system-configurator bypass, while `unitree-go2-dogops` hung before registering status/MCP and logged connection failures against the Go2 WebRTC endpoint. No live route command was sent.
- Gather Heatmap run support is now implemented in the dashboard/MCP surface: `Gather Heatmap` snapshots the current DimOS costmap into `heatmaps/`, mirrors the attempt into global route-run history as `GATHER_HEATMAP`, and `/api/map` uses the latest gathered snapshot for the Heatmap layer toggle. Route waypoint action authoring now supports adding `capture_image`, `scan_qr`, `scan_tags`, `wait`, `inspect_asset`, `verify_work_order`, and `operator_prompt` actions from the dashboard; execution still uses the existing route action handlers and placeholder image evidence until real Go2 camera frames are wired.
- Route-run history can now project a selected historical route back onto the dashboard map. Route-run detail resolves the historical run directory, selected route snapshot, and that run's saved heatmap snapshot/evidence when present, so `Gather Heatmap` history rows can replay their saved costmap instead of showing only the latest heatmap.
- Saved route management is now present in the dashboard: all authored routes render in a table with selected state, waypoint/action counts, last run status, and select/rename/duplicate/delete controls. The selected route expands an actions subrow so planned waypoint actions are visible before execution.
- Real camera AprilTag scan path on 2026-05-28: `DogOpsObservationModule` and `DogOpsSkillContainer.scan_zone` can subscribe to DimOS `color_image`, decode AprilTag 36h11 frames with the optional vision extra, return `source=camera`, package IDs, frame age, and persisted observation evidence when a run state exists. The dashboard adds a low-risk `Scan Zone` MCP button that calls `scan_zone` without replacing main route/heatmap/QR cargo behavior. Direct Go2 WebRTC camera testing confirmed the frame path; full DimOS `color_image` topic subscription still needs one final runtime smoke before claiming autonomous route-action camera evidence.
- Gemini image comparison is implemented and live-Gemini validated in the local route-run path: optional `gemini_inspect_image` route actions analyze existing captured image evidence, prefer the latest previous image from the same waypoint as baseline, support a `yesterday` baseline preference, persist structured `gemini_vision_analysis` evidence, render dashboard action/evidence rows, and skip cleanly without `GEMINI_API_KEY` so the base demo remains offline-safe. On 2026-05-28, two factory PNG fixtures under `dimos/experimental/dogops/testdata/` produced a real Gemini analysis with `baseline_match=same_route_waypoint`. `capture_image` now snapshots the latest subscribed DogOps `color_image` frame as `source=go2_camera_live` when a live frame is present, while retaining configured-file and placeholder fallbacks for offline runs; full DimOS live route-action smoke with the real Go2 still needs to be run before claiming autonomous camera evidence in the final demo.

## Required Acceptance Checklist

- `uv run pytest -q dimos/experimental/dogops` passes.
- `uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest` produces a coherent report.
- Dashboard opens and shows report/state/nav metrics.
- `uv run dimos list | rg dogops` shows `unitree-go2-dogops`.
- `uv run dimos mcp list-tools` exposes `run_mission`, `go_to`, `follow_route`, `stop_route`, `route_status`, `gather_heatmap`, `scan_zone`, `read_gauge`, `check_clearance`, `detect_blocked_aisle`, `scan_receiving_manifest`, `verify_work_order`, and `nav_eval_report`, or an exact blocker plus direct fallback is documented.
- Base `unitree-go2` hardware smoke is attempted against the real robot.
- DogOps hardware/guided run is attempted, or a specific DimOS/robot blocker is documented.
- 90-second demo video shows the closed loop.
- README explains offline and Go2 paths.
- `STATUS.md` accurately states what is complete, guided, stretch, or blocked.

## Failure Memory Pointer

Repeated failures must be recorded in `docs/FAILURE_MEMORY.md` before changing strategy. Do not retry the same failing path more than twice without a new fact.
