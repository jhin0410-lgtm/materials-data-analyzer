from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.scientific_control_plane import (
    CANONICAL_RESEARCH_STATE_ENTITIES,
    CANONICAL_TERMINAL_CLASSES,
    CONTROLLER_INVENTORY,
    GOVERNANCE_PLANE_RESPONSIBILITIES,
    LEGACY_STOP_STATUS_COMPATIBILITY,
    PROVIDER_TO_EVIDENCE_FLOW,
    SCIENCE_PLANE_RESPONSIBILITIES,
    ScientificControlPlaneError,
    build_scientific_control_plane_contract,
    project_legacy_stop_status,
    validate_scientific_control_plane_contract,
)


def test_control_plane_contract_is_deterministic_and_valid() -> None:
    first = build_scientific_control_plane_contract()
    second = build_scientific_control_plane_contract()

    assert first == second
    assert validate_scientific_control_plane_contract(first) == first


def test_canonical_state_is_explicitly_multidimensional_without_operational_stop() -> None:
    required = {
        "research_question",
        "scientific_mission",
        "hypothesis",
        "observation",
        "derived_result",
        "evidence",
        "claim",
        "inference",
        "contradiction",
        "comparability_assessment",
        "uncertainty_state",
        "evidence_gap",
        "candidate_action",
        "decision",
    }
    assert required.issubset(CANONICAL_RESEARCH_STATE_ENTITIES)
    assert "bounded_mission" not in CANONICAL_RESEARCH_STATE_ENTITIES
    assert "stop_state" not in CANONICAL_RESEARCH_STATE_ENTITIES


def test_science_and_governance_ownership_is_disjoint_and_inference_is_science_owned() -> None:
    assert set(SCIENCE_PLANE_RESPONSIBILITIES).isdisjoint(
        GOVERNANCE_PLANE_RESPONSIBILITIES
    )
    assert "inference_formation_and_assessment" in SCIENCE_PLANE_RESPONSIBILITIES
    assert "scientific_action_value" in SCIENCE_PLANE_RESPONSIBILITIES
    assert "comparability" in SCIENCE_PLANE_RESPONSIBILITIES
    assert "uncertainty" in SCIENCE_PLANE_RESPONSIBILITIES
    assert "autonomy_access_and_delegation_policy" in GOVERNANCE_PLANE_RESPONSIBILITIES
    assert "execution_authorization" in GOVERNANCE_PLANE_RESPONSIBILITIES
    assert "run_lifecycle_recording" in GOVERNANCE_PLANE_RESPONSIBILITIES


def test_provider_flow_requires_validation_and_authority_bearing_update_before_kernel() -> None:
    assert PROVIDER_TO_EVIDENCE_FLOW == (
        "provider_or_executor",
        "raw_artifact_bundle",
        "independent_domain_validator",
        "validated_evidence_packet",
        "authority_bearing_epistemic_update",
        "epistemic_kernel",
    )


def test_architecture_metadata_authentication_and_readiness_grant_no_scientific_authority() -> None:
    contract = build_scientific_control_plane_contract()

    assert set(contract["authority_boundary"].values()) == {False}
    assert contract["authority_boundary"][
        "authenticated_artifact_is_validated_scientific_evidence"
    ] is False
    assert contract["authority_boundary"][
        "diagnostic_transition_creates_authoritative_epistemic_update"
    ] is False
    assert contract["readiness_projection_semantics"] == {
        "readiness_projection_is_canonical_research_state": False,
        "characterization_l0_l8_is_readiness_projection": True,
        "readiness_projection_may_authorize_downstream_use": False,
        "readiness_projection_may_promote_scientific_status": False,
    }


def test_legacy_mission_projects_science_and_governance_without_cross_authority() -> None:
    mission = build_scientific_control_plane_contract()["mission_projection_semantics"]
    assert mission["legacy_bounded_mission_is_composite"] is True
    assert mission["science_projection_contains_objective_scope_and_success_criteria"] is True
    assert mission["governance_projection_contains_autonomy_access_and_delegation_policy"] is True
    assert mission["science_projection_may_modify_execution_policy"] is False


def test_authenticated_epistemic_transition_is_diagnostic_only() -> None:
    contract = build_scientific_control_plane_contract()
    diagnostic = contract["diagnostic_transition_semantics"]
    assert diagnostic["authenticated_epistemic_transition_is_diagnostic"] is True
    assert diagnostic["authenticated_epistemic_transition_applies_scientific_authority"] is False
    assert diagnostic["reauthentication_grants_scientific_authority"] is False
    assert diagnostic["future_authority_bearing_update_requires_validated_evidence_packet"] is True

    inventory = {
        item["surface_id"]: item for item in contract["controller_inventory"]
    }
    transition = inventory["authenticated_epistemic_transition"]
    assert transition["role"] == "authenticated_diagnostic_transition_bundle_producer_only"
    assert transition["scientific_authority_applied"] is False


def test_all_installed_looping_research_surfaces_are_classified() -> None:
    contract = build_scientific_control_plane_contract()
    inventory = {
        item["surface_id"]: item for item in contract["controller_inventory"]
    }

    assert inventory["research_cycle"]["maximum_actions_per_call"] == 1
    assert inventory["research_cycle"]["automatic_looping"] is False

    bounded = inventory["bounded_multicycle_controller"]
    assert bounded["classification"] == "compatibility_facade"
    assert bounded["automatic_looping"] is True
    assert bounded["maximum_actions_per_call"] == 32

    epistemic = inventory["epistemically_bounded_multicycle_controller"]
    assert epistemic["classification"] == "compatibility_facade"
    assert epistemic["automatic_looping"] is True
    assert epistemic["maximum_actions_per_call"] == 32

    evidence_loop = inventory["mission_authorized_evidence_loop"]
    assert evidence_loop["classification"] == "domain_implementation"
    assert evidence_loop["automatic_looping"] is True

    assert inventory["persistent_research_episode"]["automatic_looping"] is False
    assert inventory["planning_adapter_facade"]["classification"] == "compatibility_facade"
    assert inventory["autonomous_production_extensions"]["classification"] == "domain_implementation"


def test_terminal_vocabulary_contains_scientific_dispositions_not_runtime_failure_codes() -> None:
    assert "converged" in CANONICAL_TERMINAL_CLASSES
    assert "irreducible_uncertainty" in CANONICAL_TERMINAL_CLASSES
    assert "contradictory_evidence" in CANONICAL_TERMINAL_CLASSES
    assert "blocked_external_evidence" in CANONICAL_TERMINAL_CLASSES
    assert "marginal_information_value_too_low" in CANONICAL_TERMINAL_CLASSES
    assert "execution_failed" not in CANONICAL_TERMINAL_CLASSES
    assert "interrupted" not in CANONICAL_TERMINAL_CLASSES


def test_unambiguous_legacy_review_gate_projects_without_rewriting_history() -> None:
    projection = project_legacy_stop_status("manual_review_gate")

    assert projection["automatic_progress_stopped"] is True
    assert projection["canonical_terminal_class"] == "review_required"
    assert projection["semantic_refinement_required"] is False
    assert projection["historical_artifact_rewritten"] is False
    assert projection["scientific_status_promoted"] is False


def test_ambiguous_legacy_stops_do_not_invent_stronger_scientific_semantics() -> None:
    for status in ("operationally_blocked", "terminal_for_current_scope"):
        projection = project_legacy_stop_status(status)
        assert projection["automatic_progress_stopped"] is True
        assert projection["canonical_terminal_class"] is None
        assert projection["semantic_refinement_required"] is True
        assert projection["scientific_status_promoted"] is False


def test_unknown_legacy_stop_status_fails_closed() -> None:
    with pytest.raises(ScientificControlPlaneError, match="unsupported legacy stop status"):
        project_legacy_stop_status("probably_converged")


def test_frozen_tables_are_immutable_in_place() -> None:
    with pytest.raises(TypeError):
        CONTROLLER_INVENTORY[0][0] = "mutated"  # type: ignore[index]
    with pytest.raises(TypeError):
        LEGACY_STOP_STATUS_COMPATIBILITY[0][1][0] = True  # type: ignore[index]

    before = build_scientific_control_plane_contract()
    local_copy = before["controller_inventory"]
    local_copy[0]["role"] = "caller-mutated-copy"
    after = build_scientific_control_plane_contract()
    assert after["controller_inventory"][0]["role"] != "caller-mutated-copy"


def test_contract_rejects_unknown_fields_and_authority_promotion() -> None:
    contract = build_scientific_control_plane_contract()
    contract["unknown"] = True
    with pytest.raises(ScientificControlPlaneError, match="exact key set"):
        validate_scientific_control_plane_contract(contract)

    promoted = build_scientific_control_plane_contract()
    promoted["authority_boundary"]["governance_plane_grants_scientific_authority"] = True
    with pytest.raises(ScientificControlPlaneError, match="authority_boundary drifted"):
        validate_scientific_control_plane_contract(promoted)


def test_contract_rejects_science_governance_conflation_even_if_otherwise_well_formed() -> None:
    contract = copy.deepcopy(build_scientific_control_plane_contract())
    contract["governance_plane_responsibilities"][0] = "comparability"

    with pytest.raises(ScientificControlPlaneError):
        validate_scientific_control_plane_contract(contract)
