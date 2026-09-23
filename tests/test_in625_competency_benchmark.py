from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop.comparability_engine import (
    AuthenticatedEvidenceInput,
    DEFAULT_RULE_REGISTRY,
)
from materials_data_analyzer.research_loop.evidence_packet import (
    canonical_sha256,
    finalize_evidence_packet,
)
from materials_data_analyzer.research_loop.evidence_packet_adapters import (
    build_nist_ambench_trace_validation_material,
)
from materials_data_analyzer.research_loop.in625_competency_benchmark import (
    In625CompetencyBenchmarkError,
    build_in625_competency_bootstrap,
    build_in625_competency_iteration,
)


ROOT = Path(__file__).resolve().parents[1]


def _attribute(
    name: str,
    value: object,
    *,
    source_binding_ids: list[str],
    unit: str | None = None,
) -> dict[str, Any]:
    if isinstance(value, int) and not isinstance(value, bool):
        value_type = "integer"
    elif isinstance(value, float):
        value_type = "number"
    else:
        value_type = "text"
    return {
        "name": name,
        "value": value,
        "value_type": value_type,
        "unit_state": "specified" if unit is not None else "not_applicable",
        "unit": unit,
        "source_binding_ids": source_binding_ids,
    }


def _synthetic_mds2_input() -> AuthenticatedEvidenceInput:
    """Contract fixture only; never used as scientific evidence for the benchmark."""

    workbook = b"synthetic-contract-workbook"
    readme = b"195 W and 800 mm/s are machine settings"
    metadata = b'{"@id":"synthetic-mds2-contract"}'
    bindings = [
        {
            "binding_id": "workbook",
            "role": "row_level_data_sheet",
            "artifact_id": "synthetic-workbook",
            "locator": "fixture/workbook.xlsx",
            "sha256": hashlib.sha256(workbook).hexdigest(),
            "byte_size": len(workbook),
            "media_type": "application/octet-stream",
        },
        {
            "binding_id": "readme",
            "role": "measurement_semantics",
            "artifact_id": "synthetic-readme",
            "locator": "fixture/README.txt",
            "sha256": hashlib.sha256(readme).hexdigest(),
            "byte_size": len(readme),
            "media_type": "text/plain",
        },
        {
            "binding_id": "metadata",
            "role": "repository_metadata",
            "artifact_id": "synthetic-metadata",
            "locator": "fixture/metadata.json",
            "sha256": hashlib.sha256(metadata).hexdigest(),
            "byte_size": len(metadata),
            "media_type": "application/json",
        },
    ]
    packet = finalize_evidence_packet(
        {
            "schema_version": "1.0",
            "packet_type": "evidence_packet",
            "evidence_id": "fixture:mds2-2923:ammt-195-800",
            "evidence_kind": "measurement",
            "provider": {
                "provider_id": "fixture-mds2-row-provider",
                "contract_version": "1.0",
                "schema_version": "1.0",
                "adapter_id": "fixture-only",
            },
            "subject": {
                "subject_type": "material_process_cross_section_measurement",
                "identities": [
                    {"namespace": "material", "value": "IN625", "role": "material"},
                    {
                        "namespace": "mds2_physical_track_id",
                        "value": "fixture-track-1",
                        "role": "sample",
                    },
                ],
                "material_scope": "synthetic contract fixture only",
                "description": "Not scientific evidence; planner/comparability regression fixture.",
            },
            "contexts": {
                "process": {
                    "status": "applicable",
                    "attributes": [
                        _attribute(
                            "process_route",
                            "NIST AMMT bare-substrate laser track experiment",
                            source_binding_ids=["readme"],
                        ),
                        _attribute(
                            "laser_power_machine_setting",
                            195.0,
                            unit="W",
                            source_binding_ids=["workbook", "readme"],
                        ),
                        _attribute(
                            "scan_speed_machine_setting",
                            800.0,
                            unit="mm/s",
                            source_binding_ids=["workbook", "readme"],
                        ),
                        _attribute(
                            "spot_diameter_D4sigma",
                            100.0,
                            unit="um",
                            source_binding_ids=["workbook", "readme"],
                        ),
                    ],
                },
                "sample": {
                    "status": "applicable",
                    "attributes": [
                        _attribute(
                            "physical_track_id",
                            "fixture-track-1",
                            source_binding_ids=["workbook"],
                        )
                    ],
                },
                "method": {
                    "status": "applicable",
                    "attributes": [
                        _attribute(
                            "method",
                            "optical cross-section",
                            source_binding_ids=["readme"],
                        )
                    ],
                },
                "measurement": {
                    "status": "applicable",
                    "attributes": [
                        _attribute(
                            "reference_convention",
                            "melt-pool transverse width/depth geometry",
                            source_binding_ids=["readme"],
                        )
                    ],
                },
            },
            "results": [
                {
                    "result_id": "width",
                    "result_kind": "melt_pool_width",
                    "value_state": "observed",
                    "value": 120.0,
                    "value_type": "number",
                    "unit_state": "specified",
                    "unit": "um",
                    "source_binding_ids": ["workbook"],
                    "derivation_ids": [],
                    "uncertainty_ids": ["row-uncertainty"],
                    "qualifiers": ["fixture-only"],
                },
                {
                    "result_id": "depth",
                    "result_kind": "melt_pool_depth",
                    "value_state": "observed",
                    "value": 55.0,
                    "value_type": "number",
                    "unit_state": "specified",
                    "unit": "um",
                    "source_binding_ids": ["workbook"],
                    "derivation_ids": [],
                    "uncertainty_ids": ["row-uncertainty"],
                    "qualifiers": ["fixture-only"],
                },
            ],
            "uncertainty": [
                {
                    "uncertainty_id": "row-uncertainty",
                    "status": "unknown",
                    "kind": "row_specific_measurement_uncertainty",
                    "value": None,
                    "unit": None,
                    "distribution": None,
                    "confidence_level": None,
                    "source_binding_ids": ["workbook", "readme"],
                    "notes": "Fixture preserves unknown row uncertainty.",
                }
            ],
            "calibration": {"status": "unknown", "records": []},
            "source_bindings": bindings,
            "derivation_lineage": [],
            "independence": {
                "source_family_id": "fixture-mds2",
                "dataset_parent_id": "fixture-mds2",
                "sample_parent_ids": ["fixture-track-1"],
                "acquisition_parent_ids": ["fixture-track-1"],
                "development_family_id": None,
                "overlap_status": "unknown",
                "overlap_with": [],
                "independence_claim_status": "not_assessed",
            },
            "scientific_validity": {
                "domain_verifier_id": "fixture-only",
                "verification_status": "limited",
                "validated_scope": ["contract-shape regression only"],
                "excluded_scope": ["all scientific claims"],
                "assumptions": [],
                "scientific_status_promoted": False,
            },
            "comparability": {
                "status": "not_assessed",
                "requirements": ["generic comparability assessment required"],
                "limitations": ["fixture only"],
                "comparison_performed": False,
                "comparable_claimed": False,
            },
            "limitations": ["This object is not scientific evidence."],
            "authority": {
                "empirical_evidence_created": True,
                "scientific_status_promoted": False,
                "downstream_use_authorized": False,
                "planning_metadata_only": False,
                "row_level_measurement_authority": True,
                "authority_source": "domain_verifier",
            },
        }
    )
    expected = {
        "provider_id": "fixture-mds2-row-provider",
        "subject_identities": copy.deepcopy(packet["subject"]["identities"]),
        "source_bindings": copy.deepcopy(packet["source_bindings"]),
        "result_units": {"width": "um", "depth": "um"},
        "calibration_status": "unknown",
        "uncertainty_status_by_id": {"row-uncertainty": "unknown"},
        "existing_source_family_ids": [],
        "packet_sha256": packet["packet_sha256"],
    }
    return AuthenticatedEvidenceInput(
        packet=packet,
        artifacts={"workbook": workbook, "readme": readme, "metadata": metadata},
        expected=expected,
        trusted_expectation_sha256=canonical_sha256(expected),
    )


def _real_nist_input() -> AuthenticatedEvidenceInput:
    material = build_nist_ambench_trace_validation_material(ROOT)
    item = next(
        entry
        for entry in material
        if any(
            attribute["name"] == "scan_speed_mm_s"
            and attribute["value"] == 800.0
            for attribute in entry["packet"]["contexts"]["process"]["attributes"]
        )
    )
    return AuthenticatedEvidenceInput(
        packet=item["packet"],
        artifacts=item["artifacts"],
        expected=item["expected"],
        trusted_expectation_sha256=canonical_sha256(item["expected"]),
    )


def _bridge() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "1.0",
        "gate_decision": {
            "directly_comparable_mds2_rows": 0,
            "calibrated_actual_power_mapping_established": False,
            "spot_size_mapping_established": False,
            "protocol_equivalence_established": False,
            "direct_numerical_validation_authorized": False,
            "cross_machine_pooling_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "scientific_status_changed": False,
        },
        "scientific_boundary": {
            "numerical_cross_source_comparison_performed": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "scientific_status_changed": False,
        },
    }
    value["report_sha256_without_self_field"] = canonical_sha256(value)
    return value


def _claim() -> dict[str, Any]:
    required = {
        "material_identity",
        "process_route",
        "sample_acquisition_identity",
        "instrument_state_calibration",
        "acquisition_parameters",
        "units_reference_conventions",
        "target_response_semantics",
    }
    dimensions = [rule.dimension for rule in DEFAULT_RULE_REGISTRY]
    return {
        "claim_id": "in625-direct-cross-source-quantitative-comparison-v1",
        "claim_type": "direct_quantitative_cross_source_validation",
        "required_dimensions": [
            dimension for dimension in dimensions if dimension in required
        ],
        "irrelevant_dimensions": [
            dimension for dimension in dimensions if dimension not in required
        ],
        "allowed_transformations": [],
        "requires_independent_replication": False,
        "maximum_downstream_use_requested": "comparative",
    }


def test_bootstrap_preserves_competing_hypotheses_and_zero_direct_authority() -> None:
    nist = _real_nist_input()
    mds2 = _synthetic_mds2_input()
    bridge = _bridge()
    claim = _claim()

    bootstrap = build_in625_competency_bootstrap(
        nist_evidence=nist,
        mds2_evidence=mds2,
        bridge_state=bridge,
        trusted_bridge_state_sha256=canonical_sha256(bridge),
        direct_comparison_claim=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )

    assert len(bootstrap["hypothesis_portfolio"]) == 5
    hypotheses = {
        item["hypothesis_id"]: item for item in bootstrap["hypothesis_portfolio"]
    }
    assert hypotheses["H_null_scope"]["verified_positive"] is True
    assert hypotheses["H_identity_bridge"]["verified_positive"] is False
    assert hypotheses["H_calibration_transfer"]["verified_positive"] is False
    assert hypotheses["H_protocol_comparability"]["verified_positive"] is False
    assert bootstrap["comparability_assessment"]["assessment_status"] != "COMPARABLE"
    assert bootstrap["scientific_boundary"] == {
        "exact_mds2_experiment_identity_established": False,
        "exact_machine_setting_to_calibrated_power_relation_established": False,
        "bridge_established": False,
        "directly_comparable_mds2_rows": 0,
        "direct_numerical_cross_source_validation_authorized": False,
        "issue_76_exact_target_cells_satisfied": 0,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "scientific_status_changed": False,
    }
    assert bootstrap["authority_boundary"]["execution_performed"] is False


def test_authenticated_bootstrap_generates_multiple_actions_without_execution() -> None:
    nist = _real_nist_input()
    mds2 = _synthetic_mds2_input()
    bridge = _bridge()
    claim = _claim()
    bootstrap = build_in625_competency_bootstrap(
        nist_evidence=nist,
        mds2_evidence=mds2,
        bridge_state=bridge,
        trusted_bridge_state_sha256=canonical_sha256(bridge),
        direct_comparison_claim=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )
    iteration = build_in625_competency_iteration(
        bootstrap,
        trusted_bootstrap_sha256=canonical_sha256(bootstrap),
    )

    plan = iteration["plan"]
    classes = {item["action_class"] for item in plan["self_generated_gap_actions"]}
    assert "external_evidence_search" in classes
    assert "physical_experiment_design" in classes
    assert plan["selected_next_action"]["action_class"] == "external_evidence_search"
    assert plan["selected_next_action"]["execution_mode"] == "explicit_authorization_required"
    assert iteration["authority_boundary"]["selected_action_is_authorized"] is False
    assert iteration["authority_boundary"]["execution_performed"] is False
    assert iteration["scientific_boundary"]["directly_comparable_mds2_rows"] == 0


def test_same_authenticated_state_stops_as_stagnation_not_fake_progress() -> None:
    nist = _real_nist_input()
    mds2 = _synthetic_mds2_input()
    bridge = _bridge()
    claim = _claim()
    bootstrap = build_in625_competency_bootstrap(
        nist_evidence=nist,
        mds2_evidence=mds2,
        bridge_state=bridge,
        trusted_bridge_state_sha256=canonical_sha256(bridge),
        direct_comparison_claim=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )
    trusted_bootstrap = canonical_sha256(bootstrap)
    first = build_in625_competency_iteration(
        bootstrap,
        trusted_bootstrap_sha256=trusted_bootstrap,
    )
    second = build_in625_competency_iteration(
        bootstrap,
        trusted_bootstrap_sha256=trusted_bootstrap,
        previous_plan=first["plan"],
    )

    assert second["plan"]["selected_next_action"] is None
    assert second["plan"]["stop_decision"]["reason"] in {
        "stagnation_no_new_verified_evidence",
        "stagnation_no_new_verified_research_state",
    }
    assert second["authority_boundary"]["execution_performed"] is False


def test_rehashed_bridge_promotion_fails_external_trust_root() -> None:
    nist = _real_nist_input()
    mds2 = _synthetic_mds2_input()
    bridge = _bridge()
    claim = _claim()
    trusted_bridge = canonical_sha256(bridge)
    forged = copy.deepcopy(bridge)
    forged["gate_decision"]["directly_comparable_mds2_rows"] = 1
    forged.pop("report_sha256_without_self_field")
    forged["report_sha256_without_self_field"] = canonical_sha256(forged)

    with pytest.raises(In625CompetencyBenchmarkError, match="external trust-root"):
        build_in625_competency_bootstrap(
            nist_evidence=nist,
            mds2_evidence=mds2,
            bridge_state=forged,
            trusted_bridge_state_sha256=trusted_bridge,
            direct_comparison_claim=claim,
            trusted_claim_scope_sha256=canonical_sha256(claim),
        )


def test_bootstrap_rehash_tamper_cannot_authorize_direct_rows() -> None:
    nist = _real_nist_input()
    mds2 = _synthetic_mds2_input()
    bridge = _bridge()
    claim = _claim()
    bootstrap = build_in625_competency_bootstrap(
        nist_evidence=nist,
        mds2_evidence=mds2,
        bridge_state=bridge,
        trusted_bridge_state_sha256=canonical_sha256(bridge),
        direct_comparison_claim=claim,
        trusted_claim_scope_sha256=canonical_sha256(claim),
    )
    trusted = canonical_sha256(bootstrap)
    forged = copy.deepcopy(bootstrap)
    forged["scientific_boundary"]["directly_comparable_mds2_rows"] = 18
    forged["scientific_boundary"][
        "direct_numerical_cross_source_validation_authorized"
    ] = True
    forged.pop("bootstrap_sha256")
    forged["bootstrap_sha256"] = canonical_sha256(forged)

    with pytest.raises(In625CompetencyBenchmarkError, match="external trust-root"):
        build_in625_competency_iteration(
            forged,
            trusted_bootstrap_sha256=trusted,
        )
