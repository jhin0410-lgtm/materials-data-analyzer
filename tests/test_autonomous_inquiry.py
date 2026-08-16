from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.autonomous_inquiry import (
    AutonomousInquiryError,
    build_autonomous_inquiry_plan,
)


def _program() -> dict[str, object]:
    return {
        "mission": {
            "autonomy_policy": {
                "goal_generation": "bounded_autonomous",
                "reasoning_proposals": "schema_validated",
                "typed_computational_actions": "explicit_request",
                "network_evidence_search": "explicit_authorization",
                "physical_experiment_execution": "external_only",
            }
        },
        "generated_goals": [
            {
                "goal_id": "mission:tem:resolve-current-blocker",
                "workstream_id": "tem",
                "research_question": "Is the current TEM claim independently supported?",
                "goal_statement": "Resolve missing independent TEM evidence.",
                "status": "active",
                "priority": 90,
                "evidence_requirements": [
                    "At least two independent samples and acquisitions",
                    "Raw or demonstrably lossless source representation",
                ],
                "claim_boundary": {"scientific_status": "inconclusive"},
                "action_frontier": [],
            }
        ],
    }


def _proposal() -> dict[str, object]:
    return {
        "proposal_status": "validated_for_planning_only",
        "new_hypotheses": [
            {
                "hypothesis_id": "h-domain-1",
                "statement": "A domain-specific alternative supplied by validated reasoning.",
                "falsification_criteria": ["Independent evidence contradicts the alternative."],
                "discriminating_evidence": ["Independent measurement"],
                "status": "proposed_not_evidence_upgraded",
            }
        ],
        "proposed_actions": [
            {
                "action_id": "simulate-1",
                "action_class": "simulation",
                "description": "Run a bounded solver sensitivity study.",
                "rationale": "Discriminate competing explanations.",
                "required_evidence": [],
                "expected_outcome": "A checksum-bound simulation result for later verification.",
                "execution_mode": "typed_local_action",
                "expected_information_score": 0.8,
                "hypothesis_discrimination_score": 0.9,
                "feasibility_score": 0.75,
                "cost_units": 2.0,
            },
            {
                "action_id": "experiment-1",
                "action_class": "physical_experiment_design",
                "description": "Design an independent replication experiment.",
                "rationale": "Acquire missing empirical evidence.",
                "required_evidence": [],
                "expected_outcome": "A plan for an authorized facility, not an executed experiment.",
                "execution_mode": "typed_local_action",
                "expected_information_score": 1.0,
                "hypothesis_discrimination_score": 1.0,
                "feasibility_score": 0.5,
                "cost_units": 5.0,
            },
        ],
    }


def test_planner_generates_methodological_rivals_and_evidence_gaps() -> None:
    plan = build_autonomous_inquiry_plan(_program())

    assert len(plan["candidate_hypotheses"]) == 3
    assert {item["hypothesis_type"] for item in plan["candidate_hypotheses"]} == {
        "readiness_alternative",
        "methodological_rival",
        "null_or_scope_rival",
    }
    assert len(plan["evidence_gaps"]) == 2
    assert all(not item["may_be_filled_by_synthetic_evidence"] for item in plan["evidence_gaps"])
    assert plan["autonomy_boundary"]["scientific_status_changed"] is False


def test_validated_reasoning_actions_are_ranked_without_execution_authority() -> None:
    plan = build_autonomous_inquiry_plan(
        _program(), validated_reasoning_proposal=_proposal(), budget_units=8.0
    )

    assert plan["selected_next_action"]["action_id"] == "simulate-1"
    assert plan["stop_decision"]["stop"] is False
    assert plan["handoff"]["destination"] == (
        "existing_independent_action_authorization_and_typed_executor_chain"
    )
    assert plan["handoff"]["execution_performed"] is False
    assert all(not item["automatic_execution_authorized"] for item in plan["ranked_actions"])


def test_physical_experiment_is_always_plan_only() -> None:
    plan = build_autonomous_inquiry_plan(
        _program(), validated_reasoning_proposal=_proposal(), budget_units=8.0
    )
    experiment = next(
        item for item in plan["ranked_actions"] if item["action_id"] == "experiment-1"
    )

    assert experiment["execution_mode"] == "plan_only"
    assert experiment["physical_experiment_execution_authorized"] is False
    assert plan["autonomy_boundary"]["physical_experiment_execution_performed"] is False


def test_budget_exhaustion_stops_before_handoff() -> None:
    plan = build_autonomous_inquiry_plan(
        _program(), validated_reasoning_proposal=_proposal(), budget_units=0.0
    )

    assert plan["stop_decision"] == {
        "stop": True,
        "reason": "budget_exhausted",
        "next_mode": "await_budget_or_revise_scope",
    }
    assert plan["selected_next_action"] is None
    assert plan["handoff"]["required_for_selected_action"] is False


def test_minimum_utility_can_force_objective_revision_without_claim_upgrade() -> None:
    plan = build_autonomous_inquiry_plan(
        _program(),
        validated_reasoning_proposal=_proposal(),
        budget_units=8.0,
        minimum_utility=0.5,
    )

    assert plan["stop_decision"]["reason"] == "no_affordable_informative_action"
    assert plan["objective_revision"]["status"] == "proposal_only"
    assert plan["objective_revision"]["mission_mutation_performed"] is False
    assert plan["autonomy_boundary"]["mission_mutated"] is False


def test_manual_only_mission_rejects_autonomous_inquiry() -> None:
    program = _program()
    program["mission"]["autonomy_policy"]["goal_generation"] = "manual_only"

    with pytest.raises(AutonomousInquiryError, match="does not permit"):
        build_autonomous_inquiry_plan(program)


def test_unvalidated_reasoning_proposal_is_rejected() -> None:
    proposal = _proposal()
    proposal["proposal_status"] = "draft"

    with pytest.raises(AutonomousInquiryError, match="validated_for_planning_only"):
        build_autonomous_inquiry_plan(_program(), validated_reasoning_proposal=proposal)


def test_plan_hash_is_deterministic_and_binds_input_changes() -> None:
    first = build_autonomous_inquiry_plan(
        _program(), validated_reasoning_proposal=_proposal()
    )
    second = build_autonomous_inquiry_plan(
        _program(), validated_reasoning_proposal=_proposal()
    )
    changed_program = copy.deepcopy(_program())
    changed_program["generated_goals"][0]["evidence_requirements"].append(
        "Traceable detector calibration"
    )
    changed = build_autonomous_inquiry_plan(
        changed_program, validated_reasoning_proposal=_proposal()
    )

    assert first["plan_sha256"] == second["plan_sha256"]
    assert first["program_binding"] != changed["program_binding"]
    assert first["plan_sha256"] != changed["plan_sha256"]
