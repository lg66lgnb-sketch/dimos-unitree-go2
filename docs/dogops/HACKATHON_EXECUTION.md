# DogOps Hackathon Execution

This document is the field checklist for turning the DogOps code into a clear
90-second hackathon demo. It is intentionally practical: stage the arena, run the
minimum checks, record evidence, and be honest about fallback level.

## Demo Goal

Show a Unitree Go2 acting as a physical SiteOps agent:

```text
HOME -> INBOUND_DOCK -> COOLING_1 -> QA_HOLD -> HOME
```

The robot scans package and asset tags, detects that `PKG-104` is in the wrong
zone and blocking `COOLING_1`, opens `INC-001` / `WO-001`, waits for a human to
move the package to `QA_HOLD`, revisits `COOLING_1`, verifies closure, and shows
the dashboard/report/nav metrics.

## Field Checklist

### Arena

- [ ] Mark the route: `HOME -> INBOUND_DOCK -> COOLING_1 -> QA_HOLD -> HOME`.
- [ ] Keep lanes wide, short, and low-speed.
- [ ] Keep cables, power banks, bags, and loose tape away from robot feet.
- [ ] Place a visible fake cooling vent or sign for `COOLING_1`.
- [ ] Place `PKG-104` near `COOLING_1` so it clearly blocks the cooling clearance.
- [ ] Leave `PKG-103` absent so the report has one honest open exception.
- [ ] Prepare `QA_HOLD` as the human remediation zone.
- [ ] Keep a human ready to move `PKG-104`; the robot must not push packages.

### Tags And Labels

- [ ] Print AprilTag 36h11 IDs:
  `10,20,30,40,41,42,43,50,60,70,101,102,103,104`.
- [ ] Mount tags vertically near Go2 camera height or angled toward the camera.
- [ ] Keep a clean white border around each tag.
- [ ] Add large human-readable labels above tags:
  `HOME`, `INBOUND_DOCK`, `QA_HOLD`, `RACK_ROW_A`, `COOLING_1`, `PKG-101`,
  `PKG-102`, `PKG-104`.
- [ ] Verify tags are visible from the planned inspection distance before the
  full run.

### Software

- [ ] Run the offline simulation:
  ```bash
  uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
  ```
- [ ] Confirm the report mentions `PKG-104`, `COOLING_1`, `INC-001`, `WO-001`,
  `PKG-103 missing`, and `verified_closed`.
- [ ] Start the dashboard:
  ```bash
  uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765
  ```
- [ ] Capture the dashboard home page and `/api/report` output.
- [ ] Run the base Go2 smoke test before DogOps-specific hardware:
  ```bash
  uv run dimos stop --force || true
  uv run dimos --viewer none run unitree-go2 -o "go2connection.ip=${GO2_IP}" --daemon
  uv run dimos status
  uv run dimos stop --force
  ```
- [ ] If available, run or attempt `unitree-go2-dogops` and record the exact
  result.

## Fallback Levels

Use the highest level that works reliably. State the level in the report, video
narration, or final handoff.

| Level | Meaning | Use When |
|---|---|---|
| L0 | Full autonomous Go2 + DogOps dashboard + MCP | Navigation, MCP, and dashboard are all stable. |
| L1 | Guided navigation + real tag scan + dashboard | Robot runs safely, but autonomy is flaky. |
| L2 | Go2 movement/tag video + offline dashboard/report | Hardware footage exists, but MCP or live integration is flaky. |
| L3 | Offline product demo + recorded Go2 clip only | Robot/network path is blocked. |

Never hide guided mode, retries, safety stops, or manual intervention. Record
them as nav metrics or operator events.

## 90-Second Video Shot List

| Time | Shot | Must Show |
|---:|---|---|
| 0-8s | Product setup | DogOps title, arena, Go2, and the SiteOps problem. |
| 8-18s | Mission start | Operator starts `receiving_sre_demo`; dashboard visible. |
| 18-30s | Inbound scan | `INBOUND_DOCK`, package tags, `PKG-101` and `PKG-102` observed. |
| 30-45s | Hazard detection | `PKG-104` blocking `COOLING_1`; dashboard opens `INC-001`. |
| 45-55s | Work order | `WO-001`, severity `P1`, evidence, and recommended action. |
| 55-68s | Human remediation | Human moves `PKG-104` from `COOLING_1` to `QA_HOLD`. |
| 68-80s | Verification | Robot revisits or verifies `COOLING_1`; `WO-001` becomes `verified_closed`. |
| 80-90s | Final report | Dashboard/report: packages scanned, incidents, open `PKG-103`, nav metrics, fallback level. |

## Evidence To Save

- [ ] `.dogops/runs/latest/report.md`
- [ ] `.dogops/runs/latest/report.json`
- [ ] `.dogops/runs/latest/state.json`
- [ ] `.dogops/runs/latest/nav_events.jsonl`
- [ ] dashboard screenshot or screen recording
- [ ] terminal output for simulation, dashboard, registry/MCP, and hardware smoke
- [ ] short robot/arena clip
- [ ] fallback level and reason
- [ ] final 90-second video

## Final Handoff Checklist

- [ ] The story is understandable without reading the code.
- [ ] The robot never pushes or manipulates packages.
- [ ] Human remediation is visible and intentional.
- [ ] The report proves the closed loop: detect, open work order, remediate, verify.
- [ ] Navigation metrics include retries, guided interventions, and safety stops.
- [ ] Any blocked hardware path has exact logs and a fallback level.
