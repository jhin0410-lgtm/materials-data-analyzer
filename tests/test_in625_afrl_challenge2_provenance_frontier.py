from __future__ import annotations

import json
from pathlib import Path

FRONTIER = Path(
    "configs/research/in625_afrl_challenge2_provenance_frontier.v1.json"
)


def _frontier() -> dict[str, object]:
    return json.loads(FRONTIER.read_text(encoding="utf-8"))


def test_afrl_challenge2_identity_and_scope_are_exact() -> None:
    frontier = _frontier()
    authority = frontier["authority"]
    claims = frontier["verified_discovery_claims"]

    assert frontier["schema_version"] == "1.0"
    assert frontier["candidate_id"] == "afrl-mdf-m27h1z-challenge2-in625"
    assert authority["doi"] == "10.18126/M27H1Z"
    assert authority["source_name"] == "groebermichael_afrl_am_package2"
    assert authority["associated_descriptor_doi"] == "10.1007/s40192-021-00220-9"
    assert claims["material"] == "IN625"
    assert claims["process_family"] == "laser powder bed fusion"
    assert claims["machine"] == "EOS M280"
    assert claims["challenge_role"] == "microscale process-to-structure"


def test_frontier_does_not_fabricate_raw_acquisition_or_scientific_promotion() -> None:
    frontier = _frontier()
    acquisition = frontier["acquisition"]
    boundaries = frontier["scientific_boundaries"]

    assert acquisition["repository_record_publicly_resolved"] is True
    assert acquisition["raw_bytes_acquired_in_repository"] is False
    assert acquisition["raw_bytes_authenticated"] is False
    assert acquisition["raw_file_inventory_available"] is False
    assert acquisition["repository_published_checksum_contract_verified"] is False
    assert acquisition["raw_package_transfer_route"] == "Globus"
    assert "requires_authorized_globus_session" in acquisition["status"]
    assert any(
        "Join the AFRL Additive Manufacturing Modeling Challenge Series Globus group."
        == instruction
        for instruction in acquisition["current_access_instructions"]
    )

    assert boundaries["discovery_is_acquisition"] is False
    assert boundaries["repository_metadata_is_row_level_measurement_evidence"] is False
    assert boundaries["frontier_entry_is_registry_promotion"] is False
    assert boundaries["issue_76_eligible"] is False
    assert boundaries["scientific_status_changed"] is False


def test_official_q_and_a_constraints_preserve_measurement_semantics() -> None:
    frontier = _frontier()
    qa = frontier["verified_challenge_q_and_a_constraints"]

    assert qa["programmed_build_plate_preheat_c"] == 80.0
    assert qa["build_atmosphere"] == "argon"
    assert qa["laser_spot_size_measurement_status"] == "not_directly_measured_for_these_builds"
    assert qa["manufacturer_nominal_gaussian_laser_spot_diameter_4sigma_mm"] == 0.1
    assert frontier["scientific_boundaries"][
        "manufacturer_nominal_spot_size_is_direct_measurement"
    ] is False
    assert qa["B21_semantics"] == "single track wall, 10 layers tall"
    assert qa["B27_semantics"] == "2D pad, multiple tracks in one layer"
    assert qa["layer_timing_authority_file"] == "HomeIn_Build B.csv"
    assert qa["substrate_geometry_authority_file"] == "Build B- All Parts.stl"


def test_candidate_authority_artifacts_and_regime_boundaries_are_retained() -> None:
    frontier = _frontier()
    artifacts = set(frontier["candidate_authority_files_or_artifacts"])
    forms = set(frontier["verified_discovery_claims"]["physical_experiment_forms"])

    assert {
        "Challenge2ProblemStatement_2019Release.pdf",
        "HomeIn_Build B.csv",
        "Build B- All Parts.stl",
        "B21.cli",
        "B27.cli",
        "Challenge 2 Answer Template.xls",
    } <= artifacts
    assert forms == {
        "single_track",
        "single_layer_multi_track_pad",
        "multi_layer_single_track_wall",
    }
    assert any(
        "Preserve single-track, single-layer multi-track and multi-layer wall records"
        in item
        for item in frontier["promotion_plan"]
    )


def test_fallbacks_are_explicitly_non_equivalent_to_lpbf_melt_pool_evidence() -> None:
    fallbacks = _frontier()["fallback_candidates_if_transfer_blocked"]

    assert [item["priority"] for item in fallbacks] == [1, 2]
    assert fallbacks[0]["doi"] == "10.17632/xr3tvpjwfm.2"
    assert "scientifically distinct" in fallbacks[0]["reason"]
    assert "LPBF pooling" in fallbacks[0]["reason"]
    assert fallbacks[1]["doi"] == "10.17632/ybyhxv4czd.3"
    assert "not LPBF melt-pool comparability" in fallbacks[1]["reason"]
