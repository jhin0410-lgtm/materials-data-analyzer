from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.scientific_control_plane import (
    CANONICAL_RESEARCH_STATE_ENTITIES,
    CANONICAL_TERMINAL_CLASSES,
    GOVERNANCE_PLANE_RESPONSIBILITIES,
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


def test_canonical_state_is_explicitly_multidimensional() -> None:
    required = {
        "research_question",
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
        "stop_state",
    }
    assert required.issubset(CANONICAL_RESEARCH_STATE_ENTITIES)


def test_science_and_governance_ownership_is_disjoint() -> None:
    assert set(SCIENCE_PLANE_RESPONSIBILITIES).isdisjoint(
        GOVERNANCE_PLANE_RESPONSIBILITIES
    )
    assert "scientific_action_value" in SCIENCE_PLANE_RESPONSIBILITIES
    assert "comparability" in SCIENCE_PLANE_RESPONSIBILITIES
    assert "uncertainty" in SCIENCE_PLANE_RESPONSIBILITIES
    assert "execution_authorization" in GOVERNANCE_PLANE_RESPONSIBILITIES


def test_provider_flow_requires_independent_validation_before_epistemic_ingestion() -> None:
    assert PROVIDER_TO_EVIDENCE_FLOW == (
        "provider_or_executor",
        "raw_artifact_bundle",
        "independent_domain_validator",
        "validated_evidence_packet",
        "epistemic_kernel",
    )


def test_architecture_metadata_and_readiness_projection_grant_no_authority() -> None:
    contract = build_scientific_control_plane_contract()

    assert set(contract["authority_boundary"].values()) == {False}
    assert contract["readiness_projection_semantics"] == {
        "readiness_projection_is_canonical_research_state": False,
        "characterization_l0_l8_is_readiness_projection": True,
        "readiness_projection_may_authorize_downstream_use": False,
        "readiness_projection_may_promote_scientific_status": False,
    }


def test_research_cycle_is_explicitly_a_single_action_primitive() -> None:
    contract = build_scientific_control_plane_contract()
    inventory = {
        item["surface_id"]: item for item in contract["controller_inventory"]
    }

    research_cycle = inventory["research_cycle"]
    assert research_cycle["classification"] == "canonical_primitive"
    assert research_cycle["maximum_actions_per_call"] == 1
    assert research_cycle["automatic_looping"] is False
    assert inventory["planning_adapter_facade"]["classification"] == "compatibility_facade"
    assert inventory["autonomous_production_extensions"]["classification"] == "domain_implementation"


def test_terminal_vocabulary_covers_scientific_non_conclusion_states() -> None:
    assert "converged" in CANONICAL_TERMINAL_CLASSES
    assert "irreducible_uncertainty" in CANONICAL_TERMINAL_CLASSES
    assert "contradictory_evidence" in CANONICAL_TERMINAL_CLASSES
    assert "blocked_external_evidence" in CANONICAL_TERMINAL_CLASSES
    assert "marginal_information_value_too_low" in CANONICAL_TERMINAL_CLASSES


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
