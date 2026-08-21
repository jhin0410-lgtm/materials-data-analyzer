from __future__ import annotations

import hashlib
import json

import materials_data_analyzer.research_loop.recursive_research_cycle_rediagnosis as rediagnosis
from materials_data_analyzer.research_loop.recursive_research_cycle_controller import (
    build_recursive_research_cycle_checkpoint,
)
from materials_data_analyzer.research_loop.recursive_research_cycle_evidence import (
    advance_recursive_cycle_after_verified_transition,
)
from materials_data_analyzer.research_loop.recursive_research_cycle_rediagnosis import (
    complete_recursive_cycle_with_rediagnosis,
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


def test_discrepancy_to_fresh_plan_to_verified_transition_to_rediagnosis(monkeypatch) -> None:
    target = {
        "graph_id": "g-recursive",
        "node_id": "h-recursive",
        "node_type": "hypothesis",
        "statement": "A bounded model hypothesis remains under discrimination.",
    }
    previous_report = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "target": dict(target),
    }
    previous_report["report_sha256"] = _sha(previous_report)

    handoff = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_discrepancy_report_sha256": previous_report["report_sha256"],
        "target": dict(target),
        "research_objectives": [
            {
                "objective_id": "planning-objective:model-evidence:sensitivity",
                "source_proposal_id": "model-evidence:sensitivity",
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
    handoff["handoff_sha256"] = _sha(handoff)

    candidate = {
        "action_id": "planner:sensitivity",
        "action_class": "sensitivity_analysis",
        "execution_mode": "plan_only",
        "automatic_execution_authorized": False,
    }
    plan = {
        "schema_version": "1.0",
        "ranked_actions": [dict(candidate)],
        "selected_next_action": dict(candidate),
        "stop_decision": {"stop": False},
        "handoff": {"request_compiled": False, "execution_performed": False},
        "autonomy_boundary": {
            "empirical_evidence_created": False,
            "network_access_performed": False,
            "physical_experiment_execution_performed": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
            "mission_mutated": False,
        },
    }
    plan["plan_sha256"] = _sha(plan)
    match = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "handoff_sha256": handoff["handoff_sha256"],
        "fresh_plan_sha256": plan["plan_sha256"],
        "objective_id": handoff["research_objectives"][0]["objective_id"],
        "source_proposal_id": "model-evidence:sensitivity",
        "source_rank": 1,
        "candidate_action_id": "planner:sensitivity",
        "candidate_action_class": "sensitivity_analysis",
        "candidate_execution_mode": "plan_only",
        "match_rationale": "Fresh planner independently selected the same action class.",
    }
    checkpoint = build_recursive_research_cycle_checkpoint(
        planning_handoff=handoff,
        fresh_plan=plan,
        candidate_match=match,
    )
    assert checkpoint["checkpoint_status"] == "explicit_authorization_required"

    execution = {
        "schema_version": "1.0",
        "source_checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "authorization_status": "explicit_request_authorized_by_existing_chain",
        "independent_verification_status": "verified_by_existing_chain",
        "action_id": "action-verified",
        "action_type": "sensitivity_analysis",
        "action_version": "1.0",
        "request_sha256": "1" * 64,
        "registry_sha256": "2" * 64,
        "result_sha256": "3" * 64,
        "execution_outcome": "completed",
        "execution_success": True,
        "scientific_evidence_upgraded": False,
    }
    execution["verification_record_sha256"] = _sha(execution)
    graph = {
        "graph_id": target["graph_id"],
        "nodes": [dict(target, node_id=target["node_id"])],
        "assessments": [
            {
                "node_id": target["node_id"],
                "status": "inconclusive",
            }
        ],
    }
    transition = {
        "schema_version": "1.0",
        "verified_execution_record_sha256": execution["verification_record_sha256"],
        "evaluated_graph_canonical_sha256": _sha(graph),
        "target_node_id": target["node_id"],
        "transition_id": "transition-verified",
        "consumer_verification_sha256": "4" * 64,
        "consumer_verification_status": "verified_by_authenticated_transition_consumer",
        "execution_completion_treated_as_scientific_support": False,
    }
    transition["transition_record_sha256"] = _sha(transition)
    portfolio = {
        "graph_id": target["graph_id"],
        "evaluated_graph_binding": {"canonical_sha256": _sha(graph)},
        "hypotheses": [
            {
                "hypothesis_id": target["node_id"],
                "statement": target["statement"],
                "epistemic_status": "inconclusive",
                "portfolio_state": "active_discrimination_required",
                "research_directive": "continue_discriminating_research",
            }
        ],
    }
    portfolio["portfolio_sha256"] = _sha(portfolio)
    progression = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=execution,
        epistemic_transition_record=transition,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
    )
    assert progression["progression_status"] == "re_diagnosis_required"

    current_report = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "target": dict(target),
        "input_bindings": {
            "previous_discrepancy_report": {
                "report_sha256": previous_report["report_sha256"],
            }
        },
    }
    current_report_sha = "5" * 64
    monkeypatch.setattr(
        rediagnosis,
        "validate_model_evidence_discrepancy_report",
        lambda *args, **kwargs: {
            "report_sha256": current_report_sha,
            "iteration_index": 2,
            "diagnosis_types": ["empirical_model_discrepancy"],
        },
    )

    next_handoff = {
        "schema_version": "1.0",
        "source_discrepancy_report_sha256": current_report_sha,
        "research_objectives": [{"objective_id": "planning-objective:next"}],
        "planner_boundary": {
            "fresh_planner_candidate_matching_required": True,
            "automatic_execution_authorized": False,
        },
    }
    next_handoff["handoff_sha256"] = _sha(next_handoff)
    monkeypatch.setattr(
        rediagnosis,
        "build_discrepancy_planning_handoff",
        lambda *args, **kwargs: next_handoff,
    )

    completed = complete_recursive_cycle_with_rediagnosis(
        authorization_checkpoint=checkpoint,
        progression=progression,
        current_discrepancy_report=current_report,
        previous_discrepancy_report=previous_report,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
    )
    assert completed["completion_status"] == "next_planning_handoff_ready"
    assert completed["validated_rediagnosis"]["iteration_index"] == 2
    assert completed["next_planning_handoff"]["planner_boundary"][
        "fresh_planner_candidate_matching_required"
    ] is True
    assert completed["autonomy_boundary"]["planner_candidate_created"] is False
    assert completed["autonomy_boundary"]["authorization_granted"] is False
    assert completed["autonomy_boundary"]["execution_performed"] is False
    assert completed["autonomy_boundary"]["scientific_status_changed"] is False
