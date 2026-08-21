from __future__ import annotations

import copy
import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.recursive_research_cycle_evidence import (
    RecursiveResearchEvidenceError,
    advance_recursive_cycle_after_verified_transition,
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


def _checkpoint() -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "cycle_id": "recursive:g-1:h-1",
        "cycle_index": 1,
        "checkpoint_status": "explicit_authorization_required",
        "target": {
            "graph_id": "g-1",
            "node_id": "h-1",
            "node_type": "hypothesis",
            "statement": "The declared model remains adequate within the verified scope.",
        },
        "ancestry": {
            "previous_checkpoint_sha256": None,
            "source_discrepancy_report_sha256": "a" * 64,
            "planning_handoff_sha256": "b" * 64,
            "fresh_plan_sha256": "c" * 64,
        },
        "fresh_planner_state": {
            "ranked_candidate_count": 1,
            "selected_candidate_id": "planner:sensitivity-1",
            "stop_decision": {"stop": False},
        },
        "matched_objective": {"objective_id": "planning-objective:1"},
        "candidate_match": {"candidate_action_id": "planner:sensitivity-1"},
        "authorization_handoff": {
            "required": True,
            "destination": "existing_independent_action_authorization_and_typed_executor_chain",
            "authorization_granted": False,
            "request_compiled": False,
            "execution_performed": False,
        },
        "epistemic_handoff": {
            "execution_result_verified": False,
            "epistemic_interpretation_performed": False,
            "epistemic_transition_verified": False,
            "hypothesis_portfolio_refreshed": False,
            "re_diagnosis_performed": False,
        },
        "bounded_stop": {"stopped": False, "reason": None, "reopen_condition": None},
        "autonomy_boundary": {
            "critic_proposal_executed_directly": False,
            "planner_candidate_injected": False,
            "action_type_synthesized": False,
            "registry_synthesized": False,
            "availability_promoted": False,
            "authorization_granted": False,
            "automatic_execution_authorized": False,
            "execution_performed": False,
            "network_access_performed": False,
            "physical_experiment_executed": False,
            "empirical_evidence_created": False,
            "epistemic_edge_created": False,
            "scientific_status_changed": False,
        },
    }
    value["checkpoint_sha256"] = _canonical_sha(value)
    return value


def _execution(checkpoint: dict, *, outcome: str = "completed", success: bool = True) -> dict:
    value = {
        "schema_version": "1.0",
        "source_checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "authorization_status": "explicit_request_authorized_by_existing_chain",
        "independent_verification_status": "verified_by_existing_chain",
        "action_id": "action-1",
        "action_type": "sensitivity_analysis",
        "action_version": "1.0",
        "request_sha256": "d" * 64,
        "registry_sha256": "e" * 64,
        "result_sha256": "f" * 64,
        "execution_outcome": outcome,
        "execution_success": success,
        "scientific_evidence_upgraded": False,
    }
    value["verification_record_sha256"] = _canonical_sha(value)
    return value


def _graph(*, status: str = "inconclusive", graph_id: str = "g-1") -> dict:
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "graph_id": graph_id,
        "research_scope": "bounded recursive controller test",
        "nodes": [
            {
                "node_id": "h-1",
                "node_type": "hypothesis",
                "statement": "The declared model remains adequate within the verified scope.",
            }
        ],
        "edges": [],
        "assessments": [
            {
                "node_id": "h-1",
                "node_type": "hypothesis",
                "status": status,
                "verified_support_edges": [],
                "verified_contradiction_edges": [],
                "verified_falsification_edges": [],
                "diagnostic_relation_edges": [],
                "final_positive_support_granted": False,
                "confidence_score": None,
            }
        ],
    }


def _transition(execution: dict, graph: dict) -> dict:
    value = {
        "schema_version": "1.0",
        "verified_execution_record_sha256": execution["verification_record_sha256"],
        "evaluated_graph_canonical_sha256": _canonical_sha(graph),
        "target_node_id": "h-1",
        "transition_id": "transition-1",
        "consumer_verification_sha256": "1" * 64,
        "consumer_verification_status": "verified_by_authenticated_transition_consumer",
        "execution_completion_treated_as_scientific_support": False,
    }
    value["transition_record_sha256"] = _canonical_sha(value)
    return value


def _portfolio(graph: dict, *, state: str = "active_discrimination_required") -> dict:
    status = graph["assessments"][0]["status"]
    directive = {
        "active_discrimination_required": "continue_discriminating_research",
        "positive_closeout_required": "seek_domain_closeout_no_auto_promotion",
        "challenge_or_retirement_review": "seek_replication_or_scope_review",
        "retired_falsified_within_verified_scope": "do_not_repeat_without_new_hypothesis_identity",
    }[state]
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "graph_id": graph["graph_id"],
        "research_scope": graph["research_scope"],
        "evaluated_graph_binding": {"canonical_sha256": _canonical_sha(graph)},
        "plan_binding": {"plan_sha256": "2" * 64},
        "previous_portfolio_sha256": None,
        "hypothesis_count": 1,
        "state_counts": {state: 1},
        "portfolio_directive": "continue_bounded_discrimination",
        "hypotheses": [
            {
                "hypothesis_id": "h-1",
                "statement": graph["nodes"][0]["statement"],
                "epistemic_status": status,
                "portfolio_state": state,
                "research_directive": directive,
                "verified_support_edges": [],
                "verified_contradiction_edges": [],
                "verified_falsification_edges": [],
                "diagnostic_relation_edges": [],
                "final_positive_support_granted": False,
                "confidence_score": None,
                "transition": "entered_from_current_verified_graph",
            }
        ],
        "autonomy_boundary": {
            "scientific_status_changed": False,
            "automatic_execution_authorized": False,
        },
    }
    value["portfolio_sha256"] = _canonical_sha(value)
    return value


def test_verified_execution_graph_transition_and_portfolio_require_rediagnosis() -> None:
    checkpoint = _checkpoint()
    execution = _execution(checkpoint)
    graph = _graph()
    transition = _transition(execution, graph)
    portfolio = _portfolio(graph)

    result = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=execution,
        epistemic_transition_record=transition,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
    )
    assert result["progression_status"] == "re_diagnosis_required"
    assert result["re_diagnosis"]["required"] is True
    assert result["re_diagnosis"]["performed"] is False
    assert result["autonomy_boundary"]["execution_performed_by_controller"] is False
    assert result["autonomy_boundary"]["epistemic_edge_created_by_controller"] is False
    assert result["autonomy_boundary"]["scientific_status_changed_by_controller"] is False


def test_rejected_or_failed_execution_cannot_be_marked_success() -> None:
    checkpoint = _checkpoint()
    graph = _graph()

    rejected = _execution(checkpoint, outcome="rejected", success=True)
    transition = _transition(rejected, graph)
    with pytest.raises(RecursiveResearchEvidenceError, match="cannot be represented"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=rejected,
            epistemic_transition_record=transition,
            evaluated_graph=graph,
            hypothesis_portfolio=_portfolio(graph),
        )

    failed = _execution(checkpoint, outcome="failed", success=True)
    transition = _transition(failed, graph)
    with pytest.raises(RecursiveResearchEvidenceError, match="cannot be represented"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=failed,
            epistemic_transition_record=transition,
            evaluated_graph=graph,
            hypothesis_portfolio=_portfolio(graph),
        )


def test_graph_transition_and_portfolio_sha_substitution_fail_closed() -> None:
    checkpoint = _checkpoint()
    execution = _execution(checkpoint)
    graph = _graph()
    transition = _transition(execution, graph)
    portfolio = _portfolio(graph)

    wrong_transition = copy.deepcopy(transition)
    wrong_transition.pop("transition_record_sha256")
    wrong_transition["evaluated_graph_canonical_sha256"] = "9" * 64
    wrong_transition["transition_record_sha256"] = _canonical_sha(wrong_transition)
    with pytest.raises(RecursiveResearchEvidenceError, match="different evaluated graph"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=execution,
            epistemic_transition_record=wrong_transition,
            evaluated_graph=graph,
            hypothesis_portfolio=portfolio,
        )

    wrong_portfolio = copy.deepcopy(portfolio)
    wrong_portfolio.pop("portfolio_sha256")
    wrong_portfolio["evaluated_graph_binding"]["canonical_sha256"] = "8" * 64
    wrong_portfolio["portfolio_sha256"] = _canonical_sha(wrong_portfolio)
    with pytest.raises(RecursiveResearchEvidenceError, match="not bound"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=execution,
            epistemic_transition_record=transition,
            evaluated_graph=graph,
            hypothesis_portfolio=wrong_portfolio,
        )


def test_falsified_hypothesis_remains_retired_and_stops_recursion() -> None:
    checkpoint = _checkpoint()
    execution = _execution(checkpoint)
    graph = _graph(status="falsified_within_verified_scope")
    transition = _transition(execution, graph)
    portfolio = _portfolio(graph, state="retired_falsified_within_verified_scope")

    result = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=execution,
        epistemic_transition_record=transition,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
    )
    assert result["progression_status"] == "bounded_stop_hypothesis_retired"
    assert result["re_diagnosis"]["required"] is False
    assert result["bounded_stop"]["stopped"] is True
    assert result["target_hypothesis_portfolio_state"]["portfolio_state"] == (
        "retired_falsified_within_verified_scope"
    )


def test_recursive_progression_detects_no_new_graph_information() -> None:
    checkpoint = _checkpoint()
    execution = _execution(checkpoint)
    graph = _graph()
    transition = _transition(execution, graph)
    portfolio = _portfolio(graph)
    first = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=execution,
        epistemic_transition_record=transition,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
    )

    with pytest.raises(RecursiveResearchEvidenceError, match="no new evaluated graph"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=execution,
            epistemic_transition_record=transition,
            evaluated_graph=graph,
            hypothesis_portfolio=portfolio,
            previous_progression=first,
        )


def test_progression_target_graph_and_status_substitution_fail_closed() -> None:
    checkpoint = _checkpoint()
    execution = _execution(checkpoint)
    wrong_graph = _graph(graph_id="g-2")
    transition = _transition(execution, wrong_graph)

    with pytest.raises(RecursiveResearchEvidenceError, match="graph identity changed"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=execution,
            epistemic_transition_record=transition,
            evaluated_graph=wrong_graph,
            hypothesis_portfolio=_portfolio(wrong_graph),
        )

    graph = _graph(status="inconclusive")
    transition = _transition(execution, graph)
    portfolio = _portfolio(graph)
    portfolio.pop("portfolio_sha256")
    portfolio["hypotheses"][0]["epistemic_status"] = "provisionally_supported"
    portfolio["portfolio_sha256"] = _canonical_sha(portfolio)
    with pytest.raises(RecursiveResearchEvidenceError, match="does not match"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=execution,
            epistemic_transition_record=transition,
            evaluated_graph=graph,
            hypothesis_portfolio=portfolio,
        )
