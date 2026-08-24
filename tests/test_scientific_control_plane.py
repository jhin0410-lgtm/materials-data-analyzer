from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.scientific_control_plane import (
    CANONICAL_RESEARCH_STAGES,
    CANONICAL_RESEARCH_STATE_ENTITIES,
    CANONICAL_TERMINAL_CLASSES,
    CONTROLLER_INVENTORY,
    GOVERNANCE_PLANE_RESPONSIBILITIES,
    GOVERNANCE_RUN_STOP_REASONS,
    LEGACY_MISSION_FIELD_PROJECTIONS,
    LEGACY_MISSION_ITEM_PROJECTIONS,
    LEGACY_STOP_STATUS_COMPATIBILITY,
    PROVIDER_TO_EVIDENCE_FLOW,
    SCIENCE_PLANE_RESPONSIBILITIES,
    ScientificControlPlaneError,
    build_scientific_control_plane_contract,
    project_legacy_mission_field,
    project_legacy_mission_item,
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


def test_evidence_gap_mapping_requires_validated_packets_not_generic_verified_artifacts() -> None:
    assert "map_validated_evidence_packets_and_gaps" in CANONICAL_RESEARCH_STAGES
    assert "map_verified_evidence_and_gaps" not in CANONICAL_RESEARCH_STAGES
    assert CANONICAL_RESEARCH_STAGES.index("independently_verify_result") < (
        CANONICAL_RESEARCH_STAGES.index("ingest_validated_evidence_packet")
    )


def test_provider_flow_requires_validation_and_authority_bearing_update_before_kernel() -> None:
    assert PROVIDER_TO_EVIDENCE_FLOW == (
        "provider_or_executor",
        "raw_artifact_bundle",
        "independent_domain_validator",
        "validated_evidence_packet",
        "authority_bearing_epistemic_update",
        "epistemic_kernel",
    )


def test_governance_stops_are_not_scientific_terminal_dispositions() -> None:
    assert "resource_budget_exhausted" in GOVERNANCE_RUN_STOP_REASONS
    assert "authorization_or_safety_blocked" in GOVERNANCE_RUN_STOP_REASONS
    assert "resource_budget_exhausted" not in CANONICAL_TERMINAL_CLASSES
    assert "authorization_or_safety_blocked" not in CANONICAL_TERMINAL_CLASSES
    assert set(GOVERNANCE_RUN_STOP_REASONS).isdisjoint(CANONICAL_TERMINAL_CLASSES)


def test_architecture_metadata_authentication_and_readiness_grant_no_scientific_authority() -> None:
    contract = build_scientific_control_plane_contract()

    assert set(contract["authority_boundary"].values()) == {False}
    assert contract["authority_boundary"][
        "authenticated_artifact_is_validated_scientific_evidence"
    ] is False
    assert contract["authority_boundary"][
        "diagnostic_transition_creates_authoritative_epistemic_update"
    ] is False
    assert contract["authority_boundary"][
        "governance_stop_reason_is_scientific_terminal_disposition"
    ] is False
    assert contract["readiness_projection_semantics"] == {
        "readiness_projection_is_canonical_research_state": False,
        "characterization_l0_l8_is_readiness_projection": True,
        "readiness_projection_may_authorize_downstream_use": False,
        "readiness_projection_may_promote_scientific_status": False,
    }


def _production_mission() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    return json.loads(
        (root / "configs/research/autonomous_in625_production_mission.v1.json").read_text(
            encoding="utf-8"
        )
    )


def test_real_legacy_mission_field_requires_exact_classified_projection() -> None:
    mission = _production_mission()
    mission_id = mission["mission_id"]
    mission_text = mission["mission"]
    assert isinstance(mission_id, str)
    assert isinstance(mission_text, str)

    projected = project_legacy_mission_field(
        mission_id=mission_id,
        mission_text=mission_text,
    )
    assert projected["source_field"] == "mission"
    assert projected["science_projection"]
    assert projected["governance_projection"]
    assert projected["scientific_status_promoted"] is False
    assert projected["execution_authority_granted"] is False

    with pytest.raises(ScientificControlPlaneError, match="no exact deterministic"):
        project_legacy_mission_field(
            mission_id=mission_id,
            mission_text=mission_text + " widened",
        )


def test_every_real_legacy_mission_item_has_one_exact_projection() -> None:
    mission = _production_mission()
    mission_id = mission["mission_id"]
    assert isinstance(mission_id, str)

    observed = []
    for collection in ("success_criteria", "constraints", "stop_rules"):
        items = mission[collection]
        assert isinstance(items, list)
        for index, item in enumerate(items):
            assert isinstance(item, str)
            projection = project_legacy_mission_item(
                mission_id=mission_id,
                collection=collection,
                item_index=index,
                item_text=item,
            )
            assert projection["science_semantic"] or projection["governance_semantic"]
            assert projection["scientific_status_promoted"] is False
            assert projection["execution_authority_granted"] is False
            observed.append((collection, index, item))

    frozen = [
        (record.collection, record.item_index, record.item_text)
        for record in LEGACY_MISSION_ITEM_PROJECTIONS
        if record.mission_id == mission_id
    ]
    assert observed == frozen

    first = mission["success_criteria"][0]
    assert isinstance(first, str)
    with pytest.raises(ScientificControlPlaneError, match="no exact deterministic"):
        project_legacy_mission_item(
            mission_id=mission_id,
            collection="success_criteria",
            item_index=0,
            item_text=first + " widened",
        )


def test_legacy_mission_contract_exposes_exact_not_heuristic_projections() -> None:
    semantics = build_scientific_control_plane_contract()["mission_projection_semantics"]
    assert semantics["legacy_bounded_mission_is_composite"] is True
    assert semantics["real_legacy_mission_field_requires_classified_projection"] is True
    assert semantics["item_level_projection_required_for"] == [
        "success_criteria",
        "constraints",
        "stop_rules",
    ]
    assert semantics["unknown_mission_field_or_item_projection"] == "unresolved_no_authority"
    assert semantics["science_projection_may_modify_execution_policy"] is False
    assert "autonomous-in625-production-v1" in semantics["legacy_mission_field_projections"]
    assert len(semantics["legacy_mission_item_projections"]) == len(
        LEGACY_MISSION_ITEM_PROJECTIONS
    )


def test_authenticated_epistemic_transition_is_diagnostic_only() -> None:
    contract = build_scientific_control_plane_contract()
    diagnostic = contract["diagnostic_transition_semantics"]
    assert diagnostic["authenticated_epistemic_transition_is_diagnostic"] is True
    assert diagnostic["authenticated_epistemic_transition_applies_scientific_authority"] is False
    assert diagnostic["reauthentication_grants_scientific_authority"] is False
    assert diagnostic["future_authority_bearing_update_requires_validated_evidence_packet"] is True

    inventory = {item["surface_id"]: item for item in contract["controller_inventory"]}
    transition = inventory["authenticated_epistemic_transition"]
    assert transition["role"] == "authenticated_diagnostic_transition_bundle_producer_only"
    assert transition["scientific_authority_applied"] is False


def test_all_installed_looping_and_public_recursive_surfaces_are_classified() -> None:
    contract = build_scientific_control_plane_contract()
    inventory = {item["surface_id"]: item for item in contract["controller_inventory"]}

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

    checkpoint = inventory["persistent_research_episode_checkpoint"]
    assert checkpoint["classification"] == "canonical_primitive"
    assert checkpoint["automatic_looping"] is False
    assert checkpoint["maximum_actions_per_call"] == 0

    runner = inventory["persistent_research_episode"]
    assert runner["classification"] == "compatibility_facade"
    assert runner["automatic_looping"] is True
    assert runner["maximum_actions_per_call"] is None

    public_recursive = inventory["public_recursive_api"]
    assert public_recursive["classification"] == "compatibility_facade"
    assert public_recursive["automatic_looping"] is False
    assert public_recursive["maximum_actions_per_call"] == 1
    assert "bounded_replay" in public_recursive["role"]

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
    assert "resource_budget_exhausted" not in CANONICAL_TERMINAL_CLASSES
    assert "authorization_or_safety_blocked" not in CANONICAL_TERMINAL_CLASSES


def test_manual_review_gate_requires_semantic_refinement_before_science_projection() -> None:
    projection = project_legacy_stop_status("manual_review_gate")

    assert projection["automatic_progress_stopped"] is True
    assert projection["canonical_terminal_class"] is None
    assert projection["semantic_refinement_required"] is True
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
    with pytest.raises(TypeError):
        LEGACY_MISSION_FIELD_PROJECTIONS[0][2] = "mutated"  # type: ignore[index]
    with pytest.raises(TypeError):
        LEGACY_MISSION_ITEM_PROJECTIONS[0][3] = "mutated"  # type: ignore[index]

    before = build_scientific_control_plane_contract()
    before["controller_inventory"][0]["role"] = "caller-mutated-copy"
    before["mission_projection_semantics"]["legacy_mission_item_projections"][0][
        "science_semantic"
    ] = "caller-mutated-copy"
    after = build_scientific_control_plane_contract()
    assert after["controller_inventory"][0]["role"] != "caller-mutated-copy"
    assert (
        after["mission_projection_semantics"]["legacy_mission_item_projections"][0][
            "science_semantic"
        ]
        != "caller-mutated-copy"
    )


def test_contract_rejects_unknown_fields_and_authority_promotion() -> None:
    contract = build_scientific_control_plane_contract()
    contract["unknown"] = True
    with pytest.raises(ScientificControlPlaneError, match="exact key set"):
        validate_scientific_control_plane_contract(contract)

    promoted = build_scientific_control_plane_contract()
    promoted["authority_boundary"]["governance_plane_grants_scientific_authority"] = True
    with pytest.raises(ScientificControlPlaneError, match="authority_boundary drifted"):
        validate_scientific_control_plane_contract(promoted)


def test_contract_rejects_governance_stop_as_scientific_terminal() -> None:
    contract = copy.deepcopy(build_scientific_control_plane_contract())
    contract["canonical_terminal_classes"].append("resource_budget_exhausted")

    with pytest.raises(ScientificControlPlaneError):
        validate_scientific_control_plane_contract(contract)


def test_contract_rejects_science_governance_conflation_even_if_otherwise_well_formed() -> None:
    contract = copy.deepcopy(build_scientific_control_plane_contract())
    contract["governance_plane_responsibilities"][0] = "comparability"

    with pytest.raises(ScientificControlPlaneError):
        validate_scientific_control_plane_contract(contract)
