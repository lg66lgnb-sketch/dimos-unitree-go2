# DogOps Demo

## Real-Go2 Target

The real Go2 is available. Use the offline demo as a safety net, but final evidence should include L0 or L1 hardware whenever possible:

```text
L0: full autonomous Go2 + dashboard + MCP
L1: Go2 scans tags + guided navigation + dashboard
L2: Go2 movement/tag video + offline dashboard/report
L3: offline product demo + recorded Go2 clip only
```

Run the hardware sequence from [HARDWARE_HANDOFF.md](HARDWARE_HANDOFF.md) after registry/MCP validation passes.

## Part A Offline Demo

Run the deterministic offline mission:

```bash
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
cat .dogops/runs/latest/report.md
```

The offline run demonstrates the core closed loop without robot hardware, cloud APIs, or an LLM:

1. Load the demo site, manifest, policy, and mission.
2. Scan `INBOUND_DOCK` and find `PKG-101` and `PKG-102`.
3. Inspect `COOLING_1` and find `PKG-104` in the wrong zone blocking cooling.
4. Open `INC-001` / `WO-001`.
5. Simulate human remediation by moving `PKG-104` to `QA_HOLD`.
6. Verify `COOLING_1` clear and close `INC-001`.
7. Leave `PKG-103` as the open missing-package issue.
8. Write the run report and navigation metrics.

## Part B Dashboard Demo

Serve the latest run:

```bash
uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765
```

Open <http://127.0.0.1:8765/> to view the dashboard.

API checks:

```bash
curl -fsS http://127.0.0.1:8765/api/state
curl -fsS http://127.0.0.1:8765/api/report
curl -fsS http://127.0.0.1:8765/api/nav
```

## Part D Tag Detector Demo

Base simulated detector path:

```bash
uv run pytest -q dimos/experimental/dogops/test_detector.py
```

Optional OpenCV path:

```bash
uv run --extra vision python -c "import cv2; print(cv2.__version__); print(hasattr(cv2, 'aruco'))"
```

The detector uses AprilTag 36h11 IDs from `examples/dogops/site_demo.yaml`.

## Local Dry Run

```bash
PORT=8765 ./scripts/dogops_demo_dry_run.sh
```

Use `PORT=18765` or another port if `8765` is already in use.
