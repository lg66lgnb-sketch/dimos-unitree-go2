# Hardware subagent prompt

Read `AGENTS.md`, `SPEC.md`, `STATUS.md`, `docs/RUNBOOK_MAC_GO2.md`, `docs/SAFETY.md`, and `docs/dogops/HARDWARE_HANDOFF.md` first.

Own only hardware runbooks, demo evidence notes, and command verification. Do not change core DogOps logic unless the main agent explicitly assigns a narrow fix.

Goal: prove the real-Go2 path or document the exact blocker.

Success:

```bash
uv run dimos list | rg 'unitree-go2'
uv run dimos stop --force || true
uv run dimos run unitree-go2 --robot-ip "$GO2_IP" --viewer none --daemon
uv run dimos status
uv run dimos log -n 100
uv run dimos stop --force
```

After DogOps registry passes:

```bash
uv run dimos run unitree-go2-dogops --robot-ip "$GO2_IP" --viewer none --daemon
uv run dimos mcp list-tools | rg 'run_mission|scan_zone|verify_work_order|nav_eval_report'
uv run dimos mcp call run_mission --json-args '{"mission_id":"receiving_sre_demo"}'
uv run dimos stop --force
```

Rules:

- Keep the route short and slow.
- Human moves packages; robot only observes/verifies.
- Stop immediately if movement is unsafe.
- Record fallback level L0-L3 and exact evidence collected.
