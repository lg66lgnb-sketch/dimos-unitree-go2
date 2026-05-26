# DEMO.md

## 90-second script

Target fallback level: L0 or L1 because the real Go2 is available.

```text
L0 = full autonomous Go2 + DogOps dashboard + MCP
L1 = Go2 scans tags + guided navigation + dashboard
L2 = Go2 movement/tag video + offline dashboard/report
L3 = offline product demo + recorded Go2 clip only
```

State the fallback level in the final report/video if it is not L0.

### 0-8s — intro

Say:

> DogOps is a DimOS SiteOps Agent. It combines shipping and receiving, warehouse inspection, physical SRE, and navigation evaluation on a Unitree Go2.

Show dashboard title and arena.

### 8-15s — mission start

Run or show:

```bash
uv run dimos mcp call run_mission --json-args '{"mission_id":"receiving_sre_demo"}'
```

Fallback if MCP is blocked but the local product works:

```bash
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
```

### 15-30s — inbound dock

Robot goes to/looks at INBOUND_DOCK. Dashboard updates:

```text
PKG-101 found OK
PKG-102 found OK
PKG-103 missing
PKG-104 not in expected zone
```

### 30-45s — blocked cooling incident

Robot inspects RACK_ROW_A / COOLING_1. Dashboard opens:

```text
INC-001 P1 BLOCKED_COOLING
Entity: COOLING_1
Related package: PKG-104
Recommended action: move PKG-104 to QA_HOLD
```

### 45-55s — work order

Show work-order card with evidence and nav metric.

Say:

> This is not just detection. DogOps created a spatial work order tied to the package, asset, and robot route.

### 55-65s — human remediation

Human moves `PKG-104` from cooling area to QA_HOLD.

Click or run:

```bash
uv run dimos mcp call mark_ready_to_verify --json-args '{"work_order_id":"WO-001"}'
```

### 65-78s — verification

Robot revisits or re-scans `COOLING_1`.

Run/show:

```bash
uv run dimos mcp call verify_work_order --json-args '{"work_order_id":"WO-001"}'
```

Dashboard turns work order green:

```text
WO-001 verified closed
COOLING_1 clear
PKG-104 moved to QA_HOLD
```

### 78-90s — report

Show final report:

```text
Packages scanned: 4
Manifest exceptions: 2
Incidents opened: 2
Work orders verified closed: 1
Open exception: PKG-103 missing
Nav: 5/5 waypoints reached, 1 recovery, 0 safety stops
What changed: PKG-104 moved from COOLING_1 to QA_HOLD; INC-001 resolved.
```

## One-liner for judges

> DogOps turns DimOS into a closed-loop physical operations agent: it sees assets and packages, remembers expected state, reasons about site policy, acts through navigation and work orders, verifies human fixes, and reports auditable results.

## Live demo fallback language

If using the real Go2 with guided navigation:

> This is running on the Go2 with guided navigation for safety. DogOps records that intervention in the nav metrics while the SiteOps loop, work-order lifecycle, verification, and report run live.

If guided mode is used:

> We are using guided navigation for this live run, and DogOps records that honestly in the nav metrics. The SiteOps loop, inspection, work-order lifecycle, verification, and report are running live.

If offline dashboard is used:

> This is the product dashboard generated from the robot/demo run. The hardware clip shows the same tag/asset workflow; the offline mode lets us reproduce and test the full loop deterministically.
