from dimos.experimental.dogops.blueprints import build_unitree_go2_dogops_blueprint


unitree_go2_dogops = build_unitree_go2_dogops_blueprint().global_config(
    n_workers=12,
    robot_model="unitree_go2",
)

__all__ = ["unitree_go2_dogops"]
