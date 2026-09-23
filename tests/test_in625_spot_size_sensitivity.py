from __future__ import annotations

import copy
import hashlib
from typing import Any

import pytest

from materials_data_analyzer.research_loop.comparability_engine import (
    AuthenticatedEvidenceInput,
)
from materials_data_analyzer.research_loop.evidence_packet import (
    canonical_sha256,
    finalize_evidence_packet,
)
from materials_data_analyzer.research_loop.in625_competency_episode import (
    In625CompetencyEpisodeError,
    build_in625_post_sensitivity_reassessment,
)
from materials_data_analyzer.research_loop.in625_spot_size_sensitivity import (
    In625SpotSizeSensitivityError,
    authorize_in625_spot_size_sensitivity_request,
    build_in625_spot_size_sensitivity_request,
    execute_in625_spot_size_sensitivity,
    verify_in625_spot_size_sensitivity,
)


def _attribute(
    name: str,
    value: object,
    *,
    source_binding_ids: list[str],
    unit: str | None = None,
) -> dict[str, Any]:
    if isinstance(value, bool):
        value_type = "boolean"
    elif isinstance(value, int):
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


def _mds2_inputs() -> list[AuthenticatedEvidenceInput]:
    """Contract fixture with the exact 18-track/7-level benchmark signature."""

    source = b"synthetic mds2 workbook contract fixture; not scientific evidence"
    source_sha = hashlib.sha256(source).hexdigest()
    spots = [
        50.0,
        50.0,
        80.0,
        80.0,
        110.0,
        110.0,
        140.0,
        140.0,
        140.0,
        170.0,
        170.0,
        210.0,
        210.0,
        210.0,
        256.0,
        256.0,
        256.0,
        256.0,
    ]
    result: list[AuthenticatedEvidenceInput] = []
    for index, spot in enumerate(spots, start=1):
        track = f"fixture-track-{index:02d}"
        evidence_id = f"fixture-mds2-row-{index:02d}"
        jitter = float((index % 3) - 1)
        width = 100.0 + 0.50 * spot + jitter
        depth = 90.0 - 0.12 * spot + 0.25 * jitter
        binding = {
            "binding_id": "workbook",
            "role": "authoritative_row_level_data_sheet",
            "artifact_id": "fixture:Master_TrackList_Measurements.xlsx",
            "locator": "fixture/Master_TrackList_Measurements.xlsx",
            "sha256": source_sha,
            "byte_size": len(source),
            "media_type": "application/octet-stream",
        }
        packet = finalize_evidence_packet(
            {
                "schema_version": "1.0",
                "packet_type": "evidence_packet",
                "evidence_id": evidence_id,
                "evidence_kind": "measurement",
                "provider": {
                    "provider_id": "nist-mds2-2923-row-provider",
                    "contract_version": "1.0",
                    "schema_version": "1.0",
                    "adapter_id": "mds2-2923-ammt-195w-800-evidence-packet-v1",
                },
                "subject": {
                    "subject_type": "material_process_cross_section_measurement",
                    "identities": [
                        {"namespace": "material", "value": "IN625", "role": "material"},
                        {
                            "namespace": "mds2_measurement_id",
                            "value": evidence_id,
                            "role": "measurement",
                        },
                        {
                            "namespace": "mds2_physical_track_id",
                            "value": track,
                            "role": "sample",
                        },
                    ],
                    "material_scope": "synthetic contract fixture only",
                    "description": "Not scientific evidence; spot sensitivity contract fixture.",
                },
                "contexts": {
                    "process": {
                        "status": "applicable",
                        "attributes": [
                            _attribute(
                                "process_route",
                                "NIST AMMT bare-substrate laser track experiment",
                                source_binding_ids=["workbook"],
                            ),
                            _attribute(
                                "laser_power_machine_setting",
                                195.0,
                                unit="W",
                                source_binding_ids=["workbook"],
                            ),
                            _attribute(
                                "scan_speed_machine_setting",
                                800.0,
                                unit="mm/s",
                                source_binding_ids=["workbook"],
                            ),
                            _attribute(
                                "spot_diameter_D4sigma",
                                spot,
                                unit="um",
                                source_binding_ids=["workbook"],
                            ),
                            _attribute(
                                "machine",
                                "AMMT",
                                source_binding_ids=["workbook"],
                            ),
                        ],
                    },
                    "sample": {
                        "status": "applicable",
                        "attributes": [
                            _attribute(
                                "physical_track_id",
                                track,
                                source_binding_ids=["workbook"],
                            )
                        ],
                    },
                    "method": {
                        "status": "applicable",
                        "attributes": [
                            _attribute(
                                "method",
                                "optical cross-section measurement",
                                source_binding_ids=["workbook"],
                            )
                        ],
                    },
                    "measurement": {
                        "status": "applicable",
                        "attributes": [
                            _attribute(
                                "reference_convention",
                                "melt-pool transverse width/depth geometry",
                                source_binding_ids=["workbook"],
                            )
                        ],
                    },
                },
                "results": [
                    {
                        "result_id": "melt-pool-width",
                        "result_kind": "melt_pool_width",
                        "value_state": "observed",
                        "value": width,
                        "value_type": "number",
                        "unit_state": "specified",
                        "unit": "um",
                        "source_binding_ids": ["workbook"],
                        "derivation_ids": [],
                        "uncertainty_ids": ["row-uncertainty"],
                        "qualifiers": ["fixture-only"],
                    },
                    {
                        "result_id": "melt-pool-depth",
                        "result_kind": "melt_pool_depth",
                        "value_state": "observed",
                        "value": depth,
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
                        "source_binding_ids": ["workbook"],
                        "notes": "Fixture preserves unknown row-specific uncertainty.",
                    }
                ],
                "calibration": {"status": "unknown", "records": []},
                "source_bindings": [binding],
                "derivation_lineage": [],
                "independence": {
                    "source_family_id": "nist-mds2-2923",
                    "dataset_parent_id": "nist-mds2-2923",
                    "sample_parent_ids": [track],
                    "acquisition_parent_ids": [track],
                    "development_family_id": None,
                    "overlap_status": "unknown",
                    "overlap_with": [],
                    "independence_claim_status": "not_assessed",
                },
                "scientific_validity": {
                    "domain_verifier_id": "fixture-only",
                    "verification_status": "limited",
                    "validated_scope": ["contract regression only"],
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
                "limitations": ["This fixture is not scientific evidence."],
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
            "provider_id": "nist-mds2-2923-row-provider",
            "subject_identities": copy.deepcopy(packet["subject"]["identities"]),
            "source_bindings": copy.deepcopy(packet["source_bindings"]),
            "result_units": {
                "melt-pool-width": "um",
                "melt-pool-depth": "um",
            },
            "calibration_status": "unknown",
            "uncertainty_status_by_id": {"row-uncertainty": "unknown"},
            "existing_source_family_ids": [],
            "packet_sha256": packet["packet_sha256"],
        }
        result.append(
            AuthenticatedEvidenceInput(
                packet=packet,
                artifacts={"workbook": source},
                expected=expected,
                trusted_expectation_sha256=canonical_sha256(expected),
            )
        )
    return result


def _bootstrap_and_iteration() -> tuple[dict[str, Any], dict[str, Any]]:
    planning_state = {
        "schema_version": "1.0",
        "state_type": "in625_competency_unresolved_evidence",
        "unresolved_evidence_gaps": [
            {
                "gap_id": "in625-benchmark:protocol-spot-uncertainty",
                "requirement": (
                    "Acquire authoritative measurement protocol, spot-size definition/value, "
                    "calibration, uncertainty and acquisition context needed to discriminate "
                    "protocol equivalence from context aliasing."
                ),
                "action_class_hint": "external_evidence_search",
            }
        ],
        "scientific_status_changed": False,
        "direct_numerical_cross_source_validation_authorized": False,
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
    }
    portfolio = [
        {
            "hypothesis_id": "H_protocol_comparability",
            "statement": "Protocol and spot semantics are sufficiently matched.",
            "status": "unsupported_or_unresolved",
            "verified_positive": False,
            "blocking_observation": "protocol_or_spot_size_equivalence=false_or_unknown",
        },
        {
            "hypothesis_id": "H_artifact_or_lineage",
            "statement": "Context loss can explain apparent agreement.",
            "status": "active_methodological_alternative",
            "verified_positive": False,
            "blocking_observation": None,
        },
    ]
    bootstrap: dict[str, Any] = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "episode_stage": "authenticated_initial_state",
        "research_question": "What evidence is required for direct IN625 cross-source comparison?",
        "input_bindings": {},
        "hypothesis_portfolio": portfolio,
        "comparability_assessment": {"assessment_status": "UNKNOWN"},
        "planning_state": planning_state,
        "scientific_boundary": {
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_cross_source_validation_authorized": False,
        },
        "authority_boundary": {"execution_performed": False},
    }
    bootstrap["bootstrap_sha256"] = canonical_sha256(bootstrap)
    candidate = {
        "action_id": "in625-benchmark:protocol-spot-uncertainty:analysis-design",
        "action_class": "sensitivity_analysis",
        "description": "Design a bounded reanalysis for the protocol/spot-size blocker.",
        "rationale": "Test existing evidence before acquiring new work.",
        "required_evidence": [
            "spot-size measurement protocol uncertainty and context aliasing"
        ],
        "expected_outcome": "A bounded analysis contract.",
        "execution_mode": "plan_only",
        "origin": "self_generated_from_evidence_gap",
        "expected_information_score": 0.65,
        "hypothesis_discrimination_score": 0.7,
        "feasibility_score": 0.85,
        "cost_units": 1.25,
        "risk_penalty": 0.0,
        "utility_score": 0.3,
        "utility_is_calibrated_probability": False,
        "automatic_execution_authorized": False,
        "physical_experiment_execution_authorized": False,
    }
    plan = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "iteration_index": 1,
        "max_iterations": 8,
        "program_binding": {"canonical_sha256": "a" * 64},
        "critic_binding": None,
        "reasoning_proposal_binding": None,
        "planning_budget": {
            "budget_units": 8.0,
            "minimum_utility": 0.01,
            "score_semantics": "deterministic_nonprobabilistic_planning_heuristic",
        },
        "research_objectives": [],
        "evidence_gaps": [],
        "candidate_hypotheses": [],
        "self_generated_gap_actions": [candidate],
        "ranked_actions": [candidate],
        "selected_next_action": candidate,
        "stop_decision": {
            "stop": False,
            "reason": "informative_action_available",
            "next_mode": "request_existing_authorization_chain",
        },
        "objective_revision": None,
        "handoff": {
            "required_for_selected_action": True,
            "destination": "existing_independent_action_authorization_and_typed_executor_chain",
            "request_compiled": False,
            "execution_performed": False,
        },
        "autonomy_boundary": {
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
        },
    }
    plan["plan_sha256"] = canonical_sha256(plan)
    iteration: dict[str, Any] = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "episode_stage": "self_directed_planning_iteration",
        "bootstrap_sha256": bootstrap["bootstrap_sha256"],
        "provider_state_sha256": "b" * 64,
        "program_state_sha256": "c" * 64,
        "plan": plan,
        "scientific_boundary": copy.deepcopy(bootstrap["scientific_boundary"]),
        "authority_boundary": {
            "selected_action_is_authorized": False,
            "request_compiled": False,
            "execution_performed": False,
            "scientific_status_changed": False,
        },
    }
    iteration["iteration_sha256"] = canonical_sha256(iteration)
    return bootstrap, iteration


def test_spot_size_action_executes_only_after_exact_request_authorization() -> None:
    inputs = _mds2_inputs()
    _bootstrap, iteration = _bootstrap_and_iteration()
    trusted_iteration = canonical_sha256(iteration)
    request = build_in625_spot_size_sensitivity_request(
        iteration,
        trusted_iteration_sha256=trusted_iteration,
        evidence_inputs=inputs,
    )
    trusted_request = canonical_sha256(request)
    authorization = authorize_in625_spot_size_sensitivity_request(
        request,
        trusted_request_sha256=trusted_request,
    )
    result = execute_in625_spot_size_sensitivity(
        request,
        authorization_receipt=authorization,
        trusted_authorization_sha256=canonical_sha256(authorization),
        evidence_inputs=inputs,
    )
    verified = verify_in625_spot_size_sensitivity(
        result,
        request=request,
        authorization_receipt=authorization,
        trusted_authorization_sha256=canonical_sha256(authorization),
        evidence_inputs=inputs,
    )

    assert verified["analysis"]["row_count"] == 18
    assert verified["analysis"]["physical_track_count"] == 18
    assert verified["analysis"]["spot_level_count"] == 7
    assert verified["analysis"]["width"]["slope_sign"] == 1
    assert verified["analysis"]["depth"]["slope_sign"] == -1
    assert verified["analysis"]["width"]["leave_one_level_sign_stable"] is True
    assert verified["analysis"]["depth"]["leave_one_level_sign_stable"] is True
    assert verified["scientific_interpretation"]["protocol_equivalence_established"] is False
    assert verified["authority_boundary"]["scientific_status_promoted"] is False


def test_request_tamper_fails_external_authorization_root() -> None:
    inputs = _mds2_inputs()
    _bootstrap, iteration = _bootstrap_and_iteration()
    request = build_in625_spot_size_sensitivity_request(
        iteration,
        trusted_iteration_sha256=canonical_sha256(iteration),
        evidence_inputs=inputs,
    )
    trusted_request = canonical_sha256(request)
    forged = copy.deepcopy(request)
    forged["analysis_contract"]["fixed_machine_setting_power_w"] = 179.2
    forged.pop("request_sha256")
    forged["request_sha256"] = canonical_sha256(forged)

    with pytest.raises(In625SpotSizeSensitivityError, match="external authorization"):
        authorize_in625_spot_size_sensitivity_request(
            forged,
            trusted_request_sha256=trusted_request,
        )


def test_duplicate_physical_track_fails_before_analysis() -> None:
    inputs = _mds2_inputs()
    _bootstrap, iteration = _bootstrap_and_iteration()
    inputs[-1] = inputs[-2]
    with pytest.raises(In625SpotSizeSensitivityError, match="duplicate"):
        build_in625_spot_size_sensitivity_request(
            iteration,
            trusted_iteration_sha256=canonical_sha256(iteration),
            evidence_inputs=inputs,
        )


def test_verified_spot_result_changes_planning_state_and_prevents_repeat_design() -> None:
    inputs = _mds2_inputs()
    bootstrap, iteration = _bootstrap_and_iteration()
    request = build_in625_spot_size_sensitivity_request(
        iteration,
        trusted_iteration_sha256=canonical_sha256(iteration),
        evidence_inputs=inputs,
    )
    authorization = authorize_in625_spot_size_sensitivity_request(
        request,
        trusted_request_sha256=canonical_sha256(request),
    )
    result = execute_in625_spot_size_sensitivity(
        request,
        authorization_receipt=authorization,
        trusted_authorization_sha256=canonical_sha256(authorization),
        evidence_inputs=inputs,
    )
    verified = verify_in625_spot_size_sensitivity(
        result,
        request=request,
        authorization_receipt=authorization,
        trusted_authorization_sha256=canonical_sha256(authorization),
        evidence_inputs=inputs,
    )
    reassessment = build_in625_post_sensitivity_reassessment(
        bootstrap=bootstrap,
        trusted_bootstrap_sha256=canonical_sha256(bootstrap),
        first_iteration=iteration,
        trusted_iteration_sha256=canonical_sha256(iteration),
        sensitivity_result=verified,
        trusted_result_sha256=canonical_sha256(verified),
    )

    assert reassessment["scientific_conclusion"]["new_verified_information"] is True
    assert (
        reassessment["scientific_conclusion"][
            "direct_numerical_cross_source_validation_authorized"
        ]
        is False
    )
    hypotheses = {
        item["hypothesis_id"]: item for item in reassessment["hypothesis_portfolio"]
    }
    assert hypotheses["H_protocol_comparability"]["verified_positive"] is False
    assert (
        hypotheses["H_protocol_comparability"]["diagnostic_result_sha256"]
        == verified["result_sha256"]
    )
    generated_classes = {
        item["action_class"]
        for item in reassessment["next_plan"]["self_generated_gap_actions"]
    }
    assert "external_evidence_search" in generated_classes
    assert "sensitivity_analysis" not in generated_classes
    assert reassessment["authority_boundary"]["automatic_execution_authorized"] is False


def test_reassessment_rejects_rehashed_scientific_promotion() -> None:
    inputs = _mds2_inputs()
    bootstrap, iteration = _bootstrap_and_iteration()
    request = build_in625_spot_size_sensitivity_request(
        iteration,
        trusted_iteration_sha256=canonical_sha256(iteration),
        evidence_inputs=inputs,
    )
    authorization = authorize_in625_spot_size_sensitivity_request(
        request,
        trusted_request_sha256=canonical_sha256(request),
    )
    result = execute_in625_spot_size_sensitivity(
        request,
        authorization_receipt=authorization,
        trusted_authorization_sha256=canonical_sha256(authorization),
        evidence_inputs=inputs,
    )
    trusted_result = canonical_sha256(result)
    forged = copy.deepcopy(result)
    forged["scientific_interpretation"]["protocol_equivalence_established"] = True
    forged.pop("result_sha256")
    forged["result_sha256"] = canonical_sha256(forged)

    with pytest.raises(In625CompetencyEpisodeError, match="external trust-root"):
        build_in625_post_sensitivity_reassessment(
            bootstrap=bootstrap,
            trusted_bootstrap_sha256=canonical_sha256(bootstrap),
            first_iteration=iteration,
            trusted_iteration_sha256=canonical_sha256(iteration),
            sensitivity_result=forged,
            trusted_result_sha256=trusted_result,
        )
