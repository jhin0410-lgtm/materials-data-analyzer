from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import epistemic_gate as module


def _program() -> dict[str, object]:
    return {
        "mission_binding": {"path": "mission.json", "sha256": "m" * 64},
        "runtime_context_binding": None,
        "workstreams": [
            {
                "workstream_id": "nasa-battery",
                "adapter_id": "nasa-battery",
                "status": "verified",
                "planning_state": {},
            },
            {
                "workstream_id": "nist-ambench",
                "adapter_id": "nist-ambench-process-characterization",
                "status": "verified",
                "planning_state": {},
            },
        ],
    }


def _node(node_id: str, node_type: str, workstream: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "node_id": node_id,
        "node_type": node_type,
        "statement": node_id,
    }
    if workstream is not None:
        result["evidence_binding"] = {
            "workstream_id": workstream,
            "role": "test",
            "sha256": workstream[0] * 64,
        }
        result["evidence_quality"] = "diagnostic"
    return result


def _edge(edge_id: str, source: str, target: str, relation: str) -> dict[str, object]:
    return {
        "edge_id": edge_id,
        "source_node_id": source,
        "target_node_id": target,
        "relation": relation,
        "assessment_level": "diagnostic",
        "rationale": edge_id,
        "active": True,
        "verification_artifact": None,
    }


def test_gate_rejects_target_with_only_other_workstream_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text("{}", encoding="utf-8")
    evaluation = {
        "graph_id": "g",
        "graph_policy_version": "1.0",
        "nodes": [
            _node("nist-evidence", "evidence", "nist-ambench"),
            _node("target", "hypothesis"),
        ],
        "edges": [_edge("nist-support", "nist-evidence", "target", "supports")],
        "assessments": [
            {
                "node_id": "target",
                "node_type": "hypothesis",
                "status": "inconclusive",
                "verified_support_edges": [],
                "verified_contradiction_edges": [],
                "verified_falsification_edges": [],
                "diagnostic_relation_edges": ["nist-support"],
                "final_positive_support_granted": False,
                "domain_closeout_required_for_positive_conclusion": False,
                "confidence_score": None,
            }
        ],
    }
    monkeypatch.setattr(module, "build_research_program", lambda *args, **kwargs: _program())
    monkeypatch.setattr(module, "evaluate_epistemic_graph", lambda *args, **kwargs: evaluation)

    with pytest.raises(module.EpistemicGateError, match="not provenance-bound"):
        module.evaluate_epistemic_gate(
            adapter_id="nasa-battery",
            workstream_id="nasa-battery",
            target_node_ids=["target"],
            mission_path=tmp_path / "mission.json",
            graph_path=graph_path,
            repository_root=tmp_path,
        )


def test_gate_ignores_other_workstream_verified_falsification_for_selected_directive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text("{}", encoding="utf-8")
    evaluation = {
        "graph_id": "g",
        "graph_policy_version": "1.0",
        "nodes": [
            _node("nasa-evidence", "evidence", "nasa-battery"),
            _node("nist-evidence", "evidence", "nist-ambench"),
            _node("target", "hypothesis"),
        ],
        "edges": [
            _edge("nasa-diagnostic", "nasa-evidence", "target", "supports"),
            _edge("nist-falsification", "nist-evidence", "target", "falsifies"),
        ],
        "assessments": [
            {
                "node_id": "target",
                "node_type": "hypothesis",
                "status": "falsified_within_verified_scope",
                "verified_support_edges": [],
                "verified_contradiction_edges": [],
                "verified_falsification_edges": ["nist-falsification"],
                "diagnostic_relation_edges": ["nasa-diagnostic"],
                "final_positive_support_granted": False,
                "domain_closeout_required_for_positive_conclusion": False,
                "confidence_score": None,
            }
        ],
    }
    monkeypatch.setattr(module, "build_research_program", lambda *args, **kwargs: _program())
    monkeypatch.setattr(module, "evaluate_epistemic_graph", lambda *args, **kwargs: evaluation)

    result = module.evaluate_epistemic_gate(
        adapter_id="nasa-battery",
        workstream_id="nasa-battery",
        target_node_ids=["target"],
        mission_path=tmp_path / "mission.json",
        graph_path=graph_path,
        repository_root=tmp_path,
    )

    assert result["target_workstream_provenance"]["target"] == [
        "nasa-battery",
        "nist-ambench",
    ]
    assert result["directive"]["directive"] == "continue_discriminating_research"
    assert result["directive"]["target_statuses"] == {"target": "inconclusive"}
    assert result["autonomy_boundary"]["cross_workstream_inference_edges_affect_directive"] is False


def test_graph_loader_hashes_the_same_single_snapshot_it_parses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "graph.json"
    first = b'{"schema_version":"1.0","graph_id":"first"}'
    second = b'{"schema_version":"1.0","graph_id":"second"}'
    calls = 0

    original_read_bytes = Path.read_bytes

    def changing_read_bytes(self: Path) -> bytes:
        nonlocal calls
        if self == path:
            calls += 1
            return first if calls == 1 else second
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", changing_read_bytes)
    payload, sha256 = module._load_json_snapshot(path)

    assert calls == 1
    assert payload["graph_id"] == "first"
    assert sha256 == hashlib.sha256(first).hexdigest()
