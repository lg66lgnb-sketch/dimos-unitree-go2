# DIMOS_CODEBASE_NOTES.md

These notes are based on the attached `dimos-main.zip` codebase.

## Useful repo facts

- Project uses Python 3.10+ and `uv`; `.python-version` is present.
- Main package is `dimos`.
- CLI entry point is `dimos = dimos.robot.cli.dimos:cli_main`.
- `dimos run`, `dimos status`, `dimos log`, `dimos stop`, `dimos list`, and `dimos mcp ...` are implemented in `dimos/robot/cli/dimos.py`.
- `dimos apriltag` exists and generates AprilTag/ArUco PDFs.
- `pyproject.toml` has extras including `base`, `unitree`, `apriltag`, `web`, `visualization`, `perception`, `sim`, `mapping`, `agents`.

## Go2 anchors

| Purpose | Path |
|---|---|
| Go2 smart blueprint | `dimos/robot/unitree/go2/blueprints/smart/unitree_go2.py` |
| Go2 basic connection | `dimos/robot/unitree/go2/connection.py` |
| Go2 agentic blueprint | `dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_agentic.py` |
| Common Go2 agent skills | `dimos/robot/unitree/go2/blueprints/agentic/_common_agentic.py` |
| Go2 security demo blueprint | `dimos/robot/unitree/go2/blueprints/agentic/unitree_go2_security.py` |
| Unitree skill container | `dimos/robot/unitree/unitree_skill_container.py` |

`unitree_go2` composes:

- `unitree_go2_basic`;
- `VoxelGridMapper`;
- `CostMapper`;
- `ReplanningAStarPlanner`;
- `WavefrontFrontierExplorer`;
- `PatrollingModule`;
- `MovementManager`.

`unitree_go2_markers` composes `unitree_go2` + `MarkerTfModule.blueprint(marker_length_m=0.1)`.

For DogOps, either override marker length to match printed size or build a dedicated blueprint that passes the correct `marker_length_m`.

## AprilTag anchors

| Purpose | Path |
|---|---|
| Marker detector/TF module | `dimos/perception/fiducial/marker_tf_module.py` |
| Tag PDF generator | `dimos/utils/cli/apriltag.py` |
| CLI command | `dimos/robot/cli/dimos.py` function `apriltag` |

`MarkerTfModule` defaults to `DICT_APRILTAG_36h11` and publishes marker transforms. It needs `marker_length_m`.

## MCP anchors

| Purpose | Path |
|---|---|
| `@skill` decorator | `dimos/agents/annotation.py` |
| MCP server | `dimos/agents/mcp/mcp_server.py` |
| MCP client | `dimos/agents/mcp/mcp_client.py` |
| Navigation skills | `dimos/agents/skills/navigation.py` |

Base DogOps should include `McpServer` but not `McpClient`. This exposes skills without requiring LLM credentials.

## Blueprint registry

| Purpose | Path |
|---|---|
| Generated registry | `dimos/robot/all_blueprints.py` |
| Registry generator test | `dimos/robot/test_all_blueprints_generation.py` |

Run:

```bash
uv run pytest dimos/robot/test_all_blueprints_generation.py
```

In non-CI, this test writes the generated registry and may fail if it changed. Inspect diff and rerun.

## Recommended DogOps blueprint choices

Start with:

```python
unitree_go2_dogops = autoconnect(
    unitree_go2_markers,
    DogOpsObservationModule.blueprint(),
    DogOpsSkillContainer.blueprint(),
    DogOpsDashboardModule.blueprint(),
    DogOpsNavEvalModule.blueprint(),
    McpServer.blueprint(),
)
```

Only add `McpClient` to a second optional blueprint:

```python
unitree_go2_dogops_agentic = autoconnect(unitree_go2_dogops, McpClient.blueprint())
```

## Do not overfit to existing security demo

The repo has `dimos/experimental/security_demo`. DogOps should not become a generic security demo. Use it only as reference for module/test patterns if useful.
