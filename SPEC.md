# SPEC.md

## 0. Canonical product direction

**Product name:** DogOps — DimOS SiteOps Agent

**Goal:** Build a product-grade Unitree Go2 Air application on DimOS that combines the hackathon's suggested **Agents** and **Autonomy & Navigation** ideas into one finished workflow.

**Core winning loop:**

```text
site policy + receiving manifest
-> autonomous route through a staged facility
-> AprilTag/package/asset inspection
-> manifest reconciliation
-> physical hazard/work-order creation
-> human remediation request
-> robot revisits the same location
-> verifies closure
-> produces dashboard + report + navigation/relocalization metrics
```

**Official-track alignment:**

| DimOS team suggestion | DogOps implementation |
|---|---|
| warehouse inspection | inspect rack row, cooling clearance, aisle state, restricted/no-go zone, optional thermometer reading |
| shipping & receiving agent | scan package AprilTags, reconcile manifest, flag wrong-zone/missing/damaged/blocking packages |
| security patrol | not the core; incident patrol is framed as facility operations and audit, not person surveillance |
| LLM/VLM-driven autonomy | optional natural-language mission/narration; base workflow is deterministic and MCP-callable without API keys |
| plan/execute/fail/recover | mission engine has explicit recovery, guided fallback, retries, and status reporting |
| SLAM/nav/exploration | use existing DimOS Go2 mapping/nav stack; add eval metrics for the product route |
| navigation eval tooling | report waypoint success, retries, elapsed time, guided interventions, tag reacquisition, route coverage |
| relocalization benchmarks | record AprilTag reacquisition metrics and pose deltas across repeated runs |
| ArUco self-charging | stretch: `DOCK_1` alignment readiness using AprilTag pose; do not claim charging without contacts |
| autonomous elevator entry | stretch: `PORTAL_1` / fake elevator portal with door-open gate and threshold-entry metric |

**Robot/runtime constraints:**

- Robot: Unitree Go2 Air is available and should be used for final validation.
- Host: offboard host with the full DimOS checkout is the primary build and runtime target.
- Ubuntu/UTM VM: optional for offline development only; do not make it required for final validation.
- Demo space: indoor/office, about 10 m × 10 m, props can be arranged.
- Internet: somewhat reliable.
- API keys: none required. Gemini/OpenAI can be optional only.
- Demo: both 90-second video and live demo.
- Props available: paper boxes, PVC barrier tape, AprilTag 36h11 prints, quick clamps, small traffic cones, sticky A4 paper, pens, power bank, thermometer.
- First physical demo should keep object classes intentionally narrow: about five traffic cones, three boxes, and one readable sign/thermometer station. Add more object categories only after the map/route/POI/report loop is stable.

**Build rule:** The project must be useful and demoable after each major part. Do not create a fragile all-or-nothing build.

---

## 1. Product narrative

DogOps is a **physical SiteOps agent** for facilities where software alerts do not see the physical world: warehouses, data-center rows, construction offices, industrial floors, maker spaces.

The demo arena is a mini facility:

```text
HOME / NOC
  -> INBOUND_DOCK
  -> RACK_ROW_A / COOLING_1
  -> AISLE_1 / NO_GO_1
  -> QA_HOLD
  -> optional DOCK_1
  -> optional PORTAL_1
```

A shipment has arrived. One package is in the wrong zone and physically blocks cooling clearance. The robot must detect this as both a logistics problem and a facility incident.

**The one-sentence demo:**

> DogOps receives a manifest, scans incoming packages, detects a misplaced package blocking cooling, opens a P1 work order, watches a human fix it, revisits the exact asset, verifies closure, and reports both SiteOps and navigation metrics.

**Do not call this “patrol” in the main pitch.** Call it “inspection,” “work-order closure,” “facility operations,” “SiteOps,” or “physical SRE.”

### Primary end-user stories

DogOps is built for local facility operators who need physical-world status without turning every asset into an internet-connected device:

- As a factory safety owner, I want the dog to visit important non-networked machines and report their visible/manual readings, so I can see overheating, warning states, or other machine errors early enough to react.
- As a warehouse operations owner, I want the dog to compare the floor against the last inspection run, so I can see new obstructions, misplaced packages, blocked assets, or other orderliness issues that need a human fix.
- As a local operator, I want route setup, live map context, manual safety controls, readings, photos, and “what changed” in one dashboard, so I can run the inspection without understanding DimOS internals.

The dashboard should therefore prioritize current robot state, live map context, readings that need attention, floor changes since the last run, and the next human action. Raw navigation/debug detail belongs behind secondary views.

---

## 2. 90-second demo target

The video/live demo must show this minimum sequence:

| Time | Scene | What must be visible |
|---:|---|---|
| 0-8s | Product intro | Dashboard title: DogOps SiteOps Agent; physical arena visible |
| 8-15s | Mission start | Operator clicks/runs `Run mission: receiving_sre_demo` |
| 15-30s | Inbound scan | Robot arrives near boxes, scans package tags, manifest updates |
| 30-45s | Hazard detection | Robot detects `PKG-104` in wrong zone and blocking `COOLING_1` |
| 45-55s | Work order | Dashboard opens `INC-001` / `WO-001`, severity P1, evidence image/tag IDs |
| 55-65s | Human remediation | Human moves box to `QA_HOLD`; dashboard marks `READY_TO_VERIFY` |
| 65-78s | Verification | Robot revisits `COOLING_1`, sees clearance restored, closes work order |
| 78-90s | Report | Dashboard shows: packages reconciled, one resolved incident, missing/open exceptions, nav metrics |

The final screen should say something close to:

```text
DOGOPS RUN REPORT
Mission: receiving_sre_demo
Packages scanned: 4
Manifest exceptions: 2
Incidents opened: 2
Work orders verified closed: 1
Open issue: PKG-103 missing
Nav: 5/5 waypoints reached, 1 tag-search recovery, 0 safety stops
What changed: PKG-104 moved from COOLING_1 to QA_HOLD; INC-001 resolved.
```

---

## 3. Non-goals and honesty rules

These are forbidden as core behavior:

- Do not make generic security/person surveillance the main demo.
- Do not require cloud LLM/API access for success.
- Do not claim real autonomous self-charging without electrical charging hardware.
- Do not claim true autonomous elevator entry unless a safe real elevator test happened.
- Do not claim calibrated temperature/thermal inspection from a household thermometer. It can be an optional manual reading input, not autonomous thermal sensing.
- Do not hide teleop/guided interventions. Record them as metrics.
- Do not implement a new monocular SLAM system. Use DimOS navigation/mapping stack; add product eval tooling around it.

The base demo may use deterministic logic with optional LLM narration. Judges care that the robot closes a physical loop, not that every decision is opaque.

---

## 4. Existing DimOS codebase anchors

Use existing repo primitives first. Do not invent new framework infrastructure unless a real integration gap requires it.

| Need | Existing path / command |
|---|---|
| Go2 smart stack | `dimos/robot/unitree/go2/blueprints/smart/unitree_go2.py` |
| Go2 base connection | `dimos/robot/unitree/go2/connection.py` |
| Go2 agentic stack | `dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_agentic.py` |
| Existing Go2 marker blueprint | `unitree_go2_markers` in `dimos/robot/unitree/go2/blueprints/smart/unitree_go2.py` |
| AprilTag/ArUco detector | `dimos/perception/fiducial/marker_tf_module.py` |
| AprilTag PDF CLI | `dimos apriltag --ids ... --size-mm ... --family tag36h11` |
| Navigation stack | `MovementManager`, `ReplanningAStarPlanner`, `WavefrontFrontierExplorer`, `PatrollingModule` |
| Navigation skills | `dimos/agents/skills/navigation.py` |
| Go2 motion/sport skills | `dimos/robot/unitree/unitree_skill_container.py` |
| MCP server | `dimos/agents/mcp/mcp_server.py` |
| MCP CLI | `dimos mcp list-tools`, `dimos mcp call ...` |
| Optional MCP client/LLM | `McpClient` only in optional agentic build |
| Relocalization | `dimos/mapping/relocalization/module.py`, `unitree_go2_relocalization` |
| Memory recorder | `dimos/memory2/module.py`, `unitree_go2_memory` |
| Rerun / visualization | `dimos/visualization/vis_module.py`, `dimos/visualization/rerun/*` |
| Blueprint registry | `dimos/robot/test_all_blueprints_generation.py`, `dimos/robot/all_blueprints.py` |
| CLI lifecycle | `dimos run`, `dimos status`, `dimos log`, `dimos stop`, `dimos list` |

Important implementation choices from the repo:

- `MarkerTfModule` defaults to `DICT_APRILTAG_36h11` and needs the physical `marker_length_m`.
- The CLI command `dimos apriltag` can generate tag36h11 PDFs.
- `McpServer` exposes methods decorated with `@skill` from modules.
- `unitree_go2_agentic` includes `McpClient`, which may require LLM credentials. The base DogOps blueprint must not include `McpClient`.
- Blueprint registry is autogenerated. After adding blueprint variables, run the registry generation test. It may fail once because it updates `all_blueprints.py`; inspect diff and rerun.

### Implementation guardrails

Offline product checks, dashboard checks, direct skill tests, optional AprilTag detection, and dry-run scripts are useful, but they are not final acceptance. Final acceptance requires full DimOS integration: `unitree-go2-dogops` must appear in the full checkout registry or the exact blocker must be documented.

For the next build:

- Build directly in `$DIMOS_ROOT` or another full DimOS checkout.
- Add the DogOps blueprint and run registry checks early, before demo polish.
- DogOps modules used as DimOS workers should tolerate framework-injected kwargs such as `g=`.
- The Go2 blueprint file should expose a real module-level `unitree_go2_dogops` blueprint in a full DimOS checkout; use metadata fallback only for isolated import tests.
- Use `NO_PROXY=127.0.0.1,localhost` and `no_proxy=127.0.0.1,localhost` around localhost dashboard/MCP checks.
- Keep direct CLI/skill fallback, but do not let it replace `dimos list | rg dogops` unless a blocker is explicitly documented.
- Attempt base `unitree-go2` hardware smoke before DogOps-specific hardware runs.
- Use real-Go2 evidence for the final video whenever the robot/network path is available.
- Keep guided mode honest: record `guided=true`, retries, safety stops, and fallback level in the report.

### Upstream DimOS Opportunities

`docs/dogops/UPSTREAM_OPPORTUNITIES.md` tracks upstream DimOS PRs/issues that may be useful research or contribution targets. These are optional accelerators only: the base DogOps demo must not depend on unmerged upstream PRs, draft branches, or unresolved issues.

---

## 5. Repository layout to add

Add DogOps under one namespace:

```text
dimos/experimental/dogops/
  __init__.py
  constants.py
  models.py
  config_loader.py
  tag_registry.py
  detector.py
  store.py
  mission_engine.py
  live_map.py
  route_executor.py
  observation_module.py
  skills.py
  nav_eval.py
  report.py
  dashboard.py
  dashboard_static.py
  cli.py
  blueprints.py
  test_config_loader.py
  test_detector.py
  test_store.py
  test_mission_engine.py
  test_nav_eval.py
  test_report.py
  test_cli_smoke.py
```

Add a Go2-specific blueprint file if registry/import discovery does not pick up `blueprints.py` reliably:

```text
dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py
```

Add demo docs/configs outside the package:

```text
docs/dogops/
  README.md
  DEMO.md
  ARENA.md
  TAGS.md
  TROUBLESHOOTING.md
  FAILURE_MEMORY.md
  RUNBOOK_MAC_GO2.md
  RUNBOOK_UBUNTU_VM.md
  UPSTREAM_WORKFLOW.md

examples/dogops/
  site_demo.yaml
  manifest_demo.yaml
  mission_demo.yaml
  policy_demo.yaml
```

If Codex is told to copy this planning pack into the repo root, keep these root files:

```text
AGENTS.md
SPEC.md
STATUS.md
```

Existing upstream has its own `AGENTS.md`. For the public hackathon repo, replace or merge it with the short `AGENTS.md` in this pack. If contributing directly upstream, preserve upstream-critical instructions and add the DogOps rules in a concise section.

---

## 6. Product data model

Use Pydantic models. Keep serialization stable because dashboard/report/tests depend on it.

### 6.1 Enums

```text
EntityKind = zone | asset | package | dock | portal
ZoneKind = home | inbound_dock | qa_hold | rack_row | aisle | no_go | dock | portal
AssetKind = cooling_clearance | rack_status | aisle_clearance | safety_station | temperature_station
PackageState = expected | found_ok | wrong_zone | missing | damaged | blocking_asset | unknown
IncidentType = blocked_cooling | wrong_zone | missing_package | damaged_package | blocked_aisle | no_go_breach | high_temperature | unknown
Severity = P1 | P2 | P3 | INFO
IncidentState = open | acked | ready_to_verify | resolved | unresolved | false_positive
WorkOrderState = open | assigned | ready_to_verify | verified_closed | blocked | cancelled
MissionState = init | running | waiting_for_human | verifying | done | failed | stopped
NavAction = goto | scan | search_tag | rotate | step_back | guided | dock_align | portal_entry
```

### 6.2 Core models

Minimum fields:

```text
Pose2D:
  x: float | None
  y: float | None
  theta_deg: float | None
  frame: str = "world"
  source: str = "unknown"

SiteEntity:
  id: str
  kind: EntityKind
  tag_id: int | None
  display_name: str
  zone_id: str | None
  expected_state: dict
  severity_if_failed: Severity = P3
  notes: str = ""

Zone(SiteEntity):
  zone_kind: ZoneKind
  pose_hint: Pose2D | None
  radius_m: float = 0.8
  no_go: bool = False

Asset(SiteEntity):
  asset_kind: AssetKind
  expected_clear: bool | None
  expected_status: str | None
  blocking_package_ids: list[str]

Package(SiteEntity):
  expected_zone_id: str
  expected_condition: str = "ok"

SiteConfig:
  site_id: str
  tag_family: str = "tag36h11"
  marker_length_m: float
  zones: list[Zone]
  assets: list[Asset]
  packages: list[Package]

ManifestItem:
  package_id: str
  expected_zone_id: str
  expected_condition: str = "ok"

Manifest:
  manifest_id: str
  items: list[ManifestItem]

MissionStep:
  id: str
  action: str
  target_id: str
  timeout_s: float = 30.0
  required: bool = True

MissionConfig:
  mission_id: str
  display_name: str
  steps: list[MissionStep]
  verify_after_human: bool = True

Observation:
  id: str
  ts: float
  run_id: str
  entity_id: str | None
  tag_id: int | None
  zone_id: str | None
  pose: Pose2D | None
  image_path: str | None
  facts: dict[str, bool | str | int | float]
  confidence: float
  source: str

Incident:
  id: str
  run_id: str
  ts_open: float
  ts_closed: float | None
  severity: Severity
  type: IncidentType
  entity_id: str
  related_package_id: str | None
  state: IncidentState
  title: str
  evidence_observation_ids: list[str]
  recommended_action: str

WorkOrder:
  id: str
  incident_id: str
  requested_action: str
  assignee: str = "human_operator"
  state: WorkOrderState
  verification_observation_ids: list[str]

NavEvent:
  id: str
  run_id: str
  ts: float
  action: NavAction
  target_id: str | None
  success: bool
  elapsed_s: float
  retries: int
  guided: bool
  error_m: float | None
  note: str

MissionRun:
  id: str
  mission_id: str
  started_at: float
  ended_at: float | None
  state: MissionState
  current_step_id: str | None
  summary: str
```

---

## 7. Demo entities and tags

Use AprilTag 36h11. Print large tags. For the robot camera, vertical tags are safer than floor tags.

Recommended printed tag size:

- Minimum: 100 mm black border edge.
- Better: 140-180 mm for zone/asset tags.
- Mount at Go2 forward camera height if possible. Unknown camera visibility is expected; prepare adjustable mounts with boxes/clamps.

### 7.1 Tags

| Entity | Tag ID | Kind | Purpose |
|---|---:|---|---|
| `HOME` | 10 | zone | start/end; localize first |
| `INBOUND_DOCK` | 20 | zone | package scan area |
| `QA_HOLD` | 30 | zone | corrected destination for problem package |
| `RACK_ROW_A` | 40 | zone | data-center / facility row |
| `COOLING_1` | 41 | asset | blocked-cooling incident |
| `AISLE_1` | 42 | asset | aisle clearance / barrier tape incident |
| `TEMP_1` | 43 | asset | optional thermometer reading station |
| `NO_GO_1` | 50 | zone | restricted work area |
| `DOCK_1` | 60 | dock | self-charging/dock-alignment readiness stretch |
| `PORTAL_1` | 70 | portal | elevator/portal-entry stretch |
| `PKG-101` | 101 | package | expected OK in inbound |
| `PKG-102` | 102 | package | expected OK in inbound |
| `PKG-103` | 103 | package | intentionally missing in final run |
| `PKG-104` | 104 | package | wrong zone; blocks `COOLING_1` |

### 7.2 Props

| Prop | Use |
|---|---|
| paper boxes | packages, racks, blocked cooling obstacle |
| barrier tape | no-go zone, aisle boundary, hazard tape |
| cones | work zone, blocked aisle, route visual anchors |
| quick clamps | vertical tag/sign mounts |
| sticky A4 | printed labels, fake cooling vent, fake rack status, manual thermometer display |
| thermometer | optional `TEMP_1` manual input station; do not claim autonomous thermal sensing unless a camera actually reads it |
| power bank | laptop/phone/camera support |

---

## 8. Perception strategy

### 8.1 MVP perception

MVP perception is deterministic. It must not depend on VLMs.

Use three evidence types:

1. **AprilTag IDs** for entity identity.
2. **Known site layout** for zone/entity relationships.
3. **Operator-specified or simulated facts** for offline mode and fallback mode.

The MVP can infer `PKG-104 blocks COOLING_1` if both are observed near the cooling station during the inspection step and the site policy marks that package as blocking when located in `RACK_ROW_A`/`COOLING_1`.

### 8.2 Real image detector

Implement `detector.py` with a direct OpenCV ArUco path using helpers/patterns from `dimos/perception/fiducial/marker_tf_module.py`:

- Use `cv2.aruco.ArucoDetector` with `DICT_APRILTAG_36h11`.
- Convert `dimos.msgs.sensor_msgs.Image` to grayscale using existing image APIs.
- Return tag IDs and rough image centers.
- Do not require full pose estimation for MVP.
- If `CameraInfo` is available, include pose estimate as stretch.
- Store image snapshots if available.

Preferred detector outputs:

```text
DetectedTag:
  tag_id: int
  center_px: tuple[float, float]
  area_px: float
  confidence: float
  frame_id: str | None
```

### 8.3 Zone assignment

MVP zone assignment can be mission-step based:

- During `SCAN_INBOUND`, observed package tags are assigned to `INBOUND_DOCK` unless a known asset tag overrides.
- During `INSPECT_RACK_ROW`, observed package tags near `COOLING_1` are assigned to `RACK_ROW_A`/`COOLING_1`.
- During `SCAN_QA_HOLD`, observed package tags are assigned to `QA_HOLD`.

Stretch zone assignment can use TF pose/marker distance.

### 8.4 Optional VLM/LLM

Optional VLM/LLM is allowed only for:

- generating human-readable report prose;
- explaining an observation already determined by deterministic facts;
- classifying a screenshot as a non-blocking bonus;
- translating a mission prompt into a deterministic mission ID.

Base tests and demo must pass with no keys and no network.

---

## 9. Mission engine

The mission engine is deterministic, resumable, and safe.

### 9.1 Required mission stages

```text
INIT
LOAD_SITE
START_RUN
LOCALIZE_HOME
SCAN_INBOUND
RECONCILE_MANIFEST
INSPECT_RACK_ROW
OPEN_WORK_ORDERS
WAIT_FOR_HUMAN_FIX
VERIFY_FIX
SCAN_QA_HOLD
REPORT
DONE
```

### 9.2 Core state transitions

```text
INIT -> LOAD_SITE -> START_RUN -> LOCALIZE_HOME
LOCALIZE_HOME -> SCAN_INBOUND
SCAN_INBOUND -> RECONCILE_MANIFEST
RECONCILE_MANIFEST -> INSPECT_RACK_ROW
INSPECT_RACK_ROW -> OPEN_WORK_ORDERS
OPEN_WORK_ORDERS -> WAIT_FOR_HUMAN_FIX if any verifiable work order exists
WAIT_FOR_HUMAN_FIX -> VERIFY_FIX after mark_ready_to_verify
VERIFY_FIX -> SCAN_QA_HOLD
SCAN_QA_HOLD -> REPORT -> DONE
```

### 9.3 Work-order lifecycle

```text
open -> assigned -> ready_to_verify -> verified_closed
open -> blocked
open -> cancelled
```

`verify_work_order` must create a verification observation. It may close only if the incident-specific closing condition is met.

Examples:

| Incident | Closing condition |
|---|---|
| `blocked_cooling` | `PKG-104` no longer observed at `COOLING_1` and/or `COOLING_1.clearance_clear=true` |
| `wrong_zone` | package observed in expected zone or configured correction zone |
| `missing_package` | package found later, otherwise stays open |
| `blocked_aisle` | `AISLE_1.clearance_clear=true` |
| `no_go_breach` | robot did not enter no-go; breach marked false or resolved |

### 9.4 Recovery policy

Recovery must be explicit and reported.

| Failure | Recovery 1 | Recovery 2 | Exit path |
|---|---|---|---|
| tag not visible | rotate/search in place | step back/retry | guided mode; continue; record `guided=true` |
| waypoint not reached | retry once | shorter local move | skip optional target; continue required target in guided mode |
| detector ambiguous | rescan | use mission-step fallback | create `UNKNOWN` observation and continue |
| dashboard fails | restart dashboard | write static report | continue mission without live UI |
| MCP fails | call CLI directly | run pure offline/hardware runner | continue without LLM/agent, but document MCP blocker |
| optional LLM unavailable | deterministic template | omit narration | base demo unaffected |
| real robot path blocked | base `unitree-go2` smoke/logs | guided or offline fallback with robot clip | submit working code + exact hardware blocker |

**Important:** After two failed code fixes on the same bug, stop and write a short entry in `docs/FAILURE_MEMORY.md`, then choose a fallback.

---

## 10. Navigation and eval tooling

### 10.1 Navigation principle

Use existing DimOS navigation when possible. Do not build a new planner.

The product value is not a new SLAM algorithm. The product value is that every SiteOps run produces a **navigation/relocalization audit**:

- waypoints attempted;
- waypoints reached;
- elapsed time;
- retries;
- guided interventions;
- tag reacquisition success;
- optional pose error near tags;
- route coverage;
- failure reason.

### 10.2 NavEval metrics

Implement `nav_eval.py` with:

```text
record_nav_event(...)
summarize_nav_events(run_id) -> NavSummary
compare_runs(run_a, run_b) -> NavComparison
record_tag_reacquisition(tag_id, expected_zone_id, success, elapsed_s, pose_error_m=None)
record_guided_intervention(reason, target_id)
```

Minimum `NavSummary` fields:

```text
run_id
waypoints_total
waypoints_reached
waypoints_failed
success_rate
retries_total
guided_interventions
tag_reacquisition_attempts
tag_reacquisition_successes
mean_elapsed_s
worst_target_id
notes
```

### 10.3 Dashboard eval panel

Show a compact panel:

```text
Navigation Eval
- Waypoints: 5/5 reached
- Tag reacquisition: 4/5 success
- Recovery actions: 1 search_tag, 0 safety_stop
- Guided interventions: 0
- Median target time: 8.2s
```

If live nav is flaky, this panel still makes guided fallback honest and product-grade.

### 10.4 Dock alignment stretch

Add `dock_align(dock_id)` as a stretch skill.

Minimum behavior:

- search for `DOCK_1` tag;
- estimate alignment state from tag center and area if no full pose is available;
- output final status:

```text
Dock alignment readiness: PASS
Tag: DOCK_1
Lateral error estimate: 0.08m
Yaw estimate: unavailable
Charging contacts: not present; readiness only
```

Do not claim actual charging.

### 10.5 Portal/elevator stretch

Add `portal_entry(portal_id)` as a stretch skill.

Minimum behavior:

- detect `PORTAL_1` tag and barrier/door-open flag from config/dashboard;
- if `door_open=false`, do not enter;
- if `door_open=true`, move through a taped threshold or record a simulated portal entry;
- report success/failure and whether it was guided.

Do not use a real elevator unless event staff explicitly permit it.

---

## 11. Skills and MCP surface

Implement `DogOpsSkillContainer` as a DimOS `Module` with `@skill` methods. It must run without `McpClient` or API keys.

### 11.1 Required skills

```text
load_site_config(path: str = "examples/dogops/site_demo.yaml") -> str
load_manifest(path: str = "examples/dogops/manifest_demo.yaml") -> str
load_mission(path: str = "examples/dogops/mission_demo.yaml") -> str
run_mission(mission_id: str = "receiving_sre_demo") -> str
scan_zone(zone_id: str) -> str
inspect_asset(asset_id: str) -> str
reconcile_manifest() -> str
open_work_order(entity_id: str, issue_type: str) -> str
mark_ready_to_verify(work_order_id: str) -> str
verify_work_order(work_order_id: str) -> str
what_changed(since_run_id: str | None = None) -> str
nav_eval_report(run_id: str | None = None) -> str
map_open_space() -> str
set_route_plan(plan_json: str) -> str
add_route_waypoint(target_id: str) -> str
add_point_of_interest(target_id: str, reading_keys_json: str = "[]") -> str
run_route_plan() -> str
poi_report() -> str
dock_align(dock_id: str = "DOCK_1") -> str
portal_entry(portal_id: str = "PORTAL_1") -> str
stop_mission() -> str
```

### 11.2 Return format

Skills may return strings, but prefer compact JSON strings for machine readability:

```json
{
  "ok": true,
  "skill": "verify_work_order",
  "work_order_id": "WO-001",
  "state": "verified_closed",
  "summary": "COOLING_1 is clear. INC-001 resolved."
}
```

### 11.3 CLI commands

Add a DogOps CLI module that can run without DimOS workers:

```bash
uv run python -m dimos.experimental.dogops.cli validate \
  --site examples/dogops/site_demo.yaml \
  --manifest examples/dogops/manifest_demo.yaml \
  --mission examples/dogops/mission_demo.yaml

uv run python -m dimos.experimental.dogops.cli start \
  --site examples/dogops/site_demo.yaml \
  --manifest examples/dogops/manifest_demo.yaml \
  --mission examples/dogops/mission_demo.yaml \
  --out .dogops/runs/latest

uv run python -m dimos.experimental.dogops.cli simulate \
  --site examples/dogops/site_demo.yaml \
  --manifest examples/dogops/manifest_demo.yaml \
  --mission examples/dogops/mission_demo.yaml \
  --out .dogops/runs/latest

uv run python -m dimos.experimental.dogops.cli report \
  --run .dogops/runs/latest \
  --out .dogops/runs/latest/report.md

uv run python -m dimos.experimental.dogops.cli map \
  --run .dogops/runs/latest

uv run python -m dimos.experimental.dogops.cli plan \
  --run .dogops/runs/latest \
  --add-waypoint TEMP_1 \
  --add-poi TEMP_1

uv run python -m dimos.experimental.dogops.cli run-plan \
  --run .dogops/runs/latest

uv run python -m dimos.experimental.dogops.cli serve \
  --run .dogops/runs/latest \
  --host 127.0.0.1 \
  --port 8765
```

These commands are the fastest feedback loop for Codex.

---

## 12. Blueprint design

### 12.1 Base no-key blueprint

Add `unitree_go2_dogops` that includes robot stack + marker support + DogOps skills + MCP server + dashboard. It must **not** include `McpClient`.

Preferred composition:

```python
from dimos.agents.mcp.mcp_server import McpServer
from dimos.core.coordination.blueprints import autoconnect
from dimos.core.global_config import global_config
from dimos.robot.unitree.go2.blueprints.smart.unitree_go2 import unitree_go2_markers
from dimos.visualization.vis_module import vis_module
from dimos.experimental.dogops.observation_module import DogOpsObservationModule
from dimos.experimental.dogops.skills import DogOpsSkillContainer
from dimos.experimental.dogops.dashboard import DogOpsDashboardModule
from dimos.experimental.dogops.nav_eval import DogOpsNavEvalModule

unitree_go2_dogops = autoconnect(
    unitree_go2_markers,
    DogOpsObservationModule.blueprint(),
    DogOpsSkillContainer.blueprint(),
    DogOpsDashboardModule.blueprint(),
    DogOpsNavEvalModule.blueprint(),
    McpServer.blueprint(),
    vis_module(viewer_backend=global_config.viewer),
).global_config(n_workers=12, robot_model="unitree_go2")
```

If `vis_module` complicates tests or dependencies, omit it from the first runnable blueprint and add it in a stretch blueprint.

### 12.2 Optional agentic blueprint

Add a second optional blueprint only after base works:

```python
from dimos.agents.mcp.mcp_client import McpClient

unitree_go2_dogops_agentic = autoconnect(
    unitree_go2_dogops,
    McpClient.blueprint(),
)
```

This can require keys or local models. The base cannot.

### 12.3 Blueprint registry

After adding blueprint variables, run:

```bash
uv run pytest dimos/robot/test_all_blueprints_generation.py
```

Expected behavior:

- First run may update `dimos/robot/all_blueprints.py` and fail because the file has changed.
- Inspect the diff.
- Re-run the command. It should pass if the registry is current.

Then verify:

```bash
uv run dimos list | rg dogops
```

---

## 13. Dashboard and report

### 13.1 Minimal dashboard

Implement a local dashboard that works without a build step. Use FastAPI if available from `dimos[web]`; otherwise fall back to a stdlib HTTP server with generated static HTML.

Minimum routes:

```text
GET /                  -> HTML dashboard
GET /api/state         -> current run state JSON
GET /api/report        -> report JSON
GET /api/nav           -> nav eval JSON
GET /api/map           -> local map JSON
GET /api/route         -> route plan JSON
GET /api/poi           -> point-of-interest captures/readings JSON
POST /api/map/explore  -> create/refresh simulated open-space map
POST /api/route/waypoints -> add route waypoint by known target ID
POST /api/route/pois   -> add point of interest by known target ID
POST /api/route/inspection_points -> add one operator inspection point as waypoint + POI
POST /api/route/inspection_points/clear -> clear operator inspection points
POST /api/route/run    -> simulate route execution and POI capture analysis
POST /api/work_orders/{id}/ready_to_verify -> mark ready
POST /api/operator/event -> record manual/guided event
```

Map payloads must reuse the existing DimOS Go2 map/navigation stack:

- Do not build a new DogOps SLAM/map system. Use `VoxelGridMapper`, `CostMapper`, `ReplanningAStarPlanner`, `WavefrontFrontierExplorer`, `PatrollingModule`, and `MovementManager` through `unitree_go2_markers` / `unitree_go2_dogops`.
- “What the dog mapped” is DimOS `global_costmap` / `OccupancyGrid` with values `-1` unknown, `0` free, and `100` occupied.
- “Where he should go” is DogOps `RoutePlan` waypoints overlaid on that map. In the operator UI, a single inspection point creates both the waypoint and the photo/reading POI to keep simulation setup simple.
- “How he will get there” is DimOS planner `Path`.
- “Where he is now” is DimOS `odom` / `PoseStamped`.
- `DogOpsLiveMapModule` subscribes to `global_costmap`, `path`, and `odom`, persists full costmap snapshots into `site_map.dimos_costmap`, persists planner path into `site_map.dimos_path`, persists the latest robot pose, and computes known/free/occupied coverage stats.
- Keep DogOps semantic overlays separate: zones, no-go areas, assets, package tags, incidents, POIs, and route waypoints. Do not treat policy no-go zones as physical obstacles unless a future planner integration explicitly injects them into costmaps.
- The dashboard standard map panel embeds the real Rerun WebViewer (`@rerun-io/web-viewer`) against the local DimOS Rerun bridge. DogOps inspection-point/report controls are overlaid around that map surface; `map.json` remains only the fallback artifact view for offline reports/tests.
- `DOGOPS_RUNTIME_MODE=rerun-sim` keeps the dashboard on the Rerun WebViewer and uses `dogops rerun-sim` for local no-robot LiDAR replay. It is the local simulation UI path, not the static artifact path. For real DimOS/MuJoCo-style 3D mapping visuals, run the native Unitree Go2 Air simulator path, for example `uv run dimos --simulation run unitree-go2`, then publish DogOps overlays with `dogops rerun-sim --view-mode native-3d` to the same local Rerun source.
- Future alternative: make the DimOS/Rerun page the parent shell and embed DogOps as a side panel, or add a deeper Rerun click-coordinate bridge if the WebViewer exposes stable world-coordinate events.

If the dashboard exposes direct Go2 manual controls, they must be conservative, measurable, and independent of the dashboard UI shape:

- Use the native Go2 Sport API for manual velocity motions: `SPORT_MOD` / `Move` (`api_id=1008`) followed by `StopMove` (`api_id=1003`).
- Do not use wireless-controller joystick emulation as the primary dashboard movement path unless a future hardware test proves it is more reliable.
- Provide motion profiles rather than a single pulse: `Nudge`, `Step`, and `Walk`, with server-side caps for speed and duration.
- Disable Go2 obstacle avoidance before short linear manual motion in the confined demo arena; keep this scoped to manual movement only.
- Report odometry feedback after every motion command. A button is not considered validated just because the HTTP request returned.
- Keep one red hard stop available in the same control group.
- Protect robot-control POST endpoints with a per-server dashboard token, loopback host/origin checks, and server-side robot IP selection. Browser payloads must not choose arbitrary robot IPs.
- Cover this underlying capability with tests that assert Sport `Move`, `StopMove`, motion-profile caps, and response status handling, so later dashboard redesigns do not regress basic manual control.

### 13.2 Dashboard panels

Required panels:

1. Mission timeline.
2. Manifest / package reconciliation.
3. Incidents and work orders.
4. Verification status.
5. What changed.
6. Navigation eval.
7. Map and route editor with waypoints and POIs.
8. Evidence images and reading analysis for each POI.
9. Optional stretch: dock/portal readiness.

### 13.3 Report files

Every run writes:

```text
.dogops/runs/<run_id>/
  run.json
  observations.jsonl
  incidents.jsonl
  work_orders.jsonl
  nav_events.jsonl
  map.json
  route_plan.json
  poi_captures.jsonl
  sensor_readings.jsonl
  state.json
  report.json
  report.md
  dashboard.html
  evidence/
    *.jpg, *.png, or simulator-generated *.svg
```

The live dashboard can poll `state.json` every second. This is robust and easy.

---

## 14. Store design

Use stdlib `sqlite3` or JSONL. For speed and reliability, implement JSONL first, with a stable `DogOpsStore` interface.

Required store API:

```text
create_run(mission_id) -> MissionRun
finish_run(run_id, state, summary) -> MissionRun
append_observation(obs) -> None
append_incident(incident) -> None
update_incident(incident) -> None
append_work_order(work_order) -> None
update_work_order(work_order) -> None
append_nav_event(nav_event) -> None
set_site_map(site_map) -> None
set_route_plan(route_plan) -> None
append_poi_capture(capture) -> None
append_sensor_reading(reading) -> None
load_state(run_id) -> DogOpsState
write_state(run_id) -> Path
write_report(run_id) -> Path
```

JSONL is acceptable for the hackathon and public repo. Add SQLite as stretch only if JSONL is stable.

---

## 15. Staged implementation plan

Build in parts. Do not move to the next part until the current part's success criteria are met or a documented fallback is chosen.

### Part A — Offline product core

**Goal:** Product works without DimOS, robot, internet, or API keys.

Files:

```text
dimos/experimental/dogops/models.py
dimos/experimental/dogops/config_loader.py
dimos/experimental/dogops/store.py
dimos/experimental/dogops/mission_engine.py
dimos/experimental/dogops/nav_eval.py
dimos/experimental/dogops/report.py
dimos/experimental/dogops/cli.py
examples/dogops/*.yaml
docs/dogops/DEMO.md
```

Success criteria:

```bash
uv run python -m dimos.experimental.dogops.cli validate \
  --site examples/dogops/site_demo.yaml \
  --manifest examples/dogops/manifest_demo.yaml \
  --mission examples/dogops/mission_demo.yaml

uv run python -m dimos.experimental.dogops.cli simulate \
  --site examples/dogops/site_demo.yaml \
  --manifest examples/dogops/manifest_demo.yaml \
  --mission examples/dogops/mission_demo.yaml \
  --out .dogops/runs/latest

test -f .dogops/runs/latest/report.md
uv run pytest -q dimos/experimental/dogops
```

Must demonstrate in simulation:

- `PKG-104` wrong zone.
- `PKG-104` blocks `COOLING_1`.
- `INC-001` opened.
- human fix simulated.
- `INC-001` verified closed.
- `PKG-103` remains missing/open.
- nav summary exists.
- local map exists.
- route plan has waypoints and POIs.
- POI photo analysis and readings are present without cloud keys.

Exit path if Part A gets stuck:

- Reduce store to JSON files only.
- Remove dashboard from Part A.
- Keep report generation and tests.

### Part B — Dashboard/report product layer

**Goal:** A judge can understand the product from the dashboard before robot integration.

Files:

```text
dimos/experimental/dogops/dashboard.py
dimos/experimental/dogops/dashboard_static.py
dimos/experimental/dogops/test_report.py
dimos/experimental/dogops/test_cli_smoke.py
```

Success criteria:

```bash
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765
curl -fsS http://127.0.0.1:8765/api/state | jq .run_id
curl -fsS http://127.0.0.1:8765/api/report | jq .summary
curl -fsS http://127.0.0.1:8765/api/map | jq .status
curl -fsS http://127.0.0.1:8765/api/route | jq '.waypoints | length'
curl -fsS http://127.0.0.1:8765/api/poi | jq '.readings | length'
```

Visual success:

- dashboard shows map, route plan, POI photos/readings, manifest, incidents, work orders, nav metrics, and what changed.

Exit path:

- Generate `dashboard.html` and skip live FastAPI.
- Use static HTML polling local JSON only.

### Part C — DimOS skills + MCP

**Goal:** DogOps tools appear in MCP and can be called without an LLM.

Files:

```text
dimos/experimental/dogops/skills.py
dimos/experimental/dogops/blueprints.py
possibly dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py
```

Success criteria:

```bash
uv run pytest -q dimos/experimental/dogops
CI=1 uv run pytest -q -o addopts='' dimos/robot/test_all_blueprints_generation.py || true
git diff -- dimos/robot/all_blueprints.py
CI=1 uv run pytest -q -o addopts='' dimos/robot/test_all_blueprints_generation.py
uv run dimos list | rg dogops
uv run dimos --replay --viewer none run unitree-go2-dogops --daemon
uv run dimos status
uv run dimos mcp list-tools | rg 'run_mission|scan_zone|verify_work_order|nav_eval_report'
uv run dimos mcp call run_mission --json-args '{"mission_id":"receiving_sre_demo"}'
uv run dimos stop --force
```

Exit path:

- If blueprint is hard, keep offline CLI and direct `DogOpsSkillContainer` tests working, but record the exact registry blocker.
- If replay deploys modules but `dimos status` or MCP discovery cannot see a running instance, check for lingering replay processes, test skill methods directly, record the exact MCP blocker, and continue hardware/video prep only with a named fallback level.
- Do not mark final integration complete until `unitree-go2-dogops` appears in `dimos list` or the blocker is documented in `STATUS.md` and `docs/FAILURE_MEMORY.md`.

### Part D — Real/fake AprilTag observation

**Goal:** DogOps can read visible AprilTag IDs from camera images or fake fixtures.

Files:

```text
dimos/experimental/dogops/detector.py
dimos/experimental/dogops/observation_module.py
dimos/experimental/dogops/test_detector.py
```

Success criteria:

```bash
uv run dimos apriltag --ids '10,20,30,40,41,42,50,60,70,101-104' --size-mm 140 --family tag36h11 --out .dogops/apriltags.pdf
uv run pytest -q dimos/experimental/dogops/test_detector.py
```

Hardware smoke:

```bash
uv run dimos run unitree-go2-dogops --robot-ip <GO2_IP> --viewer none --daemon
uv run dimos mcp call scan_zone --json-args '{"zone_id":"INBOUND_DOCK"}'
uv run dimos log -n 200 | rg 'DogOps|tag|PKG|COOLING'
uv run dimos stop --force
```

Exit path:

- If camera-to-DimOS image conversion is hard, add `scan_zone --json-args '{"zone_id":"INBOUND_DOCK","simulated_tag_ids":[101,102,104]}'` as a guided fallback.
- Do not block the product on full pose estimation.

### Part E — Navigation integration + eval

**Goal:** Route execution attempts navigation and records real/guided metrics.

Minimum behavior:

- `run_mission` iterates mission targets.
- For each target, it attempts navigation via existing DimOS navigation interface if available.
- If navigation interface unavailable, it records a guided nav event and still performs scan/inspection.
- Metrics honestly state guided vs autonomous.

Success criteria:

```bash
uv run pytest -q dimos/experimental/dogops/test_nav_eval.py
uv run dimos --replay --viewer none run unitree-go2-dogops --daemon
uv run dimos mcp call nav_eval_report
uv run dimos stop --force
```

Real robot target:

- at least 3 staged target visits in the real demo arena, or a shorter guided route with fallback recorded;
- dashboard shows waypoint attempts and recovery.

Exit path:

- Keep guided mode visible and product-grade.
- Do not fake autonomous metrics.

### Part F — Live demo hardening

**Goal:** Repeatable 90-second run.

Success criteria:

- 3 successful full dry runs in a row using the same props.
- One 90-second video saved before code freeze, preferably L0/L1 with the real Go2.
- Emergency stop / `dimos stop --force` tested.
- Dashboard works after restart.
- Report regenerates after run.

Exit path:

- Use a shorter 2-station mission: `HOME -> INBOUND_DOCK -> COOLING_1 -> QA_HOLD`.
- Use guided fallback for navigation, but keep autonomous scans/verifications.

### Part G — Stretch features

Only after Parts A-F work.

Stretch order:

1. `dock_align(DOCK_1)` readiness panel.
2. `portal_entry(PORTAL_1)` fake elevator/threshold panel.
3. Optional Gemini/LLM summary, behind env flag.
4. Optional thermometer manual input UI.
5. Optional live Rerun viewer link/recording polish.

---

## 16. Test/fix loops

Use the narrowest check that proves the current change.

### 16.1 After model/config changes

```bash
uv run pytest -q dimos/experimental/dogops/test_config_loader.py dimos/experimental/dogops/test_store.py
```

### 16.2 After mission changes

```bash
uv run pytest -q dimos/experimental/dogops/test_mission_engine.py
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
cat .dogops/runs/latest/report.md
```

### 16.3 After dashboard changes

```bash
uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765 &
DASH_PID=$!
sleep 2
curl -fsS http://127.0.0.1:8765/api/state | jq .
curl -fsS http://127.0.0.1:8765/api/report | jq .
kill $DASH_PID
```

If visual UI changes were made, take a screenshot when practical.

### 16.4 After DimOS blueprint changes

```bash
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
uv run --no-sync pytest -q -o addopts='' dimos/experimental/dogops
CI=1 uv run --no-sync pytest -q -o addopts='' dimos/robot/test_all_blueprints_generation.py
uv run dimos list | rg dogops
```

### 16.5 After real robot changes

```bash
uv run dimos stop --force || true
uv run dimos run unitree-go2-dogops --robot-ip <GO2_IP> --viewer none --daemon
uv run dimos status
uv run dimos mcp list-tools
uv run dimos mcp call scan_zone --json-args '{"zone_id":"INBOUND_DOCK"}'
uv run dimos log -n 200
uv run dimos stop --force
```

### 16.6 If checks fail twice

1. Read the full error/log.
2. Add a short entry to `docs/FAILURE_MEMORY.md`:
   - date/time;
   - failing command;
   - exact error summary;
   - attempted fixes;
   - decision/fallback.
3. Update `STATUS.md`.
4. Continue with the documented fallback.

---

## 17. Failure memory template

Add entries like this when the same failure happens twice or when a blocker changes the plan:

```markdown
## MCP blueprint does not expose DogOps skills

Command: `uv run dimos --replay --viewer none run unitree-go2-dogops --daemon`
Symptom: replay deploys DogOps modules, but `dimos status` or `dimos mcp list-tools` cannot see a running instance.
Tried:
1. Checked full logs.
2. Tried one alternate documented DimOS launch mode.
Learned: exact framework behavior or missing dependency.
Decision: keep direct CLI/skill tests working, record fallback level, and return with a new fact.
```

Keep failure entries short, factual, and reusable. Prefer stable causes and recovery steps over dated narrative.

---

## 18. Public repo and contribution rules

- Keep DogOps code in `dimos/experimental/dogops` unless a generic upstream fix is needed.
- Avoid editing core DimOS unless required. If required, isolate the generic fix and add tests.
- Keep demo configs non-private. Do not include real venue map, device serials, tokens, or private IPs.
- No `.env` commits.
- No generated logs/screenshots with personal data.
- Keep commits focused:
  - `dogops: add offline mission engine`
  - `dogops: add work-order dashboard`
  - `dogops: expose mcp skills`
  - `dogops: add go2 blueprint`

---

## 19. Codex behavior rules

This section is for the Codex `/goal` run.

1. Start by reading `AGENTS.md`, `SPEC.md`, `STATUS.md`, and `docs/FAILURE_MEMORY.md`.
2. Implement Part A completely before Part B.
3. For each part, state success criteria in the working notes before editing.
4. Use tight loops: edit one area, run the specific test, fix, rerun.
5. After two failed fixes on the same issue, update failure memory and choose fallback.
6. Do not create weird workarounds to make tests pass. If a path is stale, hard-cut it.
7. Do not add optional LLM/API dependencies to base flow.
8. Do not start stretch features until core demo works.
9. Update `STATUS.md` at the end of each part.
10. Leave the repo in a runnable state even if later parts are incomplete.

---

## 20. Acceptance criteria for the full product

### Required before submission

- `uv run pytest -q dimos/experimental/dogops` passes.
- `uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest` produces a coherent report.
- Dashboard opens and shows report/state/nav metrics.
- `unitree-go2-dogops` appears in `dimos list`.
- MCP exposes DogOps skills or direct CLI fallback is documented.
- Base `unitree-go2` hardware smoke is attempted against the real Go2.
- `unitree-go2-dogops` hardware/guided run is attempted, or an exact DimOS/robot blocker is documented.
- 90-second demo video shows the closed loop.
- README explains how to run offline and on Go2.
- `STATUS.md` accurately states what is complete and what is guided/stretch.

### Nice-to-have before submission

- Live Go2 reads at least package tags.
- Live route has at least 3 target visits.
- Nav eval includes at least one recovery event.
- Dock alignment readiness panel works.
- Portal/elevator simulation works.
- Rerun view shows camera/map context.

### Winning-level polish

- Dashboard looks like an ops product, not a debug page.
- Report uses crisp product language.
- Demo script includes one failure/recovery moment.
- The code is clean enough that Dimensional engineers can imagine upstreaming it.

---

## 21. README pitch text

Use this as the public project pitch:

> DogOps is a DimOS SiteOps Agent for Go2. It combines warehouse inspection, shipping/receiving, physical SRE, and navigation evaluation. The robot receives a manifest, scans AprilTag-labeled packages, detects when a misplaced package blocks a cooling/asset zone, opens a spatial work order with evidence, waits for human remediation, revisits the exact location, verifies closure, and produces a dashboard report with package state, incidents, “what changed,” and navigation/relocalization metrics. The base demo runs without cloud API keys and exposes deterministic SiteOps skills through DimOS/MCP; optional stretch features add dock-alignment readiness and portal/elevator entry simulation.
