from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import autonomous_production_reference_chain_extension as production_extension
from materials_data_analyzer.research_loop import capability_expansion
from materials_data_analyzer.research_loop import capability_registry
from materials_data_analyzer.research_loop import capability_resolver
from materials_data_analyzer.research_loop import mds2_2923_experiment_identity_reference_chain as graph
from materials_data_analyzer.research_loop import mds2_2923_reference_chain_capability as capability
from materials_data_analyzer.research_loop import mds2_2923_reference_chain_capability_verifier as verifier
from materials_data_analyzer.research_loop import nist_mds2_2923_reference_chain_policy as policy


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
MISSION_SHA = "98d8730a4ba1221685267ed56cd7ae75f2ce60fcfdd8f8bb426a3825986c70ea"
POLICY = ROOT / "configs/research/nist_mds2_2923_reference_chain_naderi_evidence_policy.v1.json"


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _signed(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["report_sha256_without_self_field"] = _canonical_sha(result)
    return result


def _metadata() -> bytes:
    return json.dumps(
        {
            "@id": "https://data.nist.gov/od/id/mds2-2923",
            "description": (
                "Associated publications include https://doi.org/10.1016/j.jmapro.2021.10.053 "
                "and https://doi.org/10.1007/s40192-022-00289-w."
            ),
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _intake(metadata: bytes) -> dict[str, Any]:
    spots = [50.0, 75.0, 100.0, 125.0, 150.0, 200.0, 256.0]
    measurements: list[dict[str, Any]] = []
    for index in range(18):
        measurements.append(
            {
                "machine": "AMMT",
                "laser_power_w_machine_setting": 195.0,
                "scan_speed_mm_s_machine_setting": 800.0,
                "estimated_or_measured_spot_diameter_um": spots[index % len(spots)],
            }
        )
    return _signed(
        {
            "source": {
                "product_id": "mds2-2923",
                "nerdm_metadata_sha256": hashlib.sha256(metadata).hexdigest(),
            },
            "measurement_semantics": {
                "laser_power": "machine_setting_as_stated_by_README",
                "calibration_conversion_performed": False,
            },
            "issue_76": {"eligible": False, "exact_target_cells_satisfied": 0},
            "machine_power_speed_support": [
                {
                    "machine": "AMMT",
                    "laser_power_w_machine_setting": 180.0,
                    "scan_speed_mm_s_machine_setting": 800.0,
                    "measurement_count": 16,
                    "independent_physical_track_count": 16,
                    "spot_diameter_level_count": 1,
                },
                {
                    "machine": "AMMT",
                    "laser_power_w_machine_setting": 195.0,
                    "scan_speed_mm_s_machine_setting": 800.0,
                    "measurement_count": 18,
                    "independent_physical_track_count": 18,
                    "spot_diameter_level_count": 7,
                },
            ],
            "measurements": measurements,
        }
    )


def _naderi() -> dict[str, Any]:
    claim_ids = [
        "naderi-ammt-in625-weaver-detail-reference",
        "naderi-reference-7-weaver-spot-size-paper",
        "naderi-reference-31-ammt-design",
        "naderi-reference-32-lane-in625-protocol",
    ]
    return _signed(
        {
            "acquisition_status": "exact_naderi_reference_chain_evidence_acquired",
            "all_claims_matched": True,
            "scientific_status_changed": False,
            "claims": [
                {"claim_id": claim_id, "matched": True, "match_count": 1}
                for claim_id in claim_ids
            ],
        }
    )


def _multisource() -> dict[str, Any]:
    return _signed(
        {
            "sources": [
                {
                    "source_id": "weaver-2021-spot-size-scaling-metadata",
                    "source_class": "primary_paper_metadata",
                    "doi": "10.1016/j.jmapro.2021.10.053",
                },
                {
                    "source_id": "lane-2020-melt-pool-geometry",
                    "source_class": "primary_paper",
                    "doi": "10.1007/s40192-020-00169-1",
                },
            ]
        }
    )


def _discovery() -> dict[str, Any]:
    return _signed(
        {
            "candidates": [
                {
                    "candidate_id": "weaver",
                    "rank": 8,
                    "url": "https://doi.org/10.1016/j.jmapro.2021.10.053",
                    "link_label": "Laser spot size and scaling laws for laser beam additive manufacturing",
                    "acquisition_authorized": False,
                },
                {
                    "candidate_id": "ammt-design",
                    "rank": 12,
                    "url": (
                        "https://www.nist.gov/publications/"
                        "design-developments-and-results-nist-additive-manufacturing-metrology-testbed-ammt"
                    ),
                    "link_label": "Design, Developments, and Results from the NIST AMMT",
                    "acquisition_authorized": False,
                },
            ]
        }
    )


def _calibration() -> dict[str, Any]:
    return _signed(
        {
            "experiment_specific_bridge": {"bridge_established": False},
            "evidence_scope": {
                "digital_camera_in_situ_calibration_methodology_established": True
            },
        }
    )


def _build() -> dict[str, Any]:
    metadata = _metadata()
    return graph.build_mds2_2923_experiment_identity_reference_chain(
        nerdm_metadata_bytes=metadata,
        nist_intake=_intake(metadata),
        naderi_reference_evidence=_naderi(),
        multisource_evidence=_multisource(),
        source_discovery_report=_discovery(),
        calibration_candidate_assessment=_calibration(),
    )


def _reference_spec() -> dict[str, Any]:
    gap = capability_expansion.build_capability_gap(
        requested_action={
            "action_class": capability.ACTION_CLASS,
            "objective": "Build the exact mds2 reference graph.",
            "eligible_evidence_lanes": ["paper_and_supplementary_material"],
        },
        predecessor_report={"report_sha256_without_self_field": "a" * 64},
        available_action_classes=[],
    )
    return capability_expansion.build_capability_specification(gap)


def _candidate(spec: dict[str, Any]) -> dict[str, Any]:
    return capability_registry.build_capability_candidate(
        capability_specification=spec,
        factory_id=capability.FACTORY_ID,
        implementation_id=capability.IMPLEMENTATION_ID,
        mechanism=capability.MECHANISM,
        required_verified_primitives=capability.REQUIRED_VERIFIED_PRIMITIVES,
    )


def _verification_context(metadata: bytes) -> dict[str, Any]:
    return {
        "nerdm_metadata_bytes": metadata,
        "nist_intake": _intake(metadata),
        "multisource_evidence": _multisource(),
        "source_discovery_report": _discovery(),
        "calibration_candidate_assessment": _calibration(),
    }


def test_exact_reference_policy_authenticates_without_network() -> None:
    assert hashlib.sha256(MISSION.read_bytes()).hexdigest() == MISSION_SHA
    result = policy.authenticate_nist_mds2_2923_reference_chain_policy(
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
        policy_path=POLICY,
    )
    assert result["qualification_status"] == (
        "exact_nist_mds2_2923_reference_chain_policy_authenticated"
    )
    assert result["network_access_performed"] is False
    assert result["max_requests"] == 1
    assert result["allowed_hosts"] == ["tsapps.nist.gov"]


def test_reference_graph_is_deterministic_and_non_transitive() -> None:
    first = _build()
    second = _build()
    assert first["report_sha256_without_self_field"] == second[
        "report_sha256_without_self_field"
    ]
    assert first["reference_graph"]["edges_sha256"] == second["reference_graph"][
        "edges_sha256"
    ]
    identity = first["experiment_identity"]
    gate = first["calibration_and_protocol_gate"]
    assert identity["dataset_to_weaver_association_established"] is True
    assert identity["naderi_to_weaver_experiment_detail_reference_established"] is True
    assert identity["exact_mds2_rows_to_weaver_experiment_established"] is False
    assert identity["exact_mds2_experiment_identity_established"] is False
    assert gate["machine_setting_to_calibrated_power_relation_established"] is False
    assert gate["protocol_equivalence_established"] is False
    assert gate["directly_comparable_mds2_rows"] == 0
    assert gate["direct_numerical_cross_source_validation_authorized"] is False
    assert gate["issue_76_exact_target_cells_satisfied"] == 0
    assert first["next_action"]["action_class"] == (
        "weaver_2021_spot_size_full_text_derived_acquisition"
    )
    assert first["next_action"]["automatic_acquisition_authorized"] is False


def test_reference_graph_rejects_metadata_substitution() -> None:
    metadata = _metadata()
    intake = _intake(metadata)
    tampered = metadata + b" "
    with pytest.raises(
        graph.Mds22923ExperimentIdentityReferenceChainError,
        match="metadata bytes do not match scientific intake",
    ):
        graph.build_mds2_2923_experiment_identity_reference_chain(
            nerdm_metadata_bytes=tampered,
            nist_intake=intake,
            naderi_reference_evidence=_naderi(),
            multisource_evidence=_multisource(),
            source_discovery_report=_discovery(),
            calibration_candidate_assessment=_calibration(),
        )


def test_reference_graph_rejects_missing_explicit_reference_claim() -> None:
    naderi = _naderi()
    naderi["claims"].pop()
    naderi.pop("report_sha256_without_self_field")
    naderi["report_sha256_without_self_field"] = _canonical_sha(naderi)
    metadata = _metadata()
    with pytest.raises(
        graph.Mds22923ExperimentIdentityReferenceChainError,
        match="reference-chain claims are incomplete",
    ):
        graph.build_mds2_2923_experiment_identity_reference_chain(
            nerdm_metadata_bytes=metadata,
            nist_intake=_intake(metadata),
            naderi_reference_evidence=naderi,
            multisource_evidence=_multisource(),
            source_discovery_report=_discovery(),
            calibration_candidate_assessment=_calibration(),
        )


def test_resolver_discovers_reference_candidate_only_from_verified_primitives() -> None:
    spec = _reference_spec()
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=[]
    )
    result = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=spec,
        available_verified_primitives=capability.REQUIRED_VERIFIED_PRIMITIVES,
    )
    assert result["resolution_status"] == "bounded_candidate_discovered"
    assert result["factory_id"] == capability.FACTORY_ID
    assert result["candidate"]["network_authority_granted"] is False
    assert result["candidate"]["execution_authority_granted"] is False

    missing = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=spec,
        available_verified_primitives=capability.REQUIRED_VERIFIED_PRIMITIVES[:-1],
    )
    assert missing["resolution_status"] == "no_bounded_candidate_available"


def test_cycle11_reauthenticates_exact_predecessor_candidate_without_rediscovery() -> None:
    spec = _reference_spec()
    candidate = _candidate(spec)
    resolution = {
        "resolution_status": "bounded_candidate_discovered",
        "candidate": candidate,
    }
    receipt = production_extension._authenticate_predecessor_candidate(
        predecessor_resolution=resolution,
        predecessor_candidate=candidate,
        capability_specification=spec,
        predecessor_manifest_sha256="b" * 64,
    )
    assert receipt["resolution_status"] == "predecessor_candidate_reauthenticated"
    assert receipt["capability_candidate_sha256"] == candidate[
        "capability_candidate_sha256_without_self_field"
    ]
    assert receipt["candidate_rediscovery_performed"] is False
    assert receipt["unrestricted_discovery_performed"] is False
    assert receipt["network_authority_granted"] is False
    assert receipt["execution_authority_granted"] is False


def test_cycle11_rejects_rehashed_predecessor_candidate_authority_escalation() -> None:
    spec = _reference_spec()
    candidate = _candidate(spec)
    candidate["network_authority_granted"] = True
    candidate.pop("capability_candidate_sha256_without_self_field")
    candidate["capability_candidate_sha256_without_self_field"] = _canonical_sha(candidate)
    resolution = {
        "resolution_status": "bounded_candidate_discovered",
        "candidate": candidate,
    }
    with pytest.raises(
        production_extension.AutonomousProductionReferenceChainExtensionError,
        match="attempted to acquire authority",
    ):
        production_extension._authenticate_predecessor_candidate(
            predecessor_resolution=resolution,
            predecessor_candidate=candidate,
            capability_specification=spec,
            predecessor_manifest_sha256="b" * 64,
        )


def test_repinned_semantically_weakened_spec_cannot_pass_independent_verifier() -> None:
    spec = _reference_spec()
    weakened = dict(spec)
    weakened["scientific_acceptance"] = list(spec["scientific_acceptance"])
    weakened["scientific_acceptance"][0] = (
        "A dataset-publication association may be treated as exact row identity."
    )
    weakened.pop("capability_specification_sha256_without_self_field")
    weakened["capability_specification_sha256_without_self_field"] = _canonical_sha(
        weakened
    )
    candidate = _candidate(weakened)
    metadata = _metadata()
    receipt = verifier.verify_reference_chain_capability_candidate(
        capability_specification=weakened,
        candidate=candidate,
        available_verified_primitives=capability.REQUIRED_VERIFIED_PRIMITIVES,
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
        verification_context=_verification_context(metadata),
        perform_real_source_smoke=False,
    )
    assert receipt["semantic_spec_contract_verified"] is False
    assert receipt["verification_results"]["deterministic_contract_tests"] is False
    assert receipt["promotion_eligible"] is False


def test_no_real_source_smoke_cannot_promote_reference_candidate() -> None:
    metadata = _metadata()
    spec = _reference_spec()
    candidate = _candidate(spec)
    receipt = verifier.verify_reference_chain_capability_candidate(
        capability_specification=spec,
        candidate=candidate,
        available_verified_primitives=capability.REQUIRED_VERIFIED_PRIMITIVES,
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
        verification_context=_verification_context(metadata),
        perform_real_source_smoke=False,
    )
    assert receipt["semantic_spec_contract_verified"] is True
    assert receipt["promotion_eligible"] is False
    assert receipt["verification_results"][
        "real_source_smoke_test_when_network_evidence_is_required"
    ] is False
