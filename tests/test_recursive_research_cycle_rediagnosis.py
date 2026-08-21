from __future__ import annotations

import hashlib
import json

import pytest

import materials_data_analyzer.research_loop.recursive_research_cycle_rediagnosis as rediagnosis
from materials_data_analyzer.research_loop.model_evidence_discrepancy_physics_policy import (
    ModelEvidenceDiscrepancyPhysicsPolicyError,
)
from materials_data_analyzer.research_loop.recursive_research_cycle_rediagnosis import (
    RecursiveResearchRediagnosisError,
    complete_recursive_cycle_with_rediagnosis,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _state() -> tuple[dict, dict, dict, dict]:
    source_target = {
        "graph_id": "graph-v1",
        "node_id": "h-1",
        "node_type": "hypothesis",
        "statement": "Bounded target statement.",
    }
    current_target = dict(source_target)
    current_target["graph_id"] = "graph-v2"
    previous = {"schema_version": "1.0", "policy_version": "1.0", "target": source_target}
    previous["report_sha256"] = _sha(previous)
    checkpoint = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "cycle_id": "recursive:graph-v1:h-1",
        "cycle_index": 1,
        "checkpoint_status": "explicit_authorization_required",
        "target": source_target,
        "ancestry": {"source_discrepancy_report_sha256": previous["report_sha256"]},
    }
    checkpoint["checkpoint_sha256"] = _sha(checkpoint)
    graph = {
        "graph_id": "graph-v2",
        "research_scope": "recursive re-diagnosis",
        "nodes": [
            {
                "node_id": "h-1",
                "node_type": "hypothesis",
                "statement": "Bounded target statement.",
            }
        ],
        "edges": [],
        "assessments": [
            {
                "node_id": "h-1",
                "node_type": "hypothesis",
                "status": "inconclusive",
                "verified_support_edges": [],
                "verified_contradiction_edges": [],
                "verified_falsification_edges": [],
                "diagnostic_relation_edges": [],
                "final_positive_support_granted": False,
                "confidence_score": None,
            }
        ],
    }
    portfolio = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "graph_id": "graph-v2",
        "research_scope": "recursive re-diagnosis",
        "evaluated_graph_binding": {"canonical_sha256": _sha(graph)},
        "plan_binding": {"plan_sha256": "1" * 64},
        "previous_portfolio_sha256": None,
        "hypothesis_count": 1,
        "state_counts": {"active_discrimination_required": 1},
        "portfolio_directive": "continue_bounded_discrimination",
        "hypotheses": [
            {
                "hypothesis_id": "h-1",
                "statement": "Bounded target statement.",
                "epistemic_status": "inconclusive",
                "portfolio_state": "active_discrimination_required",
                "research_directive": "continue_discriminating_research",
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
            "numeric_belief_probability_assigned": False,
            "final_positive_support_granted": False,
            "empirical_evidence_created": False,
            "domain_mechanism_invented": False,
            "scientific_status_changed": False,
            "execution_authorized": False,
            "physical_experiment_executed": False,
        },
    }
    portfolio["portfolio_sha256"] = _sha(portfolio)
    progression = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "cycle_id": checkpoint["cycle_id"],
        "cycle_index": 1,
        "progression_status": "re_diagnosis_required",
        "source_target": source_target,
        "target": current_target,
        "ancestry": {
            "authorization_checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "evaluated_graph_canonical_sha256": _sha(graph),
            "hypothesis_portfolio_sha256": portfolio["portfolio_sha256"],
        },
        "hypothesis_portfolio": portfolio,
    }
    progression["progression_sha256"] = _sha(progression)
    return previous, checkpoint, graph, progression


def _current(previous: dict, target: dict) -> dict:
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "target": dict(target),
        "input_bindings": {
            "previous_discrepancy_report": {
                "report_sha256": previous["report_sha256"],
            }
        },
    }


def _handoff(current_sha: str, target: dict, previous_sha: str) -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_discrepancy_report_sha256": current_sha,
        "target": dict(target),
        "research_objectives": [{"objective_id": "planning-objective:next"}],
        "source_ancestry": {"previous_discrepancy_report_sha256": previous_sha},
        "planner_boundary": {
            "fresh_planner_candidate_matching_required": True,
            "automatic_execution_authorized": False,
        },
    }
    value["handoff_sha256"] = _sha(value)
    return value


def test_rediagnosis_uses_physics_hardened_validator_and_handoff(monkeypatch) -> None:
    previous, checkpoint, graph, progression = _state()
    target = progression["target"]
    current = _current(previous, target)
    current_sha = "e" * 64
    calls = {"physics": 0, "handoff": 0}

    def verify(*args, **kwargs):
        calls["physics"] += 1
        return {
            "report_sha256": current_sha,
            "iteration_index": 2,
            "diagnosis_types": ["parameter_or_property_uncertainty"],
        }

    def build(*args, **kwargs):
        calls["handoff"] += 1
        return _handoff(current_sha, target, previous["report_sha256"])

    monkeypatch.setattr(
        rediagnosis,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        verify,
    )
    monkeypatch.setattr(
        rediagnosis,
        "build_policy_hardened_discrepancy_planning_handoff",
        build,
    )
    result = complete_recursive_cycle_with_rediagnosis(
        authorization_checkpoint=checkpoint,
        progression=progression,
        current_discrepancy_report=current,
        previous_discrepancy_report=previous,
        evaluated_graph=graph,
    )
    assert calls == {"physics": 1, "handoff": 1}
    assert result["completion_status"] == "next_planning_handoff_ready"
    assert result["target"]["graph_id"] == "graph-v2"
    assert result["autonomy_boundary"]["authorization_granted"] is False


def test_physics_policy_rejection_blocks_recursive_reentry(monkeypatch) -> None:
    previous, checkpoint, graph, progression = _state()
    current = _current(previous, progression["target"])

    def reject(*args, **kwargs):
        raise ModelEvidenceDiscrepancyPhysicsPolicyError("physics contract failed")

    monkeypatch.setattr(
        rediagnosis,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        reject,
    )
    with pytest.raises(RecursiveResearchRediagnosisError, match="physics/provenance"):
        complete_recursive_cycle_with_rediagnosis(
            authorization_checkpoint=checkpoint,
            progression=progression,
            current_discrepancy_report=current,
            previous_discrepancy_report=previous,
            evaluated_graph=graph,
        )
