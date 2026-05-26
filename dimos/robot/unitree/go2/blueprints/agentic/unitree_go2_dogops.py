try:  # pragma: no cover - exercised inside a full DimOS checkout.
    from dimos.agents.mcp.mcp_server import McpServer
    from dimos.core.coordination.blueprints import autoconnect
    from dimos.experimental.dogops.dashboard import DogOpsDashboardModule
    from dimos.experimental.dogops.nav_eval import DogOpsNavEvalModule
    from dimos.experimental.dogops.observation_module import DogOpsObservationModule
    from dimos.experimental.dogops.skills import DogOpsSkillContainer
    from dimos.robot.unitree.go2.blueprints.smart.unitree_go2 import unitree_go2_markers
except ModuleNotFoundError:  # pragma: no cover - covered by local pack fallback tests.
    from dimos.experimental.dogops.blueprints import unitree_go2_dogops
else:
    unitree_go2_dogops = autoconnect(
        unitree_go2_markers,
        DogOpsObservationModule.blueprint(),
        DogOpsSkillContainer.blueprint(),
        DogOpsDashboardModule.blueprint(),
        DogOpsNavEvalModule.blueprint(),
        McpServer.blueprint(),
    ).global_config(n_workers=12, robot_model="unitree_go2")

__all__ = ["unitree_go2_dogops"]
