# DogOps Dry Runs

Run the local deterministic demo loop:

```bash
PORT=8765 ./scripts/dogops_demo_dry_run.sh
```

The script validates configs, simulates the mission, checks the report for the closed-loop result, starts the dashboard, verifies `/api/state`, `/api/report`, and `/api/nav`, then stops the temporary dashboard.

Expected checks:

- run state is `done`;
- report has `2` manifest exceptions;
- nav reports `4` waypoints reached and `1.0` route coverage;
- report includes `INC-001` resolved, `PKG-103` missing, and the nav summary.

For repeated local rehearsal:

```bash
for i in 1 2 3; do
  PORT=$((8765 + i)) ./scripts/dogops_demo_dry_run.sh
done
```

Hardware dry runs are required for final when the real Go2 is available. After the local loop passes, run the base `unitree-go2` smoke and then the `unitree-go2-dogops` sequence in [HARDWARE_HANDOFF.md](HARDWARE_HANDOFF.md).

Record guided navigation honestly in nav metrics and use the offline dashboard only as fallback L2/L3 if live DimOS/MCP is unavailable.
