from __future__ import annotations

import json
from pathlib import Path

FRONTIER = Path("configs/research/in625_external_physical_source_frontier.v1.json")


def _frontier() -> dict[str, object]:
    return json.loads(FRONTIER.read_text(encoding="utf-8"))


def test_frontier_is_discovery_only_and_never_issue_76_eligible() -> None:
    frontier = _frontier()
    candidates = frontier["candidates"]

    assert frontier["schema_version"] == "1.0"
    assert frontier["frontier_id"] == "in625-external-physical-source-frontier-v1"
    ids = [candidate["candidate_id"] for candidate in candidates]
    assert len(ids) == len(set(ids))
    assert all(candidate["issue_76_eligible"] is False for candidate in candidates)


def test_m3c37q_retains_eos_identity_and_does_not_infer_ammt_power() -> None:
    candidate = next(
        item
        for item in _frontier()["candidates"]
        if item["candidate_id"] == "nist-m3c37q-commercial-lpbf-thermography"
    )
    assert candidate["machine"] == "commercial EOS M270 LPBF system"
    assert candidate["verified_process_support"] == [
        {
            "source_file": "20170215_PowderPlate6_Bare_SingleLine_195W_800mmPs.zip",
            "laser_power_w": 195.0,
            "scan_speed_mm_s": 800.0,
            "material_state": "bare_plate_single_track",
        }
    ]
    assert 179.2 not in {
        point["laser_power_w"] for point in candidate["verified_process_support"]
    }


def test_amb2018_cbm_frontier_never_relabels_cbm_as_ammt() -> None:
    candidate = next(
        item
        for item in _frontier()["candidates"]
        if item["candidate_id"] == "nist-m31931-amb2018-02-cbm-thermography"
    )
    assert "commercial build machine" in candidate["machine"]
    assert {
        (point["laser_power_w"], point["scan_speed_mm_s"])
        for point in candidate["verified_process_support"]
    } == {(150.0, 400.0), (195.0, 800.0), (195.0, 1200.0)}
    assert all(
        point["power_semantics"] == "CBM expected power"
        for point in candidate["verified_process_support"]
    )


def test_lee_parameter_levels_are_not_misrepresented_as_process_rows() -> None:
    candidate = next(
        item
        for item in _frontier()["candidates"]
        if item["candidate_id"] == "lee-peng-shin-choi-2019-alloy625-m2"
    )
    assert candidate["alloy625_dataset_count"] == 175
    assert "verified_parameter_levels" in candidate
    assert "process_points" not in candidate
    assert any(
        "Do not assume" in requirement
        for requirement in candidate["promotion_requirements"]
    )


def test_ammt_image_lead_cannot_become_geometry_evidence_by_discovery() -> None:
    candidate = next(
        item
        for item in _frontier()["candidates"]
        if item["candidate_id"] == "emmanuel-yang-yeung-zhang-2026-ammt-images"
    )
    assert candidate["reported_image_count"] == 1200
    assert candidate["acquisition_status"].endswith("unresolved")
    assert candidate["issue_76_eligible"] is False
