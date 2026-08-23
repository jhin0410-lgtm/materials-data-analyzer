from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import autonomous_production_multisource_extension
from materials_data_analyzer.research_loop import in625_geometry_condition_mapping_assessment
from materials_data_analyzer.research_loop import in625_geometry_condition_multisource_policy
from materials_data_analyzer.research_loop import in625_geometry_condition_source_acquisition


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
POLICY = ROOT / "configs/research/in625_geometry_condition_multisource_acquisition_policy.v1.json"
REGISTRY = ROOT / "configs/research/in625_geometry_condition_source_reconnaissance.v1.json"
TARGET_PROCESS = ROOT / "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
TARGET_RESPONSE = ROOT / "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv"
EXPECTED_MISSION_SHA = "0698af600f40aef88469f20e8d380851fae2a130a556fd512640493b30e2cf04"
EXPECTED_POLICY_SHA = "a2b70b96096650811671db445bd27897795f028a508608c2eb7c4a0226658652"
EXPECTED_REGISTRY_BLOB = "d117162543a8e0c01328d65acadbe482172b16dd"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode("utf-8")


def _blob_sha(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw,
        usedforsecurity=False,
    ).hexdigest()


def test_multisource_exact_raw_byte_roots_authenticate_without_network() -> None:
    assert hashlib.sha256(MISSION.read_bytes()).hexdigest() == EXPECTED_MISSION_SHA
    assert hashlib.sha256(POLICY.read_bytes()).hexdigest() == EXPECTED_POLICY_SHA
    assert _blob_sha(REGISTRY.read_bytes()) == EXPECTED_REGISTRY_BLOB
    result = in625_geometry_condition_multisource_policy.authenticate_geometry_condition_multisource_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=EXPECTED_MISSION_SHA,
        policy_path=POLICY,
        registry_path=REGISTRY,
    )
    assert result["qualification_status"] == "exact_multisource_condition_evidence_policy_authenticated"
    assert result["source_count"] == 8
    assert result["max_requests"] == 8
    assert result["network_access_performed"] is False
    assert result["paper_claims_promoted_to_row_level_authority"] is False
    assert result["metadata_or_abstract_sources_promoted_to_full_text"] is False


def _write_repinned_fixture(
    tmp_path: Path,
    *,
    mutate_registry: Any | None = None,
    mutate_policy: Any | None = None,
) -> tuple[Path, Path, Path, Path, str]:
    root = tmp_path / "repo"
    config = root / "configs/research"
    config.mkdir(parents=True)

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if mutate_registry is not None:
        mutate_registry(registry)
    registry_bytes = _json_bytes(registry)
    registry_path = config / REGISTRY.name
    registry_path.write_bytes(registry_bytes)

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy["source_registry"]["git_blob_sha1"] = _blob_sha(registry_bytes)
    if mutate_policy is not None:
        mutate_policy(policy)
    policy_bytes = _json_bytes(policy)
    policy_path = config / POLICY.name
    policy_path.write_bytes(policy_bytes)

    mission = json.loads(MISSION.read_text(encoding="utf-8"))
    pin = next(
        item
        for item in mission["source_trust_policy_pins"]
        if item["policy_id"] == in625_geometry_condition_multisource_policy.POLICY_ID
    )
    pin["sha256"] = hashlib.sha256(policy_bytes).hexdigest()
    mission_bytes = _json_bytes(mission)
    mission_path = config / MISSION.name
    mission_path.write_bytes(mission_bytes)
    return root, mission_path, policy_path, registry_path, hashlib.sha256(mission_bytes).hexdigest()


@pytest.mark.parametrize(
    "mutator",
    [
        lambda registry: registry["sources"][3].__setitem__("url", "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=999999"),
        lambda registry: registry["sources"][3].__setitem__("doi", "10.0000/forged"),
        lambda registry: registry["sources"][4]["claims_under_review"][0].__setitem__("claim_id", "forged-claim"),
        lambda registry: registry["sources"][4].__setitem__("source_class", "official_dataset"),
    ],
)
def test_registry_repinning_cannot_substitute_source_or_claim_contract(
    tmp_path: Path,
    mutator: Any,
) -> None:
    root, mission, policy, registry, mission_sha = _write_repinned_fixture(
        tmp_path,
        mutate_registry=mutator,
    )
    with pytest.raises(
        in625_geometry_condition_multisource_policy.GeometryConditionMultisourcePolicyError,
        match="source-registry binding drifted or widened",
    ):
        in625_geometry_condition_multisource_policy.authenticate_geometry_condition_multisource_policy(
            repository_root=root,
            mission_path=mission,
            expected_mission_sha256=mission_sha,
            policy_path=policy,
            registry_path=registry,
        )


def test_policy_repinning_cannot_widen_hosts_or_request_budget(tmp_path: Path) -> None:
    def mutate(policy: dict[str, Any]) -> None:
        policy["network"]["allowed_hosts"].append("example.com")
        policy["network"]["max_requests"] = 9

    root, mission, policy, registry, mission_sha = _write_repinned_fixture(
        tmp_path,
        mutate_policy=mutate,
    )
    with pytest.raises(
        in625_geometry_condition_multisource_policy.GeometryConditionMultisourcePolicyError,
        match="multi-source network authority widened or drifted",
    ):
        in625_geometry_condition_multisource_policy.authenticate_geometry_condition_multisource_policy(
            repository_root=root,
            mission_path=mission,
            expected_mission_sha256=mission_sha,
            policy_path=policy,
            registry_path=registry,
        )


def test_bad_mission_root_fails_before_any_source_network() -> None:
    with pytest.raises(
        in625_geometry_condition_multisource_policy.GeometryConditionMultisourcePolicyError,
        match="mission bytes do not match independently supplied mission SHA-256",
    ):
        in625_geometry_condition_multisource_policy.authenticate_geometry_condition_multisource_policy(
            repository_root=ROOT,
            mission_path=MISSION,
            expected_mission_sha256="0" * 64,
            policy_path=POLICY,
            registry_path=REGISTRY,
        )


def test_source_acquisition_rejects_redirect_outside_exact_hosts() -> None:
    qualification = in625_geometry_condition_multisource_policy.authenticate_geometry_condition_multisource_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=EXPECTED_MISSION_SHA,
        policy_path=POLICY,
        registry_path=REGISTRY,
    )
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def forged_fetch(*args: object, **kwargs: object) -> in625_geometry_condition_source_acquisition.FetchResult:
        return in625_geometry_condition_source_acquisition.FetchResult(
            body=b"forged",
            final_url="https://example.com/forged.pdf",
            status_code=200,
            content_type="application/pdf",
        )

    with pytest.raises(
        in625_geometry_condition_source_acquisition.GeometryConditionSourceAcquisitionError,
        match="left exact HTTPS source authority",
    ):
        in625_geometry_condition_source_acquisition.acquire_geometry_condition_sources(
            qualification=qualification,
            source_registry=registry,
            fetcher=forged_fetch,
        )


def _fake_multisource_evidence() -> dict[str, Any]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    sources: list[dict[str, Any]] = []
    for index, source in enumerate(registry["sources"]):
        sources.append(
            {
                "source_id": source["source_id"],
                "source_class": source["source_class"],
                "title": source["title"],
                "source_sha256": f"{index + 1:064x}"[-64:],
                "row_level_measurement_authority": False,
                "claims": [
                    {
                        "claim_id": claim["claim_id"],
                        "scope": claim["scope"],
                        "matched": True,
                        "match_count": 1,
                    }
                    for claim in source["claims_under_review"]
                ],
            }
        )
    return {
        "acquisition_status": "exact_multisource_condition_evidence_acquired",
        "source_count": 8,
        "all_claim_anchors_matched": True,
        "paper_claims_promoted_to_row_level_authority": False,
        "report_sha256_without_self_field": "e" * 64,
        "sources": sources,
    }


def _fake_nist_intake() -> dict[str, Any]:
    ammt_rows = [
        {
            "machine": "AMMT",
            "material": "IN625",
            "laser_power_w_machine_setting": 180.0,
            "scan_speed_mm_s_machine_setting": 800.0,
            "surface_condition_normalized": "320 grit",
        }
        for _ in range(16)
    ] + [
        {
            "machine": "AMMT",
            "material": "IN625",
            "laser_power_w_machine_setting": 195.0,
            "scan_speed_mm_s_machine_setting": 800.0,
            "surface_condition_normalized": "320 grit",
        }
        for _ in range(18)
    ]
    eos_rows = [
        {
            "machine": "EOS M270",
            "material": "IN625",
            "laser_power_w_machine_setting": 179.2,
            "scan_speed_mm_s_machine_setting": 800.0,
            "surface_condition_normalized": "Mill",
        }
        for _ in range(144)
    ]
    return {
        "in625_inventory": {
            "measurement_row_count": 178,
            "physical_track_count": 106,
        },
        "measurement_semantics": {
            "laser_power": "machine_setting_as_stated_by_README",
            "calibration_conversion_performed": False,
        },
        "issue_76": {"eligible": False, "exact_target_cells_satisfied": 0},
        "scientific_boundary": {"cross_machine_pooling_eligible": False},
        "measurements": ammt_rows + eos_rows,
    }


def test_mapping_blocks_false_equivalence_and_preserves_conflict_ledger() -> None:
    result = in625_geometry_condition_mapping_assessment.build_geometry_condition_mapping_assessment(
        nist_intake=_fake_nist_intake(),
        multisource_evidence=_fake_multisource_evidence(),
        target_process_bytes=TARGET_PROCESS.read_bytes(),
        target_response_bytes=TARGET_RESPONSE.read_bytes(),
    )
    decision = result["gate_decision"]
    assert decision["material_identity_established"] is True
    assert decision["response_compatibility_established"] is True
    assert decision["same_machine_subset_identified"] is True
    assert decision["eos_rows_excluded_from_direct_mapping"] == 144
    assert decision["directly_comparable_mds2_rows"] == 0
    assert decision["calibrated_actual_power_mapping_established"] is False
    assert decision["spot_size_mapping_established"] is False
    assert decision["protocol_equivalence_established"] is False
    assert decision["direct_numerical_validation_authorized"] is False
    assert decision["cross_machine_pooling_authorized"] is False
    assert decision["paper_claims_promoted_to_row_level_authority"] is False
    assert decision["issue_76_exact_target_cells_satisfied"] == 0
    assert result["next_action"]["action_class"] == (
        "ammt_mds2_2923_calibration_protocol_bridge_evidence_acquisition"
    )
    assert len(result["conflict_version_ledger"]) == 3
    classifications = {
        item["classification"] for item in result["conflict_version_ledger"]
    }
    assert "explicit_scoped_calibration_correction" in classifications
    assert "later_measurement_and_definition_refinement" in classifications
    assert "unresolved_cross_experiment_calibration_mapping" in classifications


def test_mapping_rejects_eos_to_ammt_or_machine_setting_to_actual_relabel() -> None:
    intake = _fake_nist_intake()
    intake["measurements"][0]["laser_power_w_machine_setting"] = 179.2
    with pytest.raises(
        in625_geometry_condition_mapping_assessment.GeometryConditionMappingAssessmentError,
        match="mds2 AMMT power/speed support drifted",
    ):
        in625_geometry_condition_mapping_assessment.build_geometry_condition_mapping_assessment(
            nist_intake=intake,
            multisource_evidence=_fake_multisource_evidence(),
            target_process_bytes=TARGET_PROCESS.read_bytes(),
            target_response_bytes=TARGET_RESPONSE.read_bytes(),
        )


def test_mapping_rejects_issue76_promotion() -> None:
    intake = _fake_nist_intake()
    intake["issue_76"] = {"eligible": True, "exact_target_cells_satisfied": 3}
    with pytest.raises(
        in625_geometry_condition_mapping_assessment.GeometryConditionMappingAssessmentError,
        match="Issue #76 was improperly promoted",
    ):
        in625_geometry_condition_mapping_assessment.build_geometry_condition_mapping_assessment(
            nist_intake=intake,
            multisource_evidence=_fake_multisource_evidence(),
            target_process_bytes=TARGET_PROCESS.read_bytes(),
            target_response_bytes=TARGET_RESPONSE.read_bytes(),
        )


def test_mapping_rejects_paper_row_authority_promotion() -> None:
    evidence = _fake_multisource_evidence()
    evidence["sources"][3]["row_level_measurement_authority"] = True
    with pytest.raises(
        in625_geometry_condition_mapping_assessment.GeometryConditionMappingAssessmentError,
        match="paper source was promoted to row-level authority",
    ):
        in625_geometry_condition_mapping_assessment.build_geometry_condition_mapping_assessment(
            nist_intake=_fake_nist_intake(),
            multisource_evidence=evidence,
            target_process_bytes=TARGET_PROCESS.read_bytes(),
            target_response_bytes=TARGET_RESPONSE.read_bytes(),
        )


@pytest.mark.parametrize("max_cycles", [0, 9, True])
def test_multisource_wrapper_rejects_invalid_cycle_budget_before_base(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    max_cycles: object,
) -> None:
    base_called = False

    def forbidden_base(**kwargs: object) -> dict[str, Any]:
        nonlocal base_called
        base_called = True
        raise AssertionError("NIST base must not be reached")

    monkeypatch.setattr(
        autonomous_production_multisource_extension,
        "run_nist_autonomous_production",
        forbidden_base,
    )
    with pytest.raises(
        autonomous_production_multisource_extension.AutonomousProductionMultisourceExtensionError,
        match="max_cycles must be an integer from 1 to 8",
    ):
        autonomous_production_multisource_extension.run_autonomous_production(
            repository_root=ROOT,
            mission_path=MISSION,
            expected_mission_sha256=EXPECTED_MISSION_SHA,
            output_root=tmp_path / "out",
            max_cycles=max_cycles,  # type: ignore[arg-type]
        )
    assert base_called is False
