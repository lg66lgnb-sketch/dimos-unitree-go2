from __future__ import annotations

import pytest

from dimos.experimental.dogops.mission_engine import run_offline_simulation
from dimos.experimental.dogops.rerun_sim import (
    IMAGE_HEIGHT_PX,
    IMAGE_WIDTH_PX,
    _parse_local_rerun_source,
    _poi_camera_image,
    build_mapping_frames,
    build_rerun_scene,
    build_world_overlay_scene,
    demo_obstacles,
    demo_obstacles_world,
    log_state_to_rerun,
)


def test_build_rerun_scene_uses_dimos_map_route_and_pois(tmp_path) -> None:
    state = run_offline_simulation(out=tmp_path / "latest")

    scene = build_rerun_scene(state)

    assert scene.width_px == IMAGE_WIDTH_PX
    assert scene.height_px == IMAGE_HEIGHT_PX
    assert len(scene.image_rgb) == IMAGE_WIDTH_PX * IMAGE_HEIGHT_PX * 3
    assert len(scene.path_points) >= 2
    assert len(scene.route_points) >= 4
    assert "COOLING_1" in scene.target_labels
    assert any("TEMP_1" in label for label in scene.poi_labels)
    assert scene.robot_point is not None
    assert len(scene.robot_heading) == 2


def test_rerun_source_must_be_local_by_default() -> None:
    assert _parse_local_rerun_source("rerun+http://127.0.0.1:9877/proxy") == (
        "127.0.0.1",
        9877,
    )

    with pytest.raises(ValueError):
        _parse_local_rerun_source("http://127.0.0.1:9877/proxy")

    with pytest.raises(ValueError):
        _parse_local_rerun_source("rerun+http://10.0.0.5:9877/proxy")


def test_build_mapping_frames_grows_lidar_map(tmp_path) -> None:
    state = run_offline_simulation(out=tmp_path / "latest")

    frames = build_mapping_frames(state, max_frames=12)

    assert len(frames) == 12
    assert len(frames[0].robot_path) == 1
    assert len(frames[-1].robot_path) == 12
    assert len(frames[-1].mapped_free_points) >= len(frames[0].mapped_free_points)
    assert any(frame.lidar_rays for frame in frames)
    assert any(frame.lidar_hits for frame in frames)


def test_demo_simulation_adds_obstacles_and_camera_frames(tmp_path) -> None:
    state = run_offline_simulation(out=tmp_path / "latest")

    obstacles = demo_obstacles(state)
    camera = _poi_camera_image("TEMP_1")

    assert sum(1 for obstacle in obstacles if obstacle.kind == "cone") == 5
    assert sum(1 for obstacle in obstacles if obstacle.kind == "box") == 3
    assert any(obstacle.kind == "thermometer" for obstacle in obstacles)
    assert len(camera) == 320 * 180 * 3


class _FakeRerun:
    def __init__(self) -> None:
        self.logs: list[tuple[str, object]] = []
        self.blueprints: list[object] = []

    class Clear:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    class Points3D:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    class LineStrips3D:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    def log(self, path: str, payload: object) -> None:
        self.logs.append((path, payload))

    def send_blueprint(self, blueprint: object) -> None:
        self.blueprints.append(blueprint)


def test_native_3d_mode_logs_world_overlays_without_forcing_2d_blueprint(tmp_path) -> None:
    state = run_offline_simulation(out=tmp_path / "latest")

    scene = build_world_overlay_scene(state)
    obstacles = demo_obstacles_world(state)
    rr = _FakeRerun()
    log_state_to_rerun(rr, state, view_mode="native-3d", include_camera=False)
    paths = [path for path, _ in rr.logs]

    assert len(scene.route_points) >= 4
    assert all(len(point) == 3 for point in scene.route_points)
    assert any(obstacle.kind == "cone" for obstacle in obstacles)
    assert "world/dogops/route/plan" in paths
    assert "world/dogops/sim/objects" in paths
    assert "dogops/map/costmap" not in paths
    assert rr.blueprints == []
