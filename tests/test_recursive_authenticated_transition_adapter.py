from __future__ import annotations

import hashlib
import json

import pytest

import materials_data_analyzer.research_loop.recursive_research_cycle_evidence as evidence
from materials_data_analyzer.research_loop.recursive_research_cycle_evidence import (
    RecursiveResearchEvidenceError,
    build_epistemic_transition_record_from_authenticated_bundle,
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


def _execution() -> dict:
    value = {
        "schema_version": "1.0",
        "source_checkpoint_sha256": "a" * 64,
        "authorization_status": "explicit_request_authorized_by_existing_chain",
        "independent_verification_status": "verified_by_existing_chain",
        "action_id": "planner:analysis",
        "action_type": "analysis",
        "action_version": "1.0",
        "request_sha256": "b" * 64,
        "registry_sha256": "c" * 64,
        "result_sha256": "d" * 64,
        "execution_outcome": "completed",
        "execution_success": True,
        "scientific_evidence_upgraded": False,
    }
    value["verification_record_sha256"] = _sha(value)
    return value


def test_adapter_executes_consumer_and_binds_exact_successor_graph(monkeypatch, tmp_path) -> None:
    graph = {
        "graph_id": "g-1",
        "nodes": [{"node_id": "h-1", "node_type": "hypothesis", "statement": "H"}],
        "assessments": [],
    }
    graph_bytes = json.dumps(graph, ensure_ascii=False, sort_keys=True).encode("utf-8")
    graph_path = tmp_path / "epistemic_graph.json"
    graph_path.write_bytes(graph_bytes)
    report = {
        "schema_version": "1.0",
        "consumer_policy_version": "1.0",
        "bundle_root": str(tmp_path.resolve()),
        "current_transition_exact_provenance_authenticated": True,
        "transition_id": "transition-1",
        "target_node_id": "h-1",
        "graph_binding": {
            "path": "epistemic_graph.json",
            "sha256": hashlib.sha256(graph_bytes).hexdigest(),
        },
        "authority_boundary": {
            "scientific_authority_applied": False,
            "scientific_status_changed": False,
        },
    }
    calls: list[object] = []

    def fake_consumer(root):
        calls.append(root)
        return report

    monkeypatch.setattr(evidence, "authenticate_transition_bundle", fake_consumer)
    record = build_epistemic_transition_record_from_authenticated_bundle(
        tmp_path,
        verified_execution_record=_execution(),
        evaluated_graph=graph,
    )
    assert calls == [tmp_path]
    assert record["transition_id"] == "transition-1"
    assert record["consumer_verification_status"] == (
        "verified_by_authenticated_transition_consumer"
    )
    assert record["authenticated_consumer_graph_file_sha256"] == report["graph_binding"]["sha256"]
    assert record["execution_completion_treated_as_scientific_support"] is False


def test_adapter_rejects_graph_bytes_changed_after_consumer_verification(monkeypatch, tmp_path) -> None:
    graph = {
        "graph_id": "g-1",
        "nodes": [{"node_id": "h-1", "node_type": "hypothesis", "statement": "H"}],
        "assessments": [],
    }
    original = json.dumps(graph, sort_keys=True).encode("utf-8")
    path = tmp_path / "epistemic_graph.json"
    path.write_bytes(original)
    report = {
        "schema_version": "1.0",
        "consumer_policy_version": "1.0",
        "bundle_root": str(tmp_path.resolve()),
        "current_transition_exact_provenance_authenticated": True,
        "transition_id": "transition-1",
        "target_node_id": "h-1",
        "graph_binding": {
            "path": "epistemic_graph.json",
            "sha256": hashlib.sha256(original).hexdigest(),
        },
        "authority_boundary": {
            "scientific_authority_applied": False,
            "scientific_status_changed": False,
        },
    }
    monkeypatch.setattr(evidence, "authenticate_transition_bundle", lambda root: report)
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(RecursiveResearchEvidenceError, match="changed after consumer"):
        build_epistemic_transition_record_from_authenticated_bundle(
            tmp_path,
            verified_execution_record=_execution(),
            evaluated_graph=graph,
        )
