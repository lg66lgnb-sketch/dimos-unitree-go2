from types import SimpleNamespace

from dimos.experimental.dogops.dashboard_static import map_svg
from dimos.experimental.dogops.live_map import update_site_map_from_dimos_streams
from dimos.experimental.dogops.mapping import decode_dimos_costmap_full, encode_dimos_costmap_full
from dimos.experimental.dogops.mission_engine import run_offline_simulation


def test_site_map_keeps_websocket_payload_as_dashboard_contract(tmp_path) -> None:
    state = run_offline_simulation(out=tmp_path / "latest")

    costmap = state.site_map.dimos_costmap
    path = state.site_map.dimos_path
    assert costmap is not None
    assert path is not None
    assert costmap["type"] == "costmap"
    assert costmap["origin"]["type"] == "vector"
    assert costmap["resolution"] == state.site_map.resolution_m
    assert costmap["origin_theta"] == 0
    assert costmap["grid"]["update_type"] == "full"
    assert costmap["grid"]["compressed"] is True
    assert costmap["grid"]["compression"] == "zlib"
    assert "websocket_vis" in costmap["source_module"]
    assert path["type"] == "path"
    assert path["points"]
    assert "websocket_vis" in path["source_module"]

    decoded = decode_dimos_costmap_full(costmap["grid"])
    assert len(decoded) == costmap["grid"]["shape"][0]
    assert len(decoded[0]) == costmap["grid"]["shape"][1]
    assert any(value == 0 for row in decoded for value in row)
    assert any(value == 100 for row in decoded for value in row)


def test_live_map_bridge_consumes_dimos_costmap_path_and_odom(tmp_path) -> None:
    state = run_offline_simulation(out=tmp_path / "latest")
    costmap = SimpleNamespace(
        frame_id="world",
        grid=[[-1, 0, 100], [0, 50, -1]],
        resolution=0.25,
        origin=SimpleNamespace(position=SimpleNamespace(x=-1.0, y=2.0)),
    )
    path = SimpleNamespace(
        poses=[
            SimpleNamespace(
                frame_id="world",
                position=[-1.0, 2.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
            ),
            SimpleNamespace(
                frame_id="world",
                position=SimpleNamespace(x=-0.5, y=2.25),
                orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
            ),
        ]
    )
    odom = SimpleNamespace(
        frame_id="world",
        position=[-0.5, 2.25, 0.0],
        orientation=[0.0, 0.0, 0.0, 1.0],
    )

    site_map = update_site_map_from_dimos_streams(
        state.site_map,
        global_costmap=costmap,
        path=path,
        odom=odom,
    )

    assert site_map.source == "dimos_live"
    assert site_map.resolution_m == 0.25
    assert site_map.width_m == 0.75
    assert site_map.height_m == 0.5
    assert site_map.coverage_ratio == 4 / 6
    assert site_map.cell_stats["free"] == 2
    assert site_map.cell_stats["occupied"] == 2
    assert site_map.dimos_costmap is not None
    assert "CostMapper.global_costmap" in site_map.dimos_costmap["source_module"]
    assert site_map.dimos_costmap["grid"]["update_type"] == "full"
    assert decode_dimos_costmap_full(site_map.dimos_costmap["grid"])[1][1] == 50
    assert site_map.dimos_path is not None
    assert site_map.dimos_path["points"] == [[-1.0, 2.0], [-0.5, 2.25]]
    assert site_map.robot_pose is not None
    assert site_map.robot_pose.x == -0.5


def test_dashboard_map_svg_renders_dimos_payload_without_dogops_cells() -> None:
    site_map = {
        "status": "mapped",
        "coverage_ratio": 1.0,
        "dimos_schema": "dimos.web.websocket_vis.v1",
        "dimos_costmap": {
            "type": "costmap",
            "grid": encode_dimos_costmap_full([[0, 100], [-1, 0]]),
            "origin": {"type": "vector", "c": [-1.0, 2.0, 0]},
            "resolution": 0.25,
            "origin_theta": 0,
        },
        "dimos_path": {"type": "path", "points": [[-1.0, 2.0], [-0.75, 2.25]]},
        "robot_pose": {"x": -0.75, "y": 2.25, "theta_deg": 0.0},
        "cells": [],
        "features": [],
        "explored_path": [],
        "origin": {"x": 99.0, "y": 99.0},
        "width_m": 99.0,
        "height_m": 99.0,
        "resolution_m": 99.0,
    }

    svg = map_svg(site_map, {"waypoints": [], "points_of_interest": []})

    assert "dimos.web.websocket_vis.v1" in svg
    assert "#dbeafe" in svg
    assert "#fecaca" in svg
    assert "#f1f5f9" in svg
    assert "dog" in svg
    assert "<polyline" in svg
