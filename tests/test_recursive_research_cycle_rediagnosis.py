from __future__ import annotations

import copy
import hashlib
import json

import pytest

import materials_data_analyzer.research_loop.recursive_research_cycle_rediagnosis as rediagnosis
from materials_data_analyzer.research_loop.recursive_research_cycle_rediagnosis import (
    RecursiveResearchRediagnosisError,
    complete_recursive_cycle_with_rediagnosis,
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


def _previous_report() -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "target": {
            "graph_id": "g-1",
            "node_id": "h-1",
            "node_type": "hypothesis",
            "statement": "Bounded target statement.",
        },
    }
    value["report_sha256"] = _canonical_sha(value)
    return value


def _checkpoint(previous_report: dict) -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "cycle_id": "recursive:g-1:h-1",
        "cycle_index": 1,
        "checkpoint_status": "explicit_authorization_required",
        "target": dict(previous_report["target"]),
        "ancestry": {
            "previous_checkpoint_sha256": None,
            "source_discrepancy_report_sha256": previous_report["report_sha256"],
            "planning_handoff_sha256": "a" * 64,
            "fresh_plan_sha256": "b" * 64,
        },
        "autonomy_boundary": {
            "authorization_granted": False,
        },
    }
    value["checkpoint_sha256"] = _canonical_sha(value)
    return value


def _graph() -> dict:
    return {
        "graph_id": "g-1",
        "nodes": [
            {
                "node_id": "h-1",
                "node_type": "hypothesis",
                "statement": "Bounded target statement.",
            }
        ],
        "assessments": [{"node_id": "h-1", "status": "inconclusive"}],
    }


def _portfolio(graph: dict) -> dict:
    value = {
        "graph_id": "g-1",
        "evaluated_graph_binding": {"canonical_sha256": _canonical_sha(graph)},
        "hypotheses": [
            {
                "hypothesis_id": "h-1",
                "statement": "Bounded target statement.",
                "epistemic_status": "inconclusive",
                "portfolio_state": "active_discrimination_required",
                "research_directive": "continue_discriminating_research",
            }
        ],
    }
    value["portfolio_sha256"] = _canonical_sha(value)
    return value


def _progression(checkpoint: dict, graph: dict, portfolio: dict) -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "cycle_id": checkpoint["cycle_id"],
        "cycle_index": 1,
        "progression_status": "re_diagnosis_required",
        "target": dict(checkpoint["target"]),
        "ancestry": {
            "authorization_checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "verified_execution_record_sha256": "c" * 64,
            "epistemic_transition_record_sha256": "d" * 64,
            "evaluated_graph_canonical_sha256": _canonical_sha(graph),
            "hypothesis_portfolio_sha256": portfolio["portfolio_sha256"],
        },
    }
    value["progression_sha256"] = _canonical_sha(value)
    return value


def _current_report(previous: dict) -> dict:
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "target": dict(previous["target"]),
        "input_bindings": {
            "previous_discrepancy_report": {
                "report_sha256": previous["report_sha256"],
            }
        },
    }


def _next_handoff(current_sha: str) -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_discrepancy_report_sha256": current_sha,
        "research_objectives": [{"objective_id": "planning-objective:next"}],
        "planner_boundary": {
            "fresh_planner_candidate_matching_required": True,
            "automatic_execution_authorized": False,
        },
    }
    value["handoff_sha256"] = _canonical_sha(value)
    return value


def test_validated_rediagnosis_reenters_planning_without_execution_authority(monkeypatch) -> None:
    previous = _previous_report()
    checkpoint = _checkpoint(previous)
    graph = _graph()
    portfolio = _portfolio(graph)
    progression = _progression(checkpoint, graph, portfolio)
    current = _current_report(previous)
    current_sha = "e" * 64

    monkeypatch.setattr(
        rediagnosis,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        lambda *args, **kwargs: {
            "report_sha256": current_sha,
            "iteration_index": 2,
            "diagnosis_types": ["parameter_or_property_uncertainty"],
        },
    )
    monkeypatch.setattr(
        rediagnosis,
        "build_policy_hardened_discrepancy_planning_handoff",
        lambda *args, **kwargs: _next_handoff(current_sha),
    )

    result = complete_recursive_cycle_with_rediagnosis(
        authorization_checkpoint=checkpoint,
        progression=progression,
        current_discrepancy_report=current,
        previous_discrepancy_report=previous,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
    )
    assert result["completion_status"] == "next_planning_handoff_ready"
    assert result["validated_rediagnosis"]["iteration_index"] == 2
    assert result["validated_rediagnosis"]["physics_hardening_verified"] is True
    assert result["ancestry"]["previous_discrepancy_report_sha256"] == previous["report_sha256"]
    assert result["ancestry"]["current_discrepancy_report_sha256"] == current_sha
    assert result["next_planning_handoff"]["planner_boundary"][
        "fresh_planner_candidate_matching_required"
    ] is True
    assert result["autonomy_boundary"]["authorization_granted"] is False
    assert result["autonomy_boundary"]["execution_performed"] is False
    assert result["autonomy_boundary"]["scientific_status_changed"] is False


def test_rediagnosis_rejects_previous_report_or_target_substitution(monkeypatch) -> None:
    previous = _previous_report()
    checkpoint = _checkpoint(previous)
    graph = _graph()
    portfolio = _portfolio(graph)
    progression = _progression(checkpoint, graph, portfolio)
    current = _current_report(previous)

    different_previous = copy.deepcopy(previous)
    different_previous.pop("report_sha256")
    different_previous["extra"] = "different bytes"
    different_previous["report_sha256"] = _canonical_sha(different_previous)
    with pytest.raises(RecursiveResearchRediagnosisError, match="previous discrepancy"):
        complete_recursive_cycle_with_rediagnosis(
            authorization_checkpoint=checkpoint,
            progression=progression,
            current_discrepancy_report=current,
            previous_discrepancy_report=different_previous,
            evaluated_graph=graph,
            hypothesis_portfolio=portfolio,
        )

    monkeypatch.setattr(
        rediagnosis,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        lambda *args, **kwargs: {
            "report_sha256": "e" * 64,
            "iteration_index": 2,
            "diagnosis_types": [],
        },
    )
    changed_target = copy.deepcopy(current)
    changed_target["target"]["node_id"] = "h-2"
    with pytest.raises(RecursiveResearchRediagnosisError, match="target differs"):
        complete_recursive_cycle_with_rediagnosis(
            authorization_checkpoint=checkpoint,
            progression=progression,
            current_discrepancy_report=changed_target,
            previous_discrepancy_report=previous,
            evaluated_graph=graph,
            hypothesis_portfolio=portfolio,
        )


def test_rediagnosis_rejects_reused_report_and_unsafe_next_handoff(monkeypatch) -> None:
    previous = _previous_report()
    checkpoint = _checkpoint(previous)
    graph = _graph()
    portfolio = _portfolio(graph)
    progression = _progression(checkpoint, graph, portfolio)
    current = _current_report(previous)

    monkeypatch.setattr(
        rediagnosis,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        lambda *args, **kwargs: {
            "report_sha256": previous["report_sha256"],
            "iteration_index": 2,
            "diagnosis_types": [],
        },
    )
    with pytest.raises(RecursiveResearchRediagnosisError, match="must not reuse"):
        complete_recursive_cycle_with_rediagnosis(
            authorization_checkpoint=checkpoint,
            progression=progression,
            current_discrepancy_report=current,
            previous_discrepancy_report=previous,
            evaluated_graph=graph,
            hypothesis_portfolio=portfolio,
        )

    current_sha = "e" * 64
    monkeypatch.setattr(
        rediagnosis,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        lambda *args, **kwargs: {
            "report_sha256": current_sha,
            "iteration_index": 2,
            "diagnosis_types": [],
        },
    )
    unsafe = _next_handoff(current_sha)
    unsafe.pop("handoff_sha256")
    unsafe["planner_boundary"]["automatic_execution_authorized"] = True
    unsafe["handoff_sha256"] = _canonical_sha(unsafe)
    monkeypatch.setattr(
        rediagnosis,
        "build_policy_hardened_discrepancy_planning_handoff",
        lambda *args, **kwargs: unsafe,
    )
    with pytest.raises(RecursiveResearchRediagnosisError, match="cannot authorize"):
        complete_recursive_cycle_with_rediagnosis(
            authorization_checkpoint=checkpoint,
            progression=progression,
            current_discrepancy_report=current,
            previous_discrepancy_report=previous,
            evaluated_graph=graph,
            hypothesis_portfolio=portfolio,
        )


def test_rediagnosis_requires_physics_hardened_validator(monkeypatch) -> None:
    previous = _previous_report()
    checkpoint = _checkpoint(previous)
    graph = _graph()
    portfolio = _portfolio(graph)
    progression = _progression(checkpoint, graph, portfolio)
    current = _current_report(previous)

    def reject_physics(*args, **kwargs):
        raise RecursiveResearchRediagnosisError("physics hardening rejected report")

    monkeypatch.setattr(
        rediagnosis,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        reject_physics,
    )
    with pytest.raises(RecursiveResearchRediagnosisError, match="physics hardening"):
        complete_recursive_cycle_with_rediagnosis(
            authorization_checkpoint=checkpoint,
            progression=progression,
            current_discrepancy_report=current,
            previous_discrepancy_report=previous,
            evaluated_graph=graph,
            hypothesis_portfolio=portfolio,
        )
