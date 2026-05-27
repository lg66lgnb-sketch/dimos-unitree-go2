# DogOps QR Cargo Integration

DogOps accepts decoded QR cargo scan events from the standalone
`qr-cargo-bridge` project and displays them as run-local, report-only evidence in
the dashboard. QR events are persisted beside the current DogOps run and can be
optionally promoted into the run-local map-authoring layer.

QR cargo events do not actuate the robot, execute routes, enforce planner rules,
or promote data into canonical YAML.

## Run-Local Files

Events are appended to:

```text
.dogops/runs/<run_id>/qr_events.jsonl
```

DogOps also writes a compact latest-state helper file:

```text
.dogops/runs/<run_id>/qr_cargo_state.json
```

## Payload Schema

The QR payload is the JSON encoded inside the QR label:

```json
{
  "v": 1,
  "type": "cargo",
  "warehouse_id": "WH-03",
  "location_node_id": "WH03-A12-SHELF05",
  "zone": "A12",
  "shelf_id": "SHELF-05",
  "cargo_id": "BOX-20260527-018",
  "task": "scan_and_report"
}
```

`location_node_id` is the static warehouse or map node encoded by the QR label.
It may match a DogOps zone, asset, package, checkpoint, or authored map entity.

## Event Schema

The event is what `qr-cargo-bridge` posts after a scan:

```json
{
  "timestamp": 1779875037.519,
  "source": "image_file",
  "status": "decoded",
  "qr_payload_raw": "{\"v\":1,\"type\":\"cargo\",\"warehouse_id\":\"WH-03\",\"location_node_id\":\"WH03-A12-SHELF05\",\"cargo_id\":\"BOX-20260527-018\",\"task\":\"scan_and_report\"}",
  "qr_payload": {
    "v": 1,
    "type": "cargo",
    "warehouse_id": "WH-03",
    "location_node_id": "WH03-A12-SHELF05",
    "zone": "A12",
    "shelf_id": "SHELF-05",
    "cargo_id": "BOX-20260527-018",
    "task": "scan_and_report"
  },
  "robot_pose_at_detection": {
    "frame": "map",
    "x": null,
    "y": null,
    "yaw": null
  },
  "bbox_px": [[40.0, 40.0], [289.0, 40.0], [289.0, 289.0], [40.0, 289.0]],
  "action_policy": "report_only"
}
```

`robot_pose_at_detection` is the dynamic pose where the robot or camera observed
the QR. If both the dynamic pose and static `location_node_id` pose are known,
`/api/map` includes both plus a `pose_delta`.

## API

Protected write endpoints use the same local dashboard guard as map authoring:
loopback host, same-origin when an Origin header is present, and
`X-DogOps-Control-Token`.

```text
POST /api/qr/events
GET  /api/qr/events
GET  /api/qr/events/latest?limit=50
GET  /api/qr/events/<event_id>
POST /api/qr/events/<event_id>/promote_to_package
POST /api/qr/events/<event_id>/promote_to_label
POST /api/qr/events/<event_id>/bind_location_node
```

Promotion endpoints only update `.dogops/runs/<run_id>/map_authoring.json`.
They do not replace route, mission, site, or planner configuration.

## Posting From qr-cargo-bridge

For a repeatable local demo, start DogOps with a known token:

```bash
DOGOPS_DASHBOARD_TOKEN=dev-qr-token uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --host 127.0.0.1 --port 8765
```

Then post scan events with the same token header. If `qr-cargo-bridge` supports
custom headers:

```bash
qr-cargo-bridge scan-webcam \
  --webcam-index 0 \
  --events-out artifacts/qr_events/qr_webcam_events.jsonl \
  --post-url http://127.0.0.1:8765/api/qr/events \
  --post-header "X-DogOps-Control-Token: dev-qr-token"
```

Image-file smoke:

```bash
qr-cargo-bridge scan-image \
  --image artifacts/qr_labels/WH-03_BOX-20260527-018.png \
  --events-out artifacts/qr_events/qr_events.jsonl \
  --annotated-out artifacts/qr_events/annotated_result.png \
  --post-url http://127.0.0.1:8765/api/qr/events \
  --post-header "X-DogOps-Control-Token: dev-qr-token"
```

If the current `qr-cargo-bridge` CLI does not support custom headers yet, add
header support there or use the DogOps sample poster:

```bash
DOGOPS_DASHBOARD_TOKEN=dev-qr-token \
  uv run python scripts/dogops_post_sample_qr_event.py \
  --url http://127.0.0.1:8765/api/qr/events
```

Equivalent curl:

```bash
curl -fsS \
  -H "Content-Type: application/json" \
  -H "X-DogOps-Control-Token: dev-qr-token" \
  --data @examples/dogops/qr_cargo_event_sample.json \
  http://127.0.0.1:8765/api/qr/events
```

## Dashboard Behavior

The dashboard shows a QR Cargo panel with the latest events, payload fields,
source, status, action policy, robot pose, and action buttons. `/api/map`
returns a separate `qr_cargo_events` overlay, and the map renders QR cargo
markers when a pose is available.

Safety boundaries:

- QR events are report-only by default.
- QR events never directly control the Go2.
- QR events never execute or replace routes.
- QR events never promote exported state into canonical YAML automatically.
- QR events never become planner enforcement automatically.
