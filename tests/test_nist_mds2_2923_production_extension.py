from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer import research_program_cli
from materials_data_analyzer.research_loop import autonomous_production_nist_extension
from materials_data_analyzer.research_loop import nist_mds2_2923_network_policy
from materials_data_analyzer.research_loop import nist_mds2_2923_post_acquisition_rediagnosis
from materials_data_analyzer.research_loop import nist_mds2_2923_production_acquisition


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MISSION = REPOSITORY_ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
POLICY = REPOSITORY_ROOT / "configs/research/nist_mds2_2923_network_acquisition_policy.v1.json"
FRONTIER = REPOSITORY_ROOT / "configs/research/in625_external_physical_source_frontier.v1.json"
EXPECTED_MISSION_SHA256 = (
    "44091458e8a10a6ba4ef67a47056d98e4ba1a2ac5e29695cbeba7bb79f47160f"
)
EXPECTED_POLICY_SHA256 = (
    "4b19c64f4f2c764f5315971c5afba16000763a4d307929ec5e463f42ee1cbebf"
)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")


def test_exact_mission_and_nist_policy_raw_byte_pins_match() -> None:
    assert hashlib.sha256(MISSION.read_bytes()).hexdigest() == EXPECTED_MISSION_SHA256
    assert hashlib.sha256(POLICY.read_bytes()).hexdigest() == EXPECTED_POLICY_SHA256
    assert research_program_cli._AUTONOMOUS_PRODUCTION_MISSION_SHA256 == (
        EXPECTED_MISSION_SHA256
    )


def test_exact_nist_policy_authenticates_without_network() -> None:
    result = nist_mds2_2923_network_policy.authenticate_nist_mds2_2923_network_policy(
        repository_root=REPOSITORY_ROOT,
        mission_path=MISSION,
        expected_mission_sha256=EXPECTED_MISSION_SHA256,
        policy_path=POLICY,
        frontier_path=FRONTIER,
    )
    assert result["qualification_status"] == (
        "exact_nist_mds2_2923_network_policy_authenticated"
    )
    assert result["policy_sha256"] == EXPECTED_POLICY_SHA256
    assert result["candidate_id"] == "nist-mds2-2923-cross-sectional-micrographs"
    assert result["product_id"] == "mds2-2923"
    assert result["metadata_allowed_hosts"] == ["data.nist.gov"]
    assert result["artifact_allowed_hosts"] == [
        "data.nist.gov",
        "nist-oar-cache.s3.amazonaws.com",
    ]
    assert result["network_access_performed"] is False
    assert result["paper_and_other_source_lanes_remain_allowed"] is True


def _write_reauthorized_fixture(
    tmp_path: Path,
    *,
    mutate_policy: Any,
    mutate_frontier: Any | None = None,
) -> tuple[Path, Path, Path, Path, str]:
    root = tmp_path / "repo"
    config = root / "configs/research"
    config.mkdir(parents=True)

    frontier = json.loads(FRONTIER.read_text(encoding="utf-8"))
    if mutate_frontier is not None:
        mutate_frontier(frontier)
    frontier_path = config / FRONTIER.name
    frontier_path.write_bytes(_json_bytes(frontier))

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    mutate_policy(policy)
    policy_bytes = _json_bytes(policy)
    policy_path = config / POLICY.name
    policy_path.write_bytes(policy_bytes)

    mission = json.loads(MISSION.read_text(encoding="utf-8"))
    nist_pin = next(
        item
        for item in mission["source_trust_policy_pins"]
        if item["policy_id"] == "nist-mds2-2923-network-acquisition-v1"
    )
    nist_pin["sha256"] = hashlib.sha256(policy_bytes).hexdigest()
    mission_bytes = _json_bytes(mission)
    mission_path = config / MISSION.name
    mission_path.write_bytes(mission_bytes)
    return (
        root,
        mission_path,
        policy_path,
        frontier_path,
        hashlib.sha256(mission_bytes).hexdigest(),
    )


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda policy: policy["network"]["artifact_allowed_hosts"].append(
                "example.com"
            ),
            "network authority widened or drifted",
        ),
        (
            lambda policy: policy["source_identity"].__setitem__(
                "product_id", "attacker-product"
            ),
            "source identity drifted",
        ),
        (
            lambda policy: policy.__setitem__("candidate_id", "attacker-candidate"),
            "candidate identity drifted",
        ),
        (
            lambda policy: policy["files"][0].__setitem__(
                "path", "Attacker_README.txt"
            ),
            "file bytes/size identity drifted",
        ),
    ],
)
def test_repinning_cannot_widen_intrinsic_nist_authority(
    tmp_path: Path,
    mutator: Any,
    message: str,
) -> None:
    root, mission, policy, frontier, mission_sha = _write_reauthorized_fixture(
        tmp_path,
        mutate_policy=mutator,
    )
    with pytest.raises(
        nist_mds2_2923_network_policy.NistMds22923NetworkPolicyError,
        match=message,
    ):
        nist_mds2_2923_network_policy.authenticate_nist_mds2_2923_network_policy(
            repository_root=root,
            mission_path=mission,
            expected_mission_sha256=mission_sha,
            policy_path=policy,
            frontier_path=frontier,
        )


def test_frontier_response_substitution_is_rejected_even_with_unchanged_policy(
    tmp_path: Path,
) -> None:
    def mutate_frontier(frontier: dict[str, Any]) -> None:
        candidate = next(
            item
            for item in frontier["candidates"]
            if item["candidate_id"] == "nist-mds2-2923-cross-sectional-micrographs"
        )
        candidate["responses"] = ["tensile_stress"]

    root, mission, policy, frontier, mission_sha = _write_reauthorized_fixture(
        tmp_path,
        mutate_policy=lambda policy: None,
        mutate_frontier=mutate_frontier,
    )
    with pytest.raises(
        nist_mds2_2923_network_policy.NistMds22923NetworkPolicyError,
        match="response semantics drifted",
    ):
        nist_mds2_2923_network_policy.authenticate_nist_mds2_2923_network_policy(
            repository_root=root,
            mission_path=mission,
            expected_mission_sha256=mission_sha,
            policy_path=policy,
            frontier_path=frontier,
        )


def test_tampered_network_authorization_is_rejected_before_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qualification = (
        nist_mds2_2923_network_policy.authenticate_nist_mds2_2923_network_policy(
            repository_root=REPOSITORY_ROOT,
            mission_path=MISSION,
            expected_mission_sha256=EXPECTED_MISSION_SHA256,
            policy_path=POLICY,
            frontier_path=FRONTIER,
        )
    )
    authorization = (
        nist_mds2_2923_production_acquisition.build_nist_mds2_2923_network_authorization(
            qualification
        )
    )
    authorization["artifact_allowed_hosts"] = ["example.com"]
    unsigned = dict(authorization)
    unsigned.pop("authorization_sha256")
    authorization["authorization_sha256"] = (
        nist_mds2_2923_production_acquisition._canonical_sha(unsigned)
    )
    fetch_called = False

    def forbidden_fetch(*args: object, **kwargs: object) -> object:
        nonlocal fetch_called
        fetch_called = True
        raise AssertionError("network fetch must not be reached")

    with pytest.raises(
        nist_mds2_2923_production_acquisition.NistMds22923ProductionAcquisitionError,
        match="host authority drifted",
    ):
        nist_mds2_2923_production_acquisition.execute_authorized_nist_mds2_2923_acquisition(
            authorization=authorization,
            output_root=REPOSITORY_ROOT / "outputs" / "must-not-create-nist-tamper",
            fetcher=forbidden_fetch,
        )
    assert fetch_called is False


def _verified_acquisition_receipt() -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "acquisition_status": "exact_nist_mds2_2923_source_files_acquired",
        "candidate_id": "nist-mds2-2923-cross-sectional-micrographs",
        "product_id": "mds2-2923",
        "metadata_sha256": (
            "e10b2afb0e8b5f0d3b0a015bb38ed59a285510e1bb8534fed73f2fd0b7e883b6"
        ),
        "network_requests_performed": 3,
        "all_acquisition_provenance_authenticated": True,
        "unrestricted_network_search_performed": False,
        "arbitrary_url_fetch_performed": False,
        "receipt_sha256": "a" * 64,
    }
    return receipt


def _verified_scientific_intake() -> dict[str, Any]:
    return {
        "source": {
            "product_id": "mds2-2923",
            "doi": "10.18434/mds2-2923",
            "workbook_sha256": (
                "6cd32669f5c84cdb9e90890ba40ddc5548c85b0dbb95cf038f2f6fc69da67a52"
            ),
            "readme_sha256": (
                "8b8fc00ce62915af3e0c91c138dc4d033c031d7758161fb9da0e8702fa621c39"
            ),
            "nerdm_metadata_sha256": (
                "e10b2afb0e8b5f0d3b0a015bb38ed59a285510e1bb8534fed73f2fd0b7e883b6"
            ),
        },
        "in625_inventory": {
            "measurement_row_count": 178,
            "physical_track_count": 106,
            "machine_measurement_counts": {"AMMT": 34, "EOS M270": 144},
            "machine_physical_track_counts": {"AMMT": 34, "EOS M270": 72},
            "source_track_metadata_conflict_count": 1,
        },
        "measurement_semantics": {
            "laser_power": "machine_setting_as_stated_by_README",
            "calibration_conversion_performed": False,
        },
        "issue_76": {"eligible": False, "exact_target_cells_satisfied": 0},
        "scientific_boundary": {
            "cross_machine_pooling_eligible": False,
            "predictive_modeling_eligible_from_this_audit": False,
            "scientific_status_changed": False,
        },
        "report_sha256_without_self_field": "b" * 64,
    }


def test_post_nist_rediagnosis_keeps_paper_lane_without_authority_promotion() -> None:
    result = (
        nist_mds2_2923_post_acquisition_rediagnosis.build_nist_mds2_2923_post_acquisition_rediagnosis(
            acquisition_receipt=_verified_acquisition_receipt(),
            scientific_intake=_verified_scientific_intake(),
        )
    )
    assert result["verified_new_evidence"]["measurement_row_count"] == 178
    assert result["verified_new_evidence"]["dataset_local_physical_track_count"] == 106
    assert result["verified_new_evidence"]["geometry_response_compatibility_established"] is True
    assert result["current_blocker"]["code"] == "geometry_condition_mapping_not_established"
    assert result["next_action"]["action_class"] == (
        "reviewed_geometry_condition_mapping_assessment"
    )
    assert "paper_and_supplementary_material" in result["next_action"][
        "eligible_evidence_lanes"
    ]
    assert "not silently promoted" in result["next_action"]["paper_evidence_role"]
    assert result["scientific_boundary"]["direct_target_condition_comparability_established"] is False
    assert result["scientific_boundary"]["issue_76_exact_target_cells_satisfied"] == 0
    assert result["scientific_boundary"]["scientific_status_changed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda intake: intake["issue_76"].__setitem__("eligible", True),
        lambda intake: intake["measurement_semantics"].__setitem__(
            "calibration_conversion_performed", True
        ),
        lambda intake: intake["in625_inventory"].__setitem__(
            "physical_track_count", 178
        ),
    ],
)
def test_post_nist_rediagnosis_rejects_scientific_authority_promotion(
    mutation: Any,
) -> None:
    intake = _verified_scientific_intake()
    mutation(intake)
    with pytest.raises(
        nist_mds2_2923_post_acquisition_rediagnosis.NistMds22923PostAcquisitionRediagnosisError
    ):
        nist_mds2_2923_post_acquisition_rediagnosis.build_nist_mds2_2923_post_acquisition_rediagnosis(
            acquisition_receipt=_verified_acquisition_receipt(),
            scientific_intake=intake,
        )


@pytest.mark.parametrize("max_cycles", [0, 9, True])
def test_extension_rejects_invalid_cycle_budget_before_base_or_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    max_cycles: object,
) -> None:
    base_called = False

    def forbidden_base(**kwargs: object) -> dict[str, Any]:
        nonlocal base_called
        base_called = True
        raise AssertionError("base production must not be reached")

    monkeypatch.setattr(
        autonomous_production_nist_extension,
        "run_base_autonomous_production",
        forbidden_base,
    )
    with pytest.raises(
        autonomous_production_nist_extension.AutonomousProductionNistExtensionError,
        match="max_cycles must be an integer from 1 to 8",
    ):
        autonomous_production_nist_extension.run_autonomous_production(
            repository_root=REPOSITORY_ROOT,
            mission_path=MISSION,
            expected_mission_sha256=EXPECTED_MISSION_SHA256,
            output_root=tmp_path / "out",
            max_cycles=max_cycles,  # type: ignore[arg-type]
        )
    assert base_called is False
