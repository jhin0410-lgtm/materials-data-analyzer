from __future__ import annotations

import copy
import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.autonomous_inquiry import (
    build_autonomous_inquiry_plan,
)
from materials_data_analyzer.research_loop.autonomous_inquiry_plan_verifier import (
    AutonomousInquiryPlanVerifierError,
    validate_autonomous_inquiry_plan,
)
from materials_data_analyzer.research_loop.validated_recursive_cycle_planning import (
    build_validated_recursive_planning_checkpoint,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _program_state() -> dict:
    return {
        "mission": {
            "autonomy_policy": {
                "goal_generation": "bounded_autonomous",
            }
        },
        "generated_goals": [
            {
                "goal_id": "goal-property-sensitivity",
                "workstream_id": "ws-1",
                "research_question": "Does explicit property uncertainty affect the bounded result?",
                "goal_statement": "Quantify sensitivity to the explicitly uncertain property.",
                "status": "active",
                "priority": "high",
                "evidence_requirements": ["bounded property sensitivity result"],
                "claim_boundary": "computational_only",
                "action_frontier": [
                    {
                        "action_id": "planner:sensitivity-verified",
                        "action_class": "sensitivity_analysis",
                        "description": "Run bounded property sensitivity analysis.",
                        "rationale": "Discriminate explicit property uncertainty.",
                        "execution_mode": "plan_only",
                        "expected_information_score": 0.8,
                        "hypothesis_discrimination_score": 0.8,
                        "feasibility_score": 0.9,
                        "cost_units": 1.5,
                        "risk_penalty": 0.0,
                    }
                ],
            }
        ],
    }


def _handoff(previous_report_sha: str) -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_discrepancy_report_sha256": previous_report_sha,
        "target": {
            "graph_id": "g-1",
            "node_id": "h-1",
            "node_type": "hypothesis",
            "statement": "Bounded target statement.",
        },
        "source_ancestry": {
            "previous_discrepancy_report_sha256": None,
            "prior_diagnosis_types": [],
            "current_diagnosis_types": ["parameter_or_property_uncertainty"],
        },
        "research_objectives": [
            {
                "objective_id": "planning-objective:model-evidence:property-sensitivity",
                "source_proposal_id": "model-evidence:property-sensitivity",
                "source_rank": 1,
                "research_action_class": "sensitivity_analysis",
                "planner_candidate_required": True,
                "availability_asserted": False,
                "automatic_execution_authorized": False,
            }
        ],
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
    value["handoff_sha256"] = _sha(value)
    return value


def _match(handoff: dict, plan: dict) -> dict:
    selected = plan["selected_next_action"]
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "handoff_sha256": handoff["handoff_sha256"],
        "fresh_plan_sha256": plan["plan_sha256"],
        "objective_id": handoff["research_objectives"][0]["objective_id"],
        "source_proposal_id": handoff["research_objectives"][0]["source_proposal_id"],
        "source_rank": 1,
        "candidate_action_id": selected["action_id"],
        "candidate_action_class": selected["action_class"],
        "candidate_execution_mode": selected["execution_mode"],
        "match_rationale": "Planner independently reconstructed the same bounded action class.",
    }


def test_plan_verifier_rebuilds_exact_planner_result() -> None:
    program = _program_state()
    plan = build_autonomous_inquiry_plan(program)
    verified = validate_autonomous_inquiry_plan(plan, program_state=program)
    assert verified["plan_sha256"] == plan["plan_sha256"]
    assert verified["verification_status"] == "deterministically_rebuilt_from_planner_inputs"
    assert verified["authorization_granted"] is False
    assert verified["execution_performed"] is False


def test_self_rehashed_fabricated_plan_fails_deterministic_reconstruction() -> None:
    program = _program_state()
    plan = build_autonomous_inquiry_plan(program)
    fabricated = copy.deepcopy(plan)
    fabricated.pop("plan_sha256")
    fabricated["selected_next_action"]["rationale"] = "self-authored substituted rationale"
    fabricated["ranked_actions"][0]["rationale"] = "self-authored substituted rationale"
    fabricated["plan_sha256"] = _sha(fabricated)

    with pytest.raises(AutonomousInquiryPlanVerifierError, match="differs from deterministic"):
        validate_autonomous_inquiry_plan(fabricated, program_state=program)


def test_validated_recursive_entry_binds_planner_reconstruction_and_still_grants_no_authority() -> None:
    program = _program_state()
    plan = build_autonomous_inquiry_plan(program)
    handoff = _handoff("a" * 64)
    match = _match(handoff, plan)

    result = build_validated_recursive_planning_checkpoint(
        planning_handoff=handoff,
        fresh_plan=plan,
        planner_program_state=program,
        candidate_match=match,
    )
    assert result["planner_verification"]["plan_sha256"] == plan["plan_sha256"]
    assert result["recursive_checkpoint"]["checkpoint_status"] == (
        "explicit_authorization_required"
    )
    assert result["autonomy_boundary"]["planner_reconstruction_verified"] is True
    assert result["autonomy_boundary"]["authorization_granted"] is False
    assert result["autonomy_boundary"]["request_compiled"] is False
    assert result["autonomy_boundary"]["execution_performed"] is False
