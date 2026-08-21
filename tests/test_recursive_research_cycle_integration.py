from __future__ import annotations

import hashlib
import json
from pathlib import Path

import materials_data_analyzer.research_loop.recursive_research_cycle_rediagnosis as rediagnosis
from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    apply_authenticated_epistemic_transition_files,
)
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
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_real_transition_bundle_closes_one_recursive_cycle(tmp_path: Path, monkeypatch) -> None:
    target = {
        "graph_id": "graph-v1",
        "node_id": "h-1",
        "node_type": "hypothesis",
        "statement": "A bounded hypothesis remains under discrimination.",
    }
    previous_report = {"schema_version": "1.0", "policy_version": "1.0", "target": target}
    previous_report["report_sha256"] = _sha(previous_report)
    handoff = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_discrepancy_report_sha256": previous_report["report_sha256"],
        "target": target,
        "research_objectives": [
            {
                "objective_id": "planning-objective:sensitivity",
                "source_proposal_id": "model-evidence:sensitivity",
                "source_rank": 1,
                "research_action_class": "sensitivity_analysis",
                "planner_candidate_required": True,
                "availability_asserted": False,
                "automatic_execution_authorized": False,
            }
        ],
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
    handoff["handoff_sha256"] = _sha(handoff)
    candidate = {
        "action_id": "planner:sensitivity",
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
    plan = {
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
        "ranked_actions": [candidate],
        "selected_next_action": dict(candidate),
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
    plan["plan_sha256"] = _sha(plan)
    match = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "handoff_sha256": handoff["handoff_sha256"],
        "fresh_plan_sha256": plan["plan_sha256"],
        "objective_id": "planning-objective:sensitivity",
        "source_proposal_id": "model-evidence:sensitivity",
        "source_rank": 1,
        "candidate_action_id": "planner:sensitivity",
        "candidate_action_class": "sensitivity_analysis",
        "candidate_execution_mode": "plan_only",
        "match_rationale": "Fresh planner selected the same bounded action class.",
    }
    checkpoint = build_recursive_research_cycle_checkpoint(
        planning_handoff=handoff,
        fresh_plan=plan,
        candidate_match=match,
    )

    result_path = tmp_path / "result.json"
    result_sha = _write_json(result_path, {"sensitivity": 0.25})
    base_path = tmp_path / "base.json"
    base_sha = _write_json(
        base_path,
        {
            "schema_version": "1.0",
            "graph_id": "graph-v1",
            "research_scope": "recursive integration",
            "nodes": [
                {
                    "node_id": "h-1",
                    "node_type": "hypothesis",
                    "statement": target["statement"],
                    "metadata": {"claim_scope": "structural"},
                }
            ],
            "edges": [],
        },
    )
    proposal_path = tmp_path / "proposal.json"
    proposal = {
        "schema_version": "1.0",
        "transition_id": "transition-1",
        "base_graph_id": "graph-v1",
        "base_graph_sha256": base_sha,
        "new_graph_id": "graph-v2",
        "target_node_id": "h-1",
        "source_action": {
            "action_id": "planner:sensitivity",
            "action_class": "sensitivity_analysis",
            "action_version": "1.0",
            "execution_mode": "typed_local_action",
        },
        "result_node": {
            "node_id": "result-1",
            "node_type": "analysis",
            "statement": "A bounded sensitivity result completed.",
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
            "rationale": "The bounded result is diagnostic for the target.",
        },
        "limitations": ["No automatic scientific closeout."],
    }
    proposal_sha = _write_json(proposal_path, proposal)
    verification_path = tmp_path / "verification.json"
    _write_json(
        verification_path,
        {
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
            "rationale": "Exact edge is verified in structural scope only.",
            "limitations": ["No positive closeout."],
            "domain_verified": True,
        },
    )
    bundle = tmp_path / "bundle"
    apply_authenticated_epistemic_transition_files(
        base_graph_path=base_path,
        proposal_path=proposal_path,
        verification_decision_path=verification_path,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
        output_dir=bundle,
    )
    execution = {
        "schema_version": "1.0",
        "source_checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "authorization_status": "explicit_request_authorized_by_existing_chain",
        "independent_verification_status": "verified_by_existing_chain",
        "action_id": "planner:sensitivity",
        "action_type": "sensitivity_analysis",
        "action_version": "1.0",
        "request_sha256": "1" * 64,
        "registry_sha256": "2" * 64,
        "result_sha256": result_sha,
        "execution_outcome": "completed",
        "execution_success": True,
        "scientific_evidence_upgraded": False,
    }
    execution["verification_record_sha256"] = _sha(execution)
    progression = advance_recursive_cycle_after_verified_transition(
        authorization_checkpoint=checkpoint,
        verified_execution_record=execution,
        transition_bundle_root=bundle,
        fresh_plan=plan,
        program_state={"workstreams": []},
    )
    assert progression["target"]["graph_id"] == "graph-v2"
    assert progression["progression_status"] == "re_diagnosis_required"

    current_target = progression["target"]
    current_report = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "target": dict(current_target),
        "input_bindings": {
            "previous_discrepancy_report": {
                "report_sha256": previous_report["report_sha256"],
            }
        },
    }
    current_report_sha = "5" * 64
    monkeypatch.setattr(
        rediagnosis,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        lambda *args, **kwargs: {
            "report_sha256": current_report_sha,
            "iteration_index": 2,
            "diagnosis_types": ["empirical_model_discrepancy"],
        },
    )
    next_handoff = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_discrepancy_report_sha256": current_report_sha,
        "target": dict(current_target),
        "research_objectives": [{"objective_id": "planning-objective:next"}],
        "source_ancestry": {
            "previous_discrepancy_report_sha256": previous_report["report_sha256"]
        },
        "planner_boundary": {
            "fresh_planner_candidate_matching_required": True,
            "automatic_execution_authorized": False,
        },
    }
    next_handoff["handoff_sha256"] = _sha(next_handoff)
    monkeypatch.setattr(
        rediagnosis,
        "build_policy_hardened_discrepancy_planning_handoff",
        lambda *args, **kwargs: next_handoff,
    )
    graph_sha = progression["ancestry"]["evaluated_graph_canonical_sha256"]
    # Re-evaluate through the same exact bundle by reusing the internally produced graph.
    # The authoritative portfolio embeds the exact evaluated graph binding; construct the
    # same evaluated representation from the transition bundle for the re-diagnosis step.
    from materials_data_analyzer.research_loop.epistemic_graph import (
        evaluate_epistemic_graph,
    )

    raw_graph = json.loads((bundle / "epistemic_graph.json").read_text(encoding="utf-8"))
    evaluated_graph = evaluate_epistemic_graph(
        raw_graph,
        program_state={"workstreams": []},
        artifact_root=bundle,
    )
    assert _sha(evaluated_graph) == graph_sha
    completed = complete_recursive_cycle_with_rediagnosis(
        authorization_checkpoint=checkpoint,
        progression=progression,
        current_discrepancy_report=current_report,
        previous_discrepancy_report=previous_report,
        evaluated_graph=evaluated_graph,
    )
    assert completed["completion_status"] == "next_planning_handoff_ready"
    assert completed["target"]["graph_id"] == "graph-v2"
    assert completed["ancestry"]["previous_discrepancy_report_sha256"] == (
        previous_report["report_sha256"]
    )
    assert completed["autonomy_boundary"]["authorization_granted"] is False
    assert completed["autonomy_boundary"]["execution_performed"] is False
    assert completed["autonomy_boundary"]["scientific_status_changed"] is False
