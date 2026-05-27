# Issue 19 Editable Map Implementation Plan

## Scope

This plan covers the Issue #19 section titled **"Currently hardcoded/demo-derived map pieces to make editable"**. It does not implement the separate camera/Rerun follow-ups, but it must preserve the existing split where DogOps semantic state and DimOS live overlays share one map projection.

Primary source of truth remains `SPEC.md`. The editable map must keep the base DogOps demo deterministic, offline-capable, and honest about live DimOS integration.

## Current State

- `examples/dogops/site_demo.yaml` owns demo zones, assets, packages, tag IDs, and pose hints.
- `examples/dogops/mission_demo.yaml` owns the static demo route through mission steps and nav simulation events.
- `dimos/experimental/dogops/map_snapshot.py` derives map objects from run `state.json`, `report.json`, and optional live DimOS overlay data.
- Assets and packages without direct poses are positioned by deterministic offsets from their zone.
- The dashboard exposes `/api/map` and `/api/map/svg`, but it has no editable map persistence contract.
- Live map data is best-effort through `DogOpsLiveMapAdapter` and should remain independent from authored semantic state.

## Success Criteria

- Dashboard has explicit edit modes for home, labels/zones, assets, packages, no-go areas, routes, incidents, and tag bindings.
- Map edits persist in the run directory and survive dashboard reload without modifying canonical demo YAML by accident.
- `/api/map` composes authored semantic state with live DimOS overlays without collapsing those concepts into one source.
- Offline/demo mode works with no DimOS topics, no robot, no cloud keys, and no Rerun.
- Existing robot control and map layer behavior remain intact.
- Tests cover map authoring persistence, API validation, SVG/snapshot composition, route/no-go fallback, and no-hardware behavior.

## Branch And Preflight

1. Start from `origin/main` after PR #13/#15 merge state is present locally.
2. If the active checkout has dirty PR carryover, use a clean task branch or worktree based on `origin/main` before implementation.
3. Run the required repo preflight:

```bash
git status -sb
git fetch --prune origin
git branch --show-current
gh auth status
```

4. Validate the existing baseline before edits:

```bash
uv run pytest -q dimos/experimental/dogops/test_dashboard.py
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  uv run dimos list | rg dogops
```

## Data Model

Add a small authoring layer instead of mutating `SiteConfig` directly on every click.

New persisted file:

```text
.dogops/runs/<run_id>/map_authoring.json
```

Recommended model shape:

```text
MapAuthoringState
  schema_version: int
  site_id: str
  frame: str = "world"
  updated_at: float
  home: EditableMapPoint | None
  entities: list[EditableMapEntity]
  no_go_shapes: list[EditableNoGoShape]
  routes: list[EditableRoute]
  incident_locations: list[EditableIncidentLocation]
  tag_bindings: list[EditableTagBinding]

EditableMapPoint
  x: float
  y: float
  theta_deg: float | None
  source: "site_config" | "dashboard_edit" | "observation" | "live_topic"

EditableMapEntity
  id: str
  kind: "zone" | "asset" | "package" | "checkpoint"
  label: str
  pose: EditableMapPoint
  tag_id: int | None
  zone_id: str | None
  source_id: str | None

EditableNoGoShape
  id: str
  label: str
  shape: "rectangle" | "polygon"
  points: list[EditableMapPoint]
  enabled: bool
  dimos_constraint_status: "not_supported" | "pending" | "published" | "failed"

EditableRoute
  id: str
  label: str
  waypoints: list[EditableRouteWaypoint]
  mission_id: str | None

EditableRouteWaypoint
  id: str
  label: str
  pose: EditableMapPoint
  target_id: str | None
  required: bool

EditableIncidentLocation
  incident_id: str
  entity_id: str | None
  pose: EditableMapPoint
  evidence_observation_ids: list[str]

EditableTagBinding
  tag_id: int
  entity_id: str
  label: str
  binding_kind: "zone" | "asset" | "package" | "checkpoint"
```

Keep the models in `dimos/experimental/dogops/models.py` unless they become large enough to justify `map_authoring.py`. Use Pydantic validation and stable JSON serialization.

## Persistence Rules

- Load order for map rendering:
  1. canonical run state and site config;
  2. `map_authoring.json` edits;
  3. live DimOS overlay if `mode=live`.
- Authored positions override demo-derived offsets only for the edited entity.
- Never overwrite `examples/dogops/site_demo.yaml` or `mission_demo.yaml` on normal dashboard edits.
- Add an explicit export action later:

```text
POST /api/map/export
```

This can write an exported YAML artifact under the run directory first, for example:

```text
.dogops/runs/<run_id>/exports/site_authoring.yaml
.dogops/runs/<run_id>/exports/mission_authoring.yaml
```

Only after that is stable should a separate workflow update `examples/dogops/*.yaml`.

## API Contract

Implement a narrow JSON API in `DogOpsDashboardHandler`:

```text
GET  /api/map/authoring
PUT  /api/map/authoring
POST /api/map/entities
PUT  /api/map/entities/{entity_id}
DELETE /api/map/entities/{entity_id}
POST /api/map/no_go_shapes
PUT  /api/map/no_go_shapes/{shape_id}
DELETE /api/map/no_go_shapes/{shape_id}
POST /api/map/routes
PUT  /api/map/routes/{route_id}
DELETE /api/map/routes/{route_id}
POST /api/map/incidents/{incident_id}/location
POST /api/map/tag_bindings
DELETE /api/map/tag_bindings/{tag_id}
POST /api/map/export
```

Validation requirements:

- Reject unknown entity kinds, empty labels, malformed coordinates, duplicate IDs, and duplicate tag bindings.
- Coordinates are stored in the map frame, not screen pixels.
- Keep request bodies small and deterministic; no browser-provided file paths.
- Return updated authoring state plus the refreshed `/api/map` snapshot where useful.

## Snapshot Composition

Refactor `build_map_snapshot` so map rendering is not tied to demo-only derivation.

Implementation steps:

1. Add `authoring: dict | None` to `build_map_snapshot`.
2. Convert site zones/assets/packages into semantic map entities.
3. Overlay authored entity poses and labels by ID.
4. Add authored-only labels/checkpoints that do not exist in the site config.
5. Add no-go polygons/rectangles to the snapshot separately from costmap cells.
6. Use authored route waypoints when a selected route exists; otherwise fall back to nav events.
7. Keep live `costmap`, `route`, `robot_pose`, and `target` as live overlays only in `mode=live`.

Do not remove the existing demo-derived fallback. It is still the offline acceptance path.

## Dashboard UI

Use the existing no-build static dashboard. Add a compact edit toolbar to the DogOps map panel with these modes:

- Select/move.
- Set Home.
- Add label/zone.
- Add asset.
- Add package.
- Draw no-go.
- Route waypoints.
- Attach incident.
- Bind tag.

Expected behavior:

- Click map in an edit mode creates or moves the active item.
- Drag updates a marker or shape vertex.
- Escape cancels the current draft.
- Delete removes the selected authored object after confirmation.
- Save writes `map_authoring.json`.
- Reset removes only authored edits, not canonical site config.
- Export produces run-local YAML artifacts.

Coordinate conversion must use the current SVG bounds so authored points line up with demo and live overlays. Keep dimensions stable so mode switches and labels do not resize the map.

## Feature Mapping

### Home/Base Location

- Add a dedicated `Set Home` mode.
- Store the result as `MapAuthoringState.home`.
- Compose it into the `HOME` zone pose during map snapshot generation.
- Do not silently change mission start behavior until route export is explicit.

### Semantic Labels And Zones

- Allow authored `zone` or `checkpoint` entities with labels and optional tag IDs.
- Existing demo zones become editable by ID.
- New labels appear in `/api/map` and SVG immediately after save.

### Assets

- Allow authored `asset` entities with `zone_id`, tag ID, pose, and label.
- Editing an existing asset overrides the offset-from-zone placement.
- Keep asset health/status from run state and report data.

### Packages

- Allow manual package marker placement.
- Add tag-driven placement from observations as a separate action: "use latest observation pose for this tag/entity".
- Keep package reconciliation state from mission/report logic.

### No-Go Zones

- Start with rectangles and polygons persisted in `map_authoring.json`.
- Render no-go shapes distinctly from generated costmap cells.
- Add a no-op DimOS publishing hook that reports `not_supported` until a concrete planner constraint path is validated.
- Research existing DimOS planner/costmap primitives before publishing anything that claims to constrain navigation.

### Static Demo Route

- Add route authoring with click-created waypoints, reorder, delete, and save.
- Persist routes in `map_authoring.json`.
- Export route to run-local `mission_authoring.yaml` before wiring it into canonical examples.
- `run_mission` should continue using existing mission config until an explicit route/mission selection path exists.

### Incidents And Work Orders

- Add `POST /api/map/incidents/{incident_id}/location`.
- Allow clicked evidence point to attach to an incident or work order.
- Keep incident lifecycle in the existing mission/store model.

### AprilTag/Checkpoint Labels

- Add tag binding create/delete.
- Validate tag ID uniqueness.
- When a tag observation has a pose, offer it as a placement source for the bound entity.
- Keep AprilTag family and marker length from site config.

## DimOS Integration Questions

Research in this order, using existing DimOS primitives first:

1. Is there an existing topic/message for clicked goals, route waypoints, or `Path` authoring?
2. Can no-go polygons be represented through an existing costmap/planner constraint input?
3. Does MovementManager accept named waypoint objects, or only pose/goal requests?
4. Should editable semantic labels become DogOps-only state, or should they publish to a generic DimOS map annotation topic?

Until those are answered, keep authored routes/no-go shapes as DogOps state and dashboard overlays. Do not imply they are live planner constraints.

## Test Plan

Add focused tests first:

```text
dimos/experimental/dogops/test_map_authoring.py
dimos/experimental/dogops/test_dashboard.py
```

Required coverage:

- Empty authoring state round-trips.
- Home edit overrides `HOME` pose in `/api/map`.
- Existing asset/package placement overrides demo-derived offset.
- New label/checkpoint appears in snapshot and SVG.
- No-go rectangle/polygon persists and renders.
- Route authoring persists waypoint order.
- Incident location attaches evidence without changing incident state.
- Duplicate tag binding is rejected.
- Live mode still overlays fake live costmap/robot/path without losing authored semantic objects.
- Dashboard works when no live DimOS imports are available.

Verification commands:

```bash
uv run pytest -q dimos/experimental/dogops/test_map_authoring.py dimos/experimental/dogops/test_dashboard.py
uv run pytest -q dimos/experimental/dogops
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765
```

Manual smoke:

```bash
curl -fsS http://127.0.0.1:8765/api/map | jq '.counts'
curl -fsS http://127.0.0.1:8765/api/map/authoring | jq .
```

For UI changes, take before/after screenshots when practical.

## Implementation Order

1. **Preflight baseline**
   - Verify merged dashboard behavior on clean `origin/main`.
   - Record any branch/worktree caveat before editing.

2. **Authoring models and persistence**
   - Add Pydantic models.
   - Add atomic JSON read/write helpers.
   - Add unit tests independent of dashboard HTTP.

3. **Map snapshot composition**
   - Teach `build_map_snapshot` to accept authoring state.
   - Keep existing demo-derived map output unchanged when no authoring file exists.
   - Add tests for each override type.

4. **Dashboard API**
   - Add authoring endpoints and validation.
   - Keep robot-control token/origin protections separate from map editing.
   - Add HTTP tests using the existing stdlib dashboard server.

5. **Dashboard editing UI**
   - Add edit toolbar, selection state, SVG coordinate conversion, save/reset/export actions.
   - Keep layer toggles and live/demo mode switching working.
   - Avoid adding a frontend build step or dependency.

6. **Route and export path**
   - Persist routes first.
   - Export run-local YAML artifacts.
   - Wire mission selection only after export format is stable.

7. **No-go DimOS hook**
   - Add an internal publishing interface with explicit unsupported status.
   - Implement live planner integration only after validating the DimOS primitive.

8. **Docs and status**
   - Update `docs/dogops/README.md` or runbook with the authoring workflow.
   - Update `STATUS.md` only when implementation state changes.

## Risks And Fallbacks

- **Dirty branch state:** use a clean worktree based on `origin/main`; do not mix PR carryover with Issue #19 implementation.
- **Planner constraints unknown:** persist and render no-go areas as DogOps overlays until a real DimOS constraint path is proven.
- **SVG click math drift:** test coordinate conversion directly and use stable map bounds.
- **Canonical YAML churn:** export to run-local YAML first; do not auto-edit examples.
- **Live topic absence:** keep `/api/map?mode=live` returning a clear waiting/error status while authored semantic layers still render.

## Definition Of Done

- `map_authoring.json` exists and is stable after editing and reload.
- The dashboard can edit every Issue #19 hardcoded/demo-derived map category.
- Existing dashboard tests plus new authoring tests pass.
- Offline demo and `dimos list | rg dogops` still work or a precise blocker is documented.
- The final diff is scoped to DogOps map authoring code, tests, and docs.
