# Issue 19 Live Route Following Implementation Plan

## Scope

This plan covers the next step after editable map route authoring: make an authored DogOps route executable on a live Unitree Go2 through DimOS navigation, with honest progress, timeout, retry, and fallback reporting.

It starts from `main` after PR #21 merged the editable map authoring work. The current editable route feature can persist, display, select, reorder, delete, and export routes, but it does not command the dog to follow a selected route.

Primary source of truth remains `SPEC.md`. The implementation must use existing DimOS navigation and Go2 primitives first, must not introduce a custom SLAM/nav stack, and must keep offline/demo mode deterministic.

## Current State

- `MapAuthoringState.routes` persists authored route waypoints in `.dogops/runs/<run_id>/map_authoring.json`.
- `/api/map` renders the selected authored route when one exists.
- `/api/map/export` writes selected route steps to `exports/mission_authoring.yaml`.
- Dashboard single-point Go To exists through `/api/robot/go_to`.
- `/api/robot/go_to` calls DogOps MCP skill `go_to(x, y)`.
- `DogOpsSkillContainer.go_to()` publishes a DimOS `PointStamped` to the `clicked_point` stream when available.
- `DogOpsLiveMapAdapter` already subscribes to DimOS live map topics:
  - `/odom`
  - `/path`
  - `/target`
  - `/goal_request`
  - `/clicked_point`
  - `/global_costmap`
  - `/navigation_costmap`
- Offline mission nav events are still simulation-derived from `mission_demo.yaml`, not live route execution.

## Goal

Add a live route executor that can take the currently selected authored route and safely command the real Go2 through each waypoint using DimOS navigation, while recording real navigation evidence back into the DogOps run.

The first version should prove:

```text
selected authored route
-> waypoint-by-waypoint live navigation command
-> live odom/path/target monitoring
-> success/failure/retry events
-> dashboard progress
-> nav_summary/report updated from real route events
```

## Non-Goals

- Do not make authored routes automatically replace `run_mission` yet.
- Do not claim no-go zones constrain live navigation until a planner/costmap constraint path is validated.
- Do not bypass DimOS with raw Go2 velocity control for route following except as an explicitly guided fallback.
- Do not require cloud LLM/API access.
- Do not hide guided interventions; record them as `guided=true`.

## DimOS Navigation Decision Point

Before implementing route execution, validate which DimOS primitive should receive route goals in the full DimOS checkout.

Research order:

1. Confirm whether the existing `/clicked_point` topic is the correct live navigation goal input for the Go2 stack.
2. If `/clicked_point` is only a UI/debug compatibility path, wire route execution to the real navigation API instead:
   - `MovementManager`
   - existing navigation skills in `dimos/agents/skills/navigation.py`
   - planner goal request topic
   - mission or waypoint object accepted by the Go2 navigation stack
3. Keep the DogOps public interface stable: `go_to` for one point, `follow_route` for selected route execution.

Implementation can start with the existing `clicked_point` path because DogOps already uses it for map click-to-go, but acceptance requires a full DimOS runtime check that the Go2 planner consumes the published goal and produces `/target`, `/path`, and `/odom` updates.

## Data Model Additions

Add live route execution state separately from authored route definitions.

Recommended persisted runtime file:

```text
.dogops/runs/<run_id>/route_execution.json
```

Recommended shape:

```text
RouteExecutionState
  run_id: str
  route_id: str
  state: "idle" | "running" | "paused" | "completed" | "failed" | "stopped"
  started_at: float | None
  completed_at: float | None
  active_waypoint_id: str | None
  active_index: int
  stop_requested: bool
  frame: str = "map"
  reach_radius_m: float
  waypoint_timeout_s: float
  max_retries: int
  events: list[RouteExecutionEvent]

RouteExecutionEvent
  id: str
  ts: float
  route_id: str
  waypoint_id: str
  target_id: str | None
  x: float
  y: float
  state: "queued" | "sent" | "accepted" | "reached" | "timeout" | "failed" | "skipped" | "stopped"
  elapsed_s: float
  error_m: float | None
  retries: int
  guided: bool
  note: str
```

Keep this distinct from `MapAuthoringState.routes`; editing a route should not mutate an in-flight execution log.

## Route Executor

Add a small execution layer, for example:

```text
dimos/experimental/dogops/route_executor.py
```

Responsibilities:

- Load `MapAuthoringState`.
- Resolve `selected_route_id` or an explicit `route_id`.
- Validate every waypoint has finite map-frame coordinates.
- Publish each waypoint as a navigation goal.
- Monitor live DimOS feedback until reached, failed, or timed out.
- Write `RouteExecutionState`.
- Append DogOps `NavEvent` rows for report/nav summary.
- Stop cleanly when requested.

First interface:

```python
class DogOpsRouteExecutor:
    def follow_route(route_id: str | None = None, *, dry_run: bool = False) -> RouteExecutionState: ...
    def stop_route() -> RouteExecutionState: ...
    def status() -> RouteExecutionState: ...
```

The executor should accept injectable goal publisher and live-state reader objects so tests can run without DimOS imports or hardware.

## MCP Skill Surface

Add MCP skills to `DogOpsSkillContainer`:

```text
follow_route(route_id: str | None = None, dry_run: bool = False)
stop_route()
route_status()
```

Behavior:

- `follow_route` should reject empty routes and missing selected route IDs.
- `dry_run=true` should validate and emit the intended waypoint sequence without publishing live goals.
- Live mode should require either:
  - a working DimOS navigation publisher, or
  - a configured handler injected by tests/full DimOS integration.
- Responses should include route ID, active waypoint, counts, and the transport used.

Do not overload `run_mission` yet. `run_mission` continues to use existing mission config until route execution is proven and the operator explicitly opts into authored route missions.

## Navigation Monitoring

Use DimOS live map data already surfaced by `DogOpsLiveMapAdapter`:

- `/odom` for current robot pose.
- `/target`, `/goal_request`, or `/clicked_point` to confirm the active goal.
- `/path` to confirm planner activity when available.
- `/navigation_costmap` or `/global_costmap` for future safety checks.

Reach criteria for v1:

```text
distance(current_odom_xy, waypoint_xy) <= reach_radius_m
```

Suggested defaults:

- `reach_radius_m = 0.35`
- `waypoint_timeout_s = 20.0` for local demo routes
- `max_retries = 1`
- stale topic threshold follows `LIVE_TOPIC_MAX_AGE_S`

Failure cases to record:

- no odom received;
- odom stale;
- goal publish failed;
- no progress toward waypoint;
- timeout;
- explicit stop;
- safety stop or guided fallback if exposed.

## Dashboard API

Add token-protected local endpoints in `DogOpsDashboardHandler`:

```text
POST /api/map/routes/follow
POST /api/map/routes/stop
GET  /api/map/routes/status
```

Request examples:

```json
{"route_id": "AUTHORED_ROUTE", "dry_run": false}
```

Response should include:

- `ok`
- route execution state
- current route snapshot
- current live map snapshot where useful
- precise error code when unavailable

These endpoints must use the same loopback, origin, and `X-DogOps-Control-Token` protections as robot control and map authoring writes.

## Dashboard UI

Add controls near the map route authoring tools:

- `Run Route`
- `Stop Route`
- route status pill
- active waypoint display
- last error/retry note

Do not auto-run a route when selecting it. Route selection remains an authoring/display operation. `Run Route` is the explicit live action.

For safety, show the live execution state separately from authored route editing state:

```text
Authored route: LOCALHOST_ROUTE
Execution: running waypoint 2/4
Transport: clicked_point or MovementManager
Odom age: 0.4s
Last error: none
```

## Store And Report Integration

When a live route executes, append real DogOps `NavEvent` records:

- `action="goto"`
- `target_id` from waypoint target ID or waypoint ID
- `success`
- `elapsed_s`
- `retries`
- `guided`
- `error_m`
- note describing transport and timeout/fallback

Then recompute and write:

- `state.json`
- `report.json`
- `report.md`

This lets existing navigation eval UI and report cards show real route results instead of only `mission_demo.yaml` simulation events.

## Safety Rules

- Require explicit operator click on `Run Route`.
- Require route dry-run validation before live run in tests.
- Hard stop must remain available and must interrupt route execution.
- Stop route should not rely on browser state; it must update server-side route execution state.
- Do not send raw velocity commands for route following unless the operator selects guided fallback.
- Keep route speed/area conservative for the office demo.
- For first hardware run, start with a two-waypoint route within line of sight.
- Always know/run `uv run dimos stop --force` before hardware testing.

## Implementation Order

1. **Full DimOS navigation preflight**
   - Run from the full DimOS checkout.
   - Confirm `unitree-go2-dogops` appears in `dimos list`.
   - Start DogOps runtime and confirm MCP exposes `go_to`.
   - Click a single map target and verify `/clicked_point`, `/target`, `/path`, and `/odom` behavior.
   - If `/clicked_point` is not consumed, identify and document the correct MovementManager/navigation primitive before coding route execution.

2. **Route execution model**
   - Add `route_executor.py`.
   - Add `RouteExecutionState`/event models or keep local Pydantic models near the executor.
   - Add JSON persistence helpers.
   - Unit-test selected route resolution, empty route rejection, finite coordinate validation, timeout, stop, and dry-run behavior.

3. **Goal transport abstraction**
   - Extract current `go_to` goal-publish behavior behind a reusable interface.
   - Keep existing `go_to` behavior unchanged.
   - Add a fake publisher for tests.
   - Add a full DimOS transport implementation for the validated primitive.

4. **Live feedback reader**
   - Reuse or extend `DogOpsLiveMapAdapter`.
   - Add a route-executor-friendly snapshot with odom age, target, path presence, and costmap presence.
   - Unit-test stale odom and reached/not-reached calculations.

5. **MCP skills**
   - Add `follow_route`, `stop_route`, and `route_status`.
   - Add tests alongside `test_skills.py`.
   - Ensure no cloud keys or hardware are needed for dry-run/fake publisher tests.

6. **Dashboard API**
   - Add `/api/map/routes/follow`, `/api/map/routes/stop`, and `/api/map/routes/status`.
   - Protect with the same token/origin/loopback checks as robot actions.
   - Add HTTP tests using fake executor dependencies.

7. **Dashboard UI**
   - Add `Run Route`, `Stop Route`, and status rendering.
   - Keep route editing and route execution state visually distinct.
   - Refresh route status on the existing live map polling interval.

8. **Report/nav integration**
   - Append live `NavEvent` rows.
   - Recompute nav summary after route completion or stop.
   - Verify `report.md` says live/guided/fallback truthfully.

9. **Hardware smoke**
   - Base `unitree-go2` smoke first.
   - DogOps single `go_to` smoke second.
   - Two-waypoint authored route third.
   - Record exact blocker if any DimOS/MCP/runtime layer fails.

## Tests

Focused tests:

```text
dimos/experimental/dogops/test_route_executor.py
dimos/experimental/dogops/test_skills.py
dimos/experimental/dogops/test_dashboard.py
dimos/experimental/dogops/test_nav_eval.py
```

Required coverage:

- selected route resolves from `map_authoring.json`;
- explicit `route_id` overrides selected route;
- empty/missing route is rejected;
- invalid waypoint coordinate is rejected;
- dry-run returns ordered waypoints without publishing;
- fake publisher receives goals in order;
- executor waits for odom reach before next waypoint;
- stale odom causes timeout/failure;
- stop request interrupts execution;
- `NavEvent` rows are written with elapsed time, retries, guided flag, and error distance;
- dashboard route follow endpoints require token/local origin;
- dashboard route status reflects running/completed/failed/stopped states;
- existing `go_to` tests still pass.

Verification commands:

```bash
uv run pytest -q dimos/experimental/dogops/test_route_executor.py
uv run pytest -q dimos/experimental/dogops/test_skills.py dimos/experimental/dogops/test_dashboard.py
uv run pytest -q dimos/experimental/dogops
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
```

Full DimOS checks:

```bash
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  uv run dimos list | rg 'unitree-go2$|unitree-go2-dogops'

NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  uv run dimos mcp list-tools | rg 'go_to|follow_route|stop_route|route_status'
```

Hardware smoke must be separate from offline acceptance and must document the robot IP, route size, stop command, and observed behavior.

## Acceptance Criteria

- Operator can author/select a route in the dashboard.
- Operator can run the selected route explicitly.
- The route executor sends one live navigation goal at a time.
- The executor waits for real odom reach or records timeout/failure before proceeding.
- Dashboard shows active waypoint and route execution state.
- Hard stop/stop route interrupts route execution.
- `state.json`, `report.json`, and `report.md` include real route navigation events.
- Offline tests pass without DimOS imports or hardware.
- Full DimOS checkout validates `go_to` and `follow_route` MCP visibility.
- Real Go2 smoke either succeeds on a conservative two-waypoint route or documents a precise blocker.

## Open Questions

- Does the live Go2 planner consume `/clicked_point` for navigation in the DogOps runtime, or should DogOps call `MovementManager`/navigation skills directly?
- Which frame should authored route execution use by default in the full runtime: `map`, `world`, or a DimOS-specific localization frame?
- What is the right reach radius for the Go2 in the office demo after odom drift and AprilTag relocalization?
- Is there a native DimOS route/waypoint object that should replace DogOps sequencing after the first version?
- Should no-go authoring block route execution preflight if a waypoint lies inside an authored no-go shape, even before live planner constraints are implemented?
