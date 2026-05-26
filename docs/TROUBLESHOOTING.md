# TROUBLESHOOTING.md

## `uv sync` fails or takes too long

Use a lighter install:

```bash
uv sync --extra base --extra unitree --extra apriltag --extra visualization --extra web --group tests --group lint
```

Avoid `--extra all` unless needed.

## `cv2.aruco` missing

Install AprilTag extra:

```bash
uv sync --extra apriltag
```

or include it with the main sync.

## Headless Rerun/display crash

Use:

```bash
uv run dimos --viewer none run <blueprint>
```

Keep DogOps dashboard separate.

## `dimos mcp list-tools` has no DogOps tools

Check:

1. Blueprint includes `McpServer.blueprint()`.
2. `DogOpsSkillContainer` methods use `@skill` from `dimos.agents.annotation`.
3. The blueprint includes `DogOpsSkillContainer.blueprint()`.
4. The run is active: `uv run dimos status`.
5. Logs: `uv run dimos log -n 200`.

Fallback: call skill container methods in tests and use CLI for demo until MCP is fixed.

## `unitree-go2-dogops` not in `dimos list`

Run registry generator:

```bash
uv run pytest dimos/robot/test_all_blueprints_generation.py || true
git diff -- dimos/robot/all_blueprints.py
uv run pytest dimos/robot/test_all_blueprints_generation.py
uv run dimos list | rg dogops
```

If still missing, put the blueprint variable in `dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_dogops.py` and ensure it is module-level.

Do not accept a standalone-pack pass as final. The command must be run in the full DimOS checkout.

## Real Go2 does not connect

First test base blueprint:

```bash
uv run dimos run unitree-go2 --robot-ip <GO2_IP> --viewer none --daemon
uv run dimos status
uv run dimos log -n 200
uv run dimos stop --force
```

If base fails, ask event mentors for network/WebRTC setup. Do not debug DogOps until base Go2 works.

## Tags not detected

- Increase tag size.
- Mount tags vertically.
- Reduce distance.
- Avoid glare.
- Use matte paper.
- Verify `marker_length_m` matches printed black-border size.
- Test with generated images before hardware.

## Live demo is flaky

Use fallback levels:

- L1: guided nav + live tag scans + dashboard.
- L2: Go2 clip + offline dashboard/report.
- L3: offline product demo + recorded robot movement.

Do not fake metrics. Mark guided interventions honestly.
