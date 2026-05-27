from __future__ import annotations

import subprocess
import sys


def test_cli_validate_and_simulate(tmp_path) -> None:
    validate = subprocess.run(
        [sys.executable, "-m", "dimos.experimental.dogops.cli", "validate"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "validated site=dogops_demo_site" in validate.stdout

    rerun_help = subprocess.run(
        [sys.executable, "-m", "dimos.experimental.dogops.cli", "rerun-sim", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "rerun-sim" in rerun_help.stdout
    assert "--source-url" in rerun_help.stdout
    assert "--view-mode" in rerun_help.stdout

    operator_run_dir = tmp_path / "operator"
    start = subprocess.run(
        [
            sys.executable,
            "-m",
            "dimos.experimental.dogops.cli",
            "start",
            "--out",
            str(operator_run_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "state=running" in start.stdout
    assert (operator_run_dir / "dashboard.html").is_file()
    assert (operator_run_dir / "map.json").is_file()
    assert (operator_run_dir / "route_plan.json").is_file()

    run_dir = tmp_path / "latest"
    simulate = subprocess.run(
        [
            sys.executable,
            "-m",
            "dimos.experimental.dogops.cli",
            "simulate",
            "--out",
            str(run_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "state=done" in simulate.stdout
    assert (run_dir / "report.md").is_file()
    assert "PKG-104 wrong zone and blocking COOLING_1" in (run_dir / "report.md").read_text(
        encoding="utf-8"
    )

    refresh_map = subprocess.run(
        [
            sys.executable,
            "-m",
            "dimos.experimental.dogops.cli",
            "map",
            "--run",
            str(run_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "coverage=" in refresh_map.stdout

    edit_plan = subprocess.run(
        [
            sys.executable,
            "-m",
            "dimos.experimental.dogops.cli",
            "plan",
            "--run",
            str(run_dir),
            "--add-waypoint",
            "NO_GO_1",
            "--add-poi",
            "TEMP_1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "points_of_interest=" in edit_plan.stdout

    run_plan = subprocess.run(
        [
            sys.executable,
            "-m",
            "dimos.experimental.dogops.cli",
            "run-plan",
            "--run",
            str(run_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "captures=" in run_plan.stdout

    assert (run_dir / "route_plan.json").is_file()
    assert (run_dir / "map.json").is_file()
