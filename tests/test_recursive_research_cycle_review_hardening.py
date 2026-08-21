from __future__ import annotations

import copy
import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.recursive_research_cycle_controller import (
    RecursiveResearchCycleError,
    build_recursive_research_cycle_checkpoint,
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


def _handoff(*, previous_report_sha: str | None = None) -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "handoff_id": "discrepancy-planning:g-1:h-1:review",
        "source_discrepancy_report_sha256": "a" * 64,
        "source_iteration_index": 1,
        "target": {
            "graph_id": "g-1",
            "node_id": "h-1",
            "node_type": "hypothesis",
            "statement": "Bounded review target.",
        },
        "diagnosis_context": {},
        "research_objectives": [
            {
                "objective_id": "planning-objective:review",
                "source_proposal_id": "proposal:review",
                "source_rank": 1,
                "research_action_class": "sensitivity_analysis",
                "planner_candidate_required": True,
                "availability_asserted": False,
                "automatic_execution_authorized": False,
            }
        ],
        "planning_handoff_state": "fresh_planner_candidate_generation_required",
        "next_planning_cycle_required": True,
        "source_ancestry": {
            "previous_discrepancy_report_sha256": previous_report_sha,
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
    value["handoff_sha256"] = _sha(value)
    return value


def _plan(*, action_id: str = "planner:review") -> dict:
    selected = {
        "action_id": action_id,
        "action_class": "sensitivity_analysis",
        "execution_mode": "plan_only",
        "automatic_execution_authorized": False,
    }
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "ranked_actions": [dict(selected)],
        "selected_next_action": dict(selected),
        "stop_decision": {
            "stop": False,
            "reason": "informative_action_available",
            "next_mode": "request_existing_authorization_chain",
        },
        "handoff": {
            "required_for_selected_action": True,
            "request_compiled": False,
            "execution_performed": False,
        },
        "autonomy_boundary": {
            "empirical_evidence_created": False,
            "network_access_performed": False,
            "physical_experiment_execution_performed": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
            "mission_mutated": False,
        },
    }
    value["plan_sha256"] = _sha(value)
    return value


def _match(handoff: dict, plan: dict) -> dict:
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "handoff_sha256": handoff["handoff_sha256"],
        "fresh_plan_sha256": plan["plan_sha256"],
        "objective_id": "planning-objective:review",
        "source_proposal_id": "proposal:review",
        "source_rank": 1,
        "candidate_action_id": plan["selected_next_action"]["action_id"],
        "candidate_action_class": "sensitivity_analysis",
        "candidate_execution_mode": "plan_only",
        "match_rationale": "Exact typed match for the independently selected planner candidate.",
    }


def test_unsupported_autonomous_plan_policy_version_is_rejected_even_with_fresh_sha() -> None:
    handoff = _handoff()
    plan = _plan()
    plan.pop("plan_sha256")
    plan["policy_version"] = "999.0"
    plan["plan_sha256"] = _sha(plan)

    with pytest.raises(RecursiveResearchCycleError, match="policy_version"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=handoff,
            fresh_plan=plan,
            candidate_match=_match(handoff, plan),
        )


def test_planner_stop_cannot_retain_selected_action_and_reach_authorization() -> None:
    handoff = _handoff()
    plan = _plan()
    plan.pop("plan_sha256")
    plan["stop_decision"] = {
        "stop": True,
        "reason": "budget_exhausted",
        "next_mode": "await_budget_or_revise_scope",
    }
    plan["plan_sha256"] = _sha(plan)

    with pytest.raises(RecursiveResearchCycleError, match="stop decision"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=handoff,
            fresh_plan=plan,
            candidate_match=_match(handoff, plan),
        )


def test_successor_handoff_requires_previous_checkpoint_ancestry() -> None:
    handoff = _handoff(previous_report_sha="9" * 64)
    plan = _plan()

    with pytest.raises(RecursiveResearchCycleError, match="requires previous"):
        build_recursive_research_cycle_checkpoint(
            planning_handoff=handoff,
            fresh_plan=plan,
            candidate_match=_match(handoff, plan),
            previous_checkpoint=None,
        )


def test_initial_handoff_without_previous_report_may_start_cycle_one() -> None:
    handoff = _handoff(previous_report_sha=None)
    plan = _plan()
    checkpoint = build_recursive_research_cycle_checkpoint(
        planning_handoff=handoff,
        fresh_plan=plan,
        candidate_match=_match(handoff, plan),
    )
    assert checkpoint["cycle_index"] == 1
    assert checkpoint["checkpoint_status"] == "explicit_authorization_required"
