from __future__ import annotations

import copy
import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.recursive_research_cycle_controller import (
    RecursiveResearchCycleError,
    build_recursive_research_cycle_checkpoint,
    validate_recursive_research_cycle_checkpoint,
)


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _handoff() -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "handoff_id": "discrepancy-planning:g-1:h-1:aaaaaaaaaaaa",
        "source_discrepancy_report_sha256": "a" * 64,
        "source_iteration_index": 1,
        "target": {
            "graph_id": "g-1",
            "node_id": "h-1",
            "node_type": "hypothesis",
            "statement": "The declared model remains adequate within the verified scope.",
        },
        "diagnosis_context": {
            "diagnosis_types": ["parameter_or_property_uncertainty"],
            "passed_gates": ["numerical_validity"],
            "failed_gates": ["parameter_property_authority"],
            "stop_recommendation": "continue_discriminating_research",
            "stop_rationale": "Property authority remains insufficient.",
            "hypothesis_portfolio_directive": "continue_discriminating_research",
        },
        "research_objectives": [
            {
                "objective_id": "planning-objective:model-evidence:property-sensitivity",
                "source_proposal_id": "model-evidence:property-sensitivity",
                "source_rank": 1,
                "research_action_class": "sensitivity_analysis",
                "description": "Quantify sensitivity to the explicitly uncertain property.",
                "rationale": "Property uncertainty may account for the discrepancy.",
                "information_gain_priority": "high",
                "source_execution_mode": "plan_only",
                "planner_candidate_required": True,
                "candidate_match_status": "not_evaluated_in_current_handoff",
                "action_type": None,
                "action_version": None,
                "action_registry_id": None,
                "availability_asserted": False,
                "automatic_execution_authorized": False,
            }
        ],
        "planning_handoff_state": "fresh_planner_candidate_generation_required",
        "next_planning_cycle_required": True,
        "source_ancestry": {
            "previous_discrepancy_report_sha256": None,
            "prior_diagnosis_types": [],
            "current_diagnosis_types": ["parameter_or_property_uncertainty"],
        },
        "planner_boundary": {
            "current_planner_frontier_modified": False,
            "current_selected_action_modified": False,
            "executable_candidate_created": False,
            "candidate_availability_verified": False,
            "candidate_registry_binding_created": False,
            "fresh_planner_candidate_matching_required": True,
            "action_authorization_granted": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
        },
    }
    value["handoff_sha256"] = _canonical_sha(value)
    return value


def _plan(*, action_id: str = "planner:sensitivity-1") -> dict:
    selected = {
        "action_id": action_id,
        "action_class": "sensitivity_analysis",
        "action_kind": "analysis",
        "description": "Run bounded property sensitivity analysis.",
        "rationale": "Discriminate whether explicit property uncertainty matters.",
        "required_evidence": [],
        "expected_outcome": "Quantify sensitivity without imputing properties.",
        "execution_mode": "plan_only",
        "origin": "verified_goal_frontier",
        "expected_information_score": 0.8,
        "hypothesis_discrimination_score": 0.8,
        "feasibility_score": 0.9,
        "cost_units": 1.5,
        "risk_penalty": 0.0,
        "utility_score": 0.384,
        "utility_is_calibrated_probability": False,
        "automatic_execution_authorized": False,
        "physical_experiment_execution_authorized": False,
    }
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "program_binding": {"canonical_sha256": "b" * 64},
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
        "ranked_actions": [selected],
        "selected_next_action": dict(selected),
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
            "bounded_goal_derivation_performed": True,
            "methodological_rival_hypotheses_generated": False,
            "domain_mechanism_truth_invented": False,
            "empirical_evidence_created": False,
            "calibrated_probability_claimed": False,
            "network_access_performed": False,
            "physical_experiment_execution_performed": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
            "mission_mutated": False,
        },
    }
    value["plan_sha256"] = _canonical_sha(value)
    return value


def _match(handoff: dict, plan: dict) -> dict:
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "handoff_sha256": handoff["handoff_sha256"],
        "fresh_plan_sha256": plan["plan_sha256"],
        "objective_id": "planning-objective:model-evidence:property-sensitivity",
        "source_proposal_id": "model-evidence:property-sensitivity",
        "source_rank": 1,
        "candidate_action_id": "planner:sensitivity-1",
        "candidate_action_class": "sensitivity_analysis",
        "candidate_execution_mode": "plan_only",
        "match_rationale": (
            "The independently selected planner candidate addresses the same bounded "
            "property-sensitivity research objective."
        ),
    }


def test_fresh_selected_planner_candidate_advances_only_to_explicit_authorization() -> None:
    handoff = _handoff()
    plan = _plan()
    match = _match(handoff, plan)
    checkpoint = build_recursive_research_cycle_checkpoint(
        planning_handoff=handoff,
        fresh_plan=plan,
        candidate_match=match,
    )

    assert checkpoint["checkpoint_status"] == "explicit_authorization_required"
    assert checkpoint["authorization_handoff"] == {
        "required": True,
        "destination": "existing_independent_action_authorization_and_typed_executor_chain",
        "authorization_granted": False,
        "request_compiled": False,
        "execution_performed": False,
    }
    assert checkpoint["candidate_match"]["availability_promoted"] is False
    assert checkpoint["autonomy_boundary"]["critic_proposal_executed_directly"] is False
    assert checkpoint["autonomy_boundary"]["automatic_execution_authorized"] is False
    assert checkpoint["autonomy_boundary"]["epistemic_edge_created"] is False
    assert checkpoint["autonomy_boundary"]["scientific_status_changed"] is False

    verified = validate_recursive_research_cycle_checkpoint(
        checkpoint,
        planning_handoff=handoff,
        fresh_plan=plan,
        candidate_match=match,
    )
    assert verified["checkpoint_status"] == "explicit_authorization_required"
    assert verified["authorization_granted"] is False
    assert verified["execution_performed"] is False


def test_no_explicit_candidate_match_is_bounded_stop_not_heuristic_execution() -> None:
    checkpoint = build_recursive_research_cycle_checkpoint(
        planning_handoff=_handoff(),
        fresh_plan=_plan(),
        candidate_match=None,
    )
    assert checkpoint["checkpoint_status"] == "bounded_stop_no_matching_candidate"
    assert checkpoint["bounded_stop"]["stopped"] is True
    assert checkpoint["authorization_handoff"]["required"] is False
    assert checkpoint["autonomy_boundary"]["execution_performed"] is False


def test_match_cannot_substitute_objective_candidate_or_action_class() -> None:
    handoff = _handoff()
    plan = _plan()
    match = _match(handoff, plan)

    wrong_objective = copy.deepcopy(match)
    wrong_objective["objective_id"] = "planning-objective:other"
    with pytest.raises(RecursiveResearchCycleError, match="objective"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=handoff,
            fresh_plan=plan,
            candidate_match=wrong_objective,
        )

    wrong_candidate = copy.deepcopy(match)
    wrong_candidate["candidate_action_id"] = "planner:other"
    with pytest.raises(RecursiveResearchCycleError, match="selected_next_action"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=handoff,
            fresh_plan=plan,
            candidate_match=wrong_candidate,
        )

    wrong_class = copy.deepcopy(match)
    wrong_class["candidate_action_class"] = "simulation"
    with pytest.raises(RecursiveResearchCycleError, match="action_class"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=handoff,
            fresh_plan=plan,
            candidate_match=wrong_class,
        )


def test_handoff_plan_and_checkpoint_tamper_fail_closed() -> None:
    handoff = _handoff()
    plan = _plan()
    match = _match(handoff, plan)
    checkpoint = build_recursive_research_cycle_checkpoint(
        planning_handoff=handoff,
        fresh_plan=plan,
        candidate_match=match,
    )

    tampered_handoff = copy.deepcopy(handoff)
    tampered_handoff["target"]["statement"] = "substituted statement"
    with pytest.raises(RecursiveResearchCycleError, match="handoff_sha256"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=tampered_handoff,
            fresh_plan=plan,
            candidate_match=match,
        )

    tampered_plan = copy.deepcopy(plan)
    tampered_plan["selected_next_action"]["rationale"] = "substituted rationale"
    with pytest.raises(RecursiveResearchCycleError, match="plan_sha256"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=handoff,
            fresh_plan=tampered_plan,
            candidate_match=match,
        )

    tampered_checkpoint = copy.deepcopy(checkpoint)
    tampered_checkpoint["authorization_handoff"]["authorization_granted"] = True
    with pytest.raises(RecursiveResearchCycleError, match="checkpoint_sha256"):
        validate_recursive_research_cycle_checkpoint(
            tampered_checkpoint,
            planning_handoff=handoff,
            fresh_plan=plan,
            candidate_match=match,
        )


def test_previous_checkpoint_requires_a_new_plan_and_stable_target_identity() -> None:
    handoff = _handoff()
    plan = _plan()
    match = _match(handoff, plan)
    first = build_recursive_research_cycle_checkpoint(
        planning_handoff=handoff,
        fresh_plan=plan,
        candidate_match=match,
    )

    with pytest.raises(RecursiveResearchCycleError, match="plan SHA was reused"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=handoff,
            fresh_plan=plan,
            candidate_match=match,
            previous_checkpoint=first,
        )

    new_plan = _plan(action_id="planner:sensitivity-2")
    new_match = _match(handoff, new_plan)
    new_match["candidate_action_id"] = "planner:sensitivity-2"
    changed_target_handoff = copy.deepcopy(handoff)
    changed_target_handoff.pop("handoff_sha256")
    changed_target_handoff["target"]["node_id"] = "h-2"
    changed_target_handoff["handoff_sha256"] = _canonical_sha(changed_target_handoff)
    new_match["handoff_sha256"] = changed_target_handoff["handoff_sha256"]

    with pytest.raises(RecursiveResearchCycleError, match="target identity changed"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=changed_target_handoff,
            fresh_plan=new_plan,
            candidate_match=new_match,
            previous_checkpoint=first,
        )


def test_selected_candidate_must_be_exact_member_of_fresh_ranked_actions() -> None:
    handoff = _handoff()
    plan = _plan()
    plan.pop("plan_sha256")
    plan["selected_next_action"]["description"] = "not the ranked candidate bytes"
    plan["plan_sha256"] = _canonical_sha(plan)
    match = _match(handoff, plan)

    with pytest.raises(RecursiveResearchCycleError, match="independently ranked"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=handoff,
            fresh_plan=plan,
            candidate_match=match,
        )
