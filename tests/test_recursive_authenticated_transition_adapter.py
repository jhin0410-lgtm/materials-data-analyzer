from __future__ import annotations

import hashlib
import json

import pytest

import materials_data_analyzer.research_loop.recursive_research_cycle_evidence as evidence
from materials_data_analyzer.research_loop.recursive_research_cycle_evidence import (
    RecursiveResearchEvidenceError,
)


def _execution() -> dict:
    return {
        "action_id": "planner:analysis",
        "action_type": "analysis",
        "action_version": "1.0",
        "result_sha256": "d" * 64,
    }


def _source_target() -> dict:
    return {
        "graph_id": "g-1",
        "node_id": "h-1",
        "node_type": "hypothesis",
        "statement": "H",
    }


def _evaluated_graph() -> dict:
    return {
        "graph_id": "g-2",
        "nodes": [
            {
                "node_id": "h-1",
                "node_type": "hypothesis",
                "statement": "H",
            }
        ],
        "assessments": [
            {
                "node_id": "h-1",
                "node_type": "hypothesis",
                "status": "inconclusive",
            }
        ],
    }


def _write_bundle(tmp_path):
    graph = {
        "graph_id": "g-2",
        "nodes": [{"node_id": "h-1", "node_type": "hypothesis", "statement": "H"}],
        "edges": [],
    }
    graph_bytes = json.dumps(graph, ensure_ascii=False, sort_keys=True).encode("utf-8")
    graph_path = tmp_path / "epistemic_graph.json"
    graph_path.write_bytes(graph_bytes)
    proposal = {
        "transition_id": "transition-1",
        "base_graph_id": "g-1",
        "new_graph_id": "g-2",
        "target_node_id": "h-1",
        "source_action": {
            "action_id": "planner:analysis",
            "action_class": "analysis",
            "action_version": "1.0",
        },
        "result_node": {
            "artifact_bindings": [{"role": "result", "sha256": "d" * 64}]
        },
    }
    proposal_bytes = json.dumps(proposal, ensure_ascii=False, sort_keys=True).encode("utf-8")
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_bytes(proposal_bytes)
    report = {
        "bundle_root": str(tmp_path.resolve()),
        "current_transition_exact_provenance_authenticated": True,
        "transition_id": "transition-1",
        "target_node_id": "h-1",
        "inference_edge_id": "edge-1",
        "relation": "supports",
        "inference_scope": "computational",
        "proposal_binding": {
            "path": "proposal.json",
            "sha256": hashlib.sha256(proposal_bytes).hexdigest(),
        },
        "graph_binding": {
            "path": "epistemic_graph.json",
            "sha256": hashlib.sha256(graph_bytes).hexdigest(),
        },
    }
    return report, graph_path


def test_adapter_executes_consumer_binds_execution_and_evaluates_successor(
    monkeypatch, tmp_path
) -> None:
    report, _graph_path = _write_bundle(tmp_path)
    calls: list[object] = []

    def fake_consumer(root):
        calls.append(root)
        return report

    evaluated = _evaluated_graph()
    monkeypatch.setattr(evidence, "authenticate_transition_bundle", fake_consumer)
    monkeypatch.setattr(
        evidence,
        "evaluate_epistemic_graph",
        lambda graph, *, program_state, artifact_root: evaluated,
    )

    (
        report_sha,
        transition,
        actual_evaluated,
        evaluated_sha,
        target,
        assessment,
    ) = evidence._authenticated_transition(
        bundle_root=tmp_path,
        execution=_execution(),
        source_target=_source_target(),
        program_state={"workstreams": []},
    )

    assert calls == [tmp_path]
    assert report_sha == evidence._canonical_sha256(report)
    assert transition["transition_id"] == "transition-1"
    assert transition["current_transition_exact_provenance_authenticated"] is True
    assert transition["execution_completion_treated_as_scientific_support"] is False
    assert actual_evaluated == evaluated
    assert evaluated_sha == evidence._canonical_sha256(evaluated)
    assert target["graph_id"] == "g-2"
    assert assessment["status"] == "inconclusive"


def test_adapter_rejects_graph_bytes_changed_after_consumer_verification(
    monkeypatch, tmp_path
) -> None:
    report, graph_path = _write_bundle(tmp_path)
    monkeypatch.setattr(evidence, "authenticate_transition_bundle", lambda root: report)
    graph_path.write_text("{}", encoding="utf-8")

    with pytest.raises(RecursiveResearchEvidenceError, match="changed after authenticated"):
        evidence._authenticated_transition(
            bundle_root=tmp_path,
            execution=_execution(),
            source_target=_source_target(),
            program_state={"workstreams": []},
        )
