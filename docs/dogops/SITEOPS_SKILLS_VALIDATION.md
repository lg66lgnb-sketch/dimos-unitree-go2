# SiteOps Skills Validation

This validates the SiteOps / DogOps skill option from issue
[#2](https://github.com/lg66lgnb-sketch/dimos-unitree-go2/issues/2), excluding the
Three.js / DimSim path.

## Validated Skill Surface

The DogOps skill container now exposes the issue-level SiteOps names:

- `scan_zone(zone_id)`
- `inspect_asset(asset_id)`
- `read_gauge(asset_id)`
- `check_clearance(asset_id)`
- `detect_blocked_aisle(zone_id)`
- `scan_receiving_manifest(zone_id)`
- `open_work_order(entity_id, issue_type)`
- `verify_work_order(work_order_id)`
- `nav_eval_report(run_id)`

`read_gauge`, `check_clearance`, `detect_blocked_aisle`, and
`scan_receiving_manifest` are deterministic wrappers over the existing DogOps
site, manifest, mission, incident, and report state. They are intentionally
hardware-independent so the MCP surface can be validated before Go2 runs.

## Local Validation

Run from this repo:

```bash
uv run pytest -q dimos/experimental/dogops/test_skills.py
```

Broader DogOps check:

```bash
uv run pytest -q dimos/experimental/dogops
```

## Full DimOS MCP Validation

After copying this pack into a full DimOS checkout and generating the DogOps
blueprint registry, validate the tools through DimOS MCP:

```bash
uv run dimos mcp list-tools | rg 'scan_zone|inspect_asset|read_gauge|check_clearance|detect_blocked_aisle|scan_receiving_manifest|open_work_order|verify_work_order|nav_eval_report'
uv run dimos mcp call scan_receiving_manifest --json-args '{"zone_id":"INBOUND_DOCK"}'
uv run dimos mcp call read_gauge --json-args '{"asset_id":"TEMP_1"}'
uv run dimos mcp call nav_eval_report
```

The base validation remains deterministic. Real Go2, AprilTag camera input, and
guided navigation can be layered on top without changing these skill names.
