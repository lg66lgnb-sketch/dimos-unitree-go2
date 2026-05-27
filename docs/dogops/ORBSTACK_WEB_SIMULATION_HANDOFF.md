# DogOps OrbStack Web Simulation Handoff

This note records the workflow validated in OrbStack / web simulation mode. It is intentionally not a real-Go2 hardware validation record.

The goal of this PR is to make the DogOps offline and OrbStack web workflow reproducible, then provide a clear handoff path for applying the same workflow to a real Unitree Go2 later.

## Scope of this PR

This PR validates:

- DogOps deterministic configuration validation;
- mission simulation;
- report generation;
- map generation;
- route planning;
- POI and navigation evidence generation;
- local DogOps dashboard;
- OrbStack web visualization through DogOps Dashboard, Rerun Web Viewer, and DimOS WebSocket UI.

This PR does not claim:

- real-Go2 hardware validation;
- autonomous real-Go2 route completion;
- calibrated thermal sensing;
- real self-charging;
- real elevator or portal behavior.

## Offline / OrbStack workflow

Run from the full DimOS checkout or the prepared DogOps development checkout:

```bash
uv run --no-sync python -m dimos.experimental.dogops.cli validate
uv run --no-sync python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run --no-sync python -m dimos.experimental.dogops.cli report --run .dogops/runs/latest
uv run --no-sync python -m dimos.experimental.dogops.cli map --run .dogops/runs/latest
uv run --no-sync python -m dimos.experimental.dogops.cli plan --run .dogops/runs/latest --add-waypoint TEMP_1 --add-poi TEMP_1
uv run --no-sync python -m dimos.experimental.dogops.cli run-plan --run .dogops/runs/latest
uv run --no-sync python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --host 0.0.0.0 --port 8765
```

The run should produce files such as:

```text
.dogops/runs/latest/state.json
.dogops/runs/latest/report.md
.dogops/runs/latest/report.json
.dogops/runs/latest/map.json
.dogops/runs/latest/route_plan.json
.dogops/runs/latest/poi_captures.jsonl
.dogops/runs/latest/sensor_readings.jsonl
```

Do not commit generated `.dogops/` outputs.

## Browser URLs from Mac

When the services run inside OrbStack Ubuntu, open the web pages from the Mac browser.

DogOps Dashboard:

```text
http://<UBUNTU_IP>:8765
```

Rerun Web Viewer, script/default port:

```text
http://<UBUNTU_IP>:9878/?url=rerun%2Bhttp%3A%2F%2F<UBUNTU_IP>%3A9877%2Fproxy
```

Rerun Web Viewer, alternate viewer port used in earlier successful tests:

```text
http://<UBUNTU_IP>:9090/?url=rerun%2Bhttp%3A%2F%2F<UBUNTU_IP>%3A9877%2Fproxy
```

DimOS WebSocket UI:

```text
http://<UBUNTU_IP>:7779
```

Port meaning:

| Port | Meaning |
|---:|---|
| 8765 | DogOps dashboard |
| 9878 or 9090 | Rerun Web Viewer page |
| 9877 | Rerun proxy data source, used as `rerun+http://<UBUNTU_IP>:9877/proxy` |
| 7779 | DimOS WebSocket visualization UI |
| 3030 | Rerun viewer websocket endpoint; do not open directly as a webpage |

Check active listeners with:

```bash
ss -lntp | grep -E '9877|9878|9090|7779|8765|3030'
```

## Real-Go2 handoff, not required for this PR

The same DogOps workflow can later be applied to a real Unitree Go2 by validating the base `unitree-go2` path first, then launching `unitree-go2-dogops` with a valid robot IP.

That future hardware path requires:

```bash
export GO2_IP=<GO2_IP>
uv run --no-sync dimos run unitree-go2 --robot-ip "$GO2_IP" --viewer none --daemon
uv run --no-sync dimos status
uv run --no-sync dimos stop --force
```

Then, only after the base robot path is healthy:

```bash
uv run --no-sync dimos run unitree-go2-dogops --robot-ip "$GO2_IP" --viewer none --daemon
```

The error:

```text
AssertionError: IP address must be provided
```

means someone entered the real hardware blueprint path without providing `GO2_IP`. It is not a failure of the offline or OrbStack web simulation workflow.
