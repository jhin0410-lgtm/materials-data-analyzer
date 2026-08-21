from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    apply_authenticated_epistemic_transition_files,
)
from materials_data_analyzer.research_loop.recursive_research_cycle_evidence import (
    RecursiveResearchEvidenceError,
    _advance_recursive_cycle_after_verified_transition as advance_recursive_cycle_after_verified_transition,
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


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _plan(action_id: str = "planner:sensitivity") -> dict:
    selected = {
        "action_id": action_id,
        "action_class": "sensitivity_analysis",
        "action_kind": "analysis",
        "description": "Run bounded sensitivity analysis.",
        "rationale": "Discriminate the bounded target.",
        "required_evidence": [],
        "expected_outcome": "A bounded verified result.",
        "execution_mode": "plan_only",
        "origin": "verified_goal_frontier",
        "expected_information_score": 0.8,
        "hypothesis_discrimination_score": 0.8,
        "feasibility_score": 0.9,
        "cost_units": 1.0,
        "risk_penalty": 0.0,
        "utility_score": 0.576,
        "utility_is_calibrated_probability": False,
        "automatic_execution_authorized": False,
        "physical_experiment_execution_authorized": False,
    }
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
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
    value["plan_sha256"] = _sha(value)
    return value


def _checkpoint(plan: dict) -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "cycle_id": "recursive:graph-v1:h-1",
        "cycle_index": 1,
        "checkpoint_status": "explicit_authorization_required",
        "target": {
            "graph_id": "graph-v1",
            "node_id": "h-1",
            "node_type": "hypothesis",
            "statement": "The bounded target remains under discrimination.",
        },
        "ancestry": {
            "previous_checkpoint_sha256": None,
            "source_discrepancy_report_sha256": "b" * 64,
            "planning_handoff_sha256": "c" * 64,
            "fresh_plan_sha256": plan["plan_sha256"],
        },
        "fresh_planner_state": {
            "ranked_candidate_count": 1,
            "selected_candidate_id": "planner:sensitivity",
            "stop_decision": dict(plan["stop_decision"]),
        },
        "matched_objective": {"objective_id": "planning-objective:1"},
        "candidate_match": {
            "candidate_action_id": "planner:sensitivity",
            "candidate_action_class": "sensitivity_analysis",
        },
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
    value["checkpoint_sha256"] = _sha(value)
    return value


def _bundle(tmp_path: Path, *, source_action_id: str = "planner:sensitivity", falsified: bool = False) -> tuple[Path, str]:
    result = tmp_path / "result.json"
    result_sha = _write_json(result, {"sensitivity": 0.25})
    prior_result_sha = _write_json(tmp_path / "prior-result.json", {"prior": True})
    prior_verifier_sha = _write_json(tmp_path / "prior-verifier.json", {"verified": True})
    nodes: list[dict] = [
        {
            "node_id": "h-1",
            "node_type": "hypothesis",
            "statement": "The bounded target remains under discrimination.",
            "metadata": {"claim_scope": "structural"},
        }
    ]
    edges: list[dict] = []
    if falsified:
        nodes.append(
            {
                "node_id": "prior-analysis",
                "node_type": "analysis",
                "statement": "Prior verified analysis falsified the target in scope.",
                "execution_status": "completed",
                "artifact_bindings": [
                    {
                        "role": "primary_result",
                        "path": "prior-result.json",
                        "sha256": prior_result_sha,
                    }
                ],
                "metadata": {"result_origin": "authorized_local_analysis"},
            }
        )
        edges.append(
            {
                "edge_id": "prior-falsification",
                "source_node_id": "prior-analysis",
                "target_node_id": "h-1",
                "relation": "falsifies",
                "assessment_level": "domain_verified",
                "rationale": "Prior exact verifier established falsification in scope.",
                "active": True,
                "verification_artifact": {
                    "role": "domain_verification_decision",
                    "path": "prior-verifier.json",
                    "sha256": prior_verifier_sha,
                },
            }
        )
    base_graph = {
        "schema_version": "1.0",
        "graph_id": "graph-v1",
        "research_scope": "recursive evidence regression",
        "nodes": nodes,
        "edges": edges,
    }
    base = tmp_path / "base.json"
    base_sha = _write_json(base, base_graph)
    proposal = {
        "schema_version": "1.0",
        "transition_id": "transition-1",
        "base_graph_id": "graph-v1",
        "base_graph_sha256": base_sha,
        "new_graph_id": "graph-v2",
        "target_node_id": "h-1",
        "source_action": {
            "action_id": source_action_id,
            "action_class": "sensitivity_analysis",
            "action_version": "1.0",
            "execution_mode": "typed_local_action",
        },
        "result_node": {
            "node_id": "result-1",
            "node_type": "analysis",
            "statement": "A bounded sensitivity analysis completed.",
            "artifact_bindings": [
                {"role": "primary_result", "path": "result.json", "sha256": result_sha}
            ],
            "metadata": {"result_origin": "authorized_local_analysis"},
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": "tests-1",
            "inference_edge_id": "inference-1",
            "relation": "supports",
            "rationale": "The result is diagnostic for the structural target.",
        },
        "limitations": ["No positive scientific closeout is granted."],
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_sha = _write_json(proposal_path, proposal)
    verification = {
        "schema_version": "1.1",
        "decision_id": "verification-1",
        "transition_id": "transition-1",
        "proposal_sha256": proposal_sha,
        "base_graph_sha256": base_sha,
        "inference_edge_id": "inference-1",
        "result_node_id": "result-1",
        "target_node_id": "h-1",
        "relation": "supports",
        "inference_scope": "structural",
        "verifier_id": "bounded-domain-verifier-v1.1",
        "rationale": "Exact edge verification is structural only.",
        "limitations": ["No positive closeout is granted."],
        "domain_verified": True,
    }
    verification_path = tmp_path / "verification.json"
    _write_json(verification_path, verification)
    output = tmp_path / "bundle"
    apply_authenticated_epistemic_transition_files(
        base_graph_path=base,
        proposal_path=proposal_path,
        verification_decision_path=verification_path,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
        output_dir=output,
    )
    # The authenticated successor graph retains historical artifact paths. Materialize
    # the exact bound historical bytes inside the published bundle so the independent
    # consumer can revalidate them rather than relying on the producer workspace.
    (output / "prior-result.json").write_bytes((tmp_path / "prior-result.json").read_bytes())
    (output / "prior-verifier.json").write_bytes(
        (tmp_path / "prior-verifier.json").read_bytes()
    )
    return output, result_sha


def _execution(checkpoint: dict, result_sha: str, *, action_id: str = "planner:sensitivity") -> dict:
    value = {
        "schema_version": "1.0",
        "source_checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "authorization_status": "explicit_request_authorized_by_existing_chain",
        "independent_verification_status": "verified_by_existing_chain",
        "action_id": action_id,
        "action_type": "sensitivity_analysis",
        "action_version": "1.0",
        "request_sha256": "d" * 64,
        "registry_sha256": "e" * 64,
        "result_sha256": result_sha,
        "execution_outcome": "completed",
        "execution_success": True,
        "scientific_evidence_upgraded": False,
    }
    value["verification_record_sha256"] = _sha(value)
    return value


def test_real_authenticated_transition_refreshes_authoritative_portfolio(tmp_path: Path) -> None:
    plan = _plan()
    checkpoint = _checkpoint(plan)
    bundle, result_sha = _bundle(tmp_path)
    result = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=_execution(checkpoint, result_sha),
        transition_bundle_root=bundle,
        fresh_plan=plan,
        program_state={"workstreams": []},
    )
    assert result["progression_status"] == "re_diagnosis_required"
    assert result["source_target"]["graph_id"] == "graph-v1"
    assert result["target"]["graph_id"] == "graph-v2"
    assert result["verified_epistemic_transition"][
        "current_transition_exact_provenance_authenticated"
    ] is True
    assert result["target_hypothesis_portfolio_state"]["portfolio_state"] == (
        "active_discrimination_required"
    )
    assert result["autonomy_boundary"]["scientific_status_changed_by_controller"] is False


def test_executed_action_must_equal_planner_selected_checkpoint_action(tmp_path: Path) -> None:
    plan = _plan()
    checkpoint = _checkpoint(plan)
    bundle, result_sha = _bundle(tmp_path)
    with pytest.raises(RecursiveResearchEvidenceError, match="action_id does not match"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=_execution(
                checkpoint, result_sha, action_id="different-action"
            ),
            transition_bundle_root=bundle,
            fresh_plan=plan,
            program_state={"workstreams": []},
        )


def test_authenticated_transition_action_must_equal_verified_execution(tmp_path: Path) -> None:
    plan = _plan()
    checkpoint = _checkpoint(plan)
    bundle, result_sha = _bundle(tmp_path, source_action_id="different-action")
    with pytest.raises(RecursiveResearchEvidenceError, match="proposal action_id differs"):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=_execution(checkpoint, result_sha),
            transition_bundle_root=bundle,
            fresh_plan=plan,
            program_state={"workstreams": []},
        )


def test_falsified_state_is_derived_and_stops_without_caller_portfolio(tmp_path: Path) -> None:
    plan = _plan()
    checkpoint = _checkpoint(plan)
    bundle, result_sha = _bundle(tmp_path, falsified=True)
    result = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=_execution(checkpoint, result_sha),
        transition_bundle_root=bundle,
        fresh_plan=plan,
        program_state={"workstreams": []},
    )
    assert result["progression_status"] == "bounded_stop_hypothesis_retired"
    assert result["target_epistemic_assessment"]["status"] == (
        "falsified_within_verified_scope"
    )
    assert result["target_hypothesis_portfolio_state"]["portfolio_state"] == (
        "retired_falsified_within_verified_scope"
    )


def test_cycle_one_rejects_predecessor_progression(tmp_path: Path) -> None:
    plan = _plan()
    checkpoint = _checkpoint(plan)
    bundle, result_sha = _bundle(tmp_path)
    execution = _execution(checkpoint, result_sha)
    first = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=execution,
        transition_bundle_root=bundle,
        fresh_plan=plan,
        program_state={"workstreams": []},
    )
    with pytest.raises(
        RecursiveResearchEvidenceError,
        match="cycle-one progression cannot accept a predecessor progression",
    ):
        advance_recursive_cycle_after_verified_transition(
            authorization_checkpoint=checkpoint,
            verified_execution_record=execution,
            transition_bundle_root=bundle,
            fresh_plan=plan,
            program_state={"workstreams": []},
            previous_progression=first,
        )
