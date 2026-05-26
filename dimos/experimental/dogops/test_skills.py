from __future__ import annotations

import json

from dimos.experimental.dogops.skills import DogOpsSkillContainer


def _payload(raw: str) -> dict[str, object]:
    return json.loads(raw)


def test_skill_container_runs_closed_loop_and_reports_state(tmp_path) -> None:
    skills = DogOpsSkillContainer(run_dir=tmp_path / "latest")

    assert _payload(skills.load_site_config())["packages"] == 4
    assert _payload(skills.load_manifest())["packages"] == 4
    assert _payload(skills.load_mission())["mission_id"] == "receiving_sre_demo"

    run = _payload(skills.run_mission())
    assert run["ok"] is True
    assert run["state"] == "done"

    scan = _payload(skills.scan_zone("INBOUND_DOCK"))
    assert scan["visible_tag_ids"] == [20, 101, 102]

    manifest_scan = _payload(skills.scan_receiving_manifest("INBOUND_DOCK"))
    assert manifest_scan["status"] == "mismatch"
    assert manifest_scan["missing_packages"] == ["PKG-103"]
    assert manifest_scan["detected_packages"] == ["PKG-101", "PKG-102"]

    asset = _payload(skills.inspect_asset("COOLING_1"))
    assert asset["ok"] is True
    assert asset["expected_clear"] is True

    gauge = _payload(skills.read_gauge("TEMP_1"))
    assert gauge["status"] == "normal"
    assert gauge["unit"] == "celsius"

    clearance = _payload(skills.check_clearance("COOLING_1"))
    assert clearance["status"] == "clear"

    aisle = _payload(skills.detect_blocked_aisle("RACK_ROW_A"))
    assert aisle["blocked"] is False

    reconciliation = _payload(skills.reconcile_manifest())
    assert reconciliation["manifest_exceptions"] == 2

    changes = _payload(skills.what_changed())
    assert "PKG-104 moved" in str(changes["changes"])

    nav = _payload(skills.nav_eval_report())
    assert nav["nav_summary"]["waypoints_reached"] == 4  # type: ignore[index]


def test_skill_container_work_order_methods_are_idempotent(tmp_path) -> None:
    skills = DogOpsSkillContainer(run_dir=tmp_path / "latest")
    skills.run_mission()

    existing = _payload(skills.open_work_order("COOLING_1", "blocked_cooling"))
    assert existing["incident_id"] == "INC-001"
    assert existing["work_order_id"] == "WO-001"

    ready = _payload(skills.mark_ready_to_verify("WO-001"))
    assert ready["ok"] is True

    verified = _payload(skills.verify_work_order("WO-001"))
    assert verified["state"] == "verified_closed"


def test_skill_container_stretch_skills_are_simulated_without_cloud_keys(tmp_path) -> None:
    skills = DogOpsSkillContainer(run_dir=tmp_path / "latest")

    dock = _payload(skills.dock_align())
    assert dock["ok"] is True
    assert dock["simulated"] is True

    portal = _payload(skills.portal_entry())
    assert portal["ok"] is True
    assert portal["door_open"] is True

    stopped = _payload(skills.stop_mission())
    assert stopped["state"] == "not_started"
