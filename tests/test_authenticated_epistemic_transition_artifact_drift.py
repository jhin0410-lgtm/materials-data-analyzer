from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import authenticated_epistemic_transition as module
from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    apply_authenticated_epistemic_transition_files,
)
from materials_data_analyzer.research_loop.epistemic_graph import EpistemicGraphError


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_result_artifact_drift_after_staging_fails_and_cleans_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"rank_before": 3, "rank_after": 4})

    base_graph = {
        "schema_version": "1.0",
        "graph_id": "graph-v1",
        "research_scope": "authenticated transition artifact-drift regression",
        "nodes": [
            {
                "node_id": "question-1",
                "node_type": "research_question",
                "statement": "What does the bounded result establish?",
            },
            {
                "node_id": "hypothesis-1",
                "node_type": "hypothesis",
                "statement": "The structural target holds within scope.",
                "metadata": {"claim_scope": "structural"},
            },
        ],
        "edges": [
            {
                "edge_id": "motivation-1",
                "source_node_id": "question-1",
                "target_node_id": "hypothesis-1",
                "relation": "motivates",
                "assessment_level": "proposal",
                "rationale": "The question motivates the hypothesis.",
                "active": True,
            }
        ],
    }
    base_file = tmp_path / "base_graph.json"
    base_sha = _write_json(base_file, base_graph)

    proposal = {
        "schema_version": "1.0",
        "transition_id": "transition-1",
        "base_graph_id": "graph-v1",
        "base_graph_sha256": base_sha,
        "new_graph_id": "graph-v2",
        "target_node_id": "hypothesis-1",
        "source_action": {
            "action_id": "action-1",
            "action_class": "simulation",
            "action_version": "1.0",
            "execution_mode": "typed_local_action",
        },
        "result_node": {
            "node_id": "result-1",
            "node_type": "simulation",
            "statement": "A bounded structural simulation completed.",
            "artifact_bindings": [
                {"role": "primary_result", "path": "result.json", "sha256": result_sha}
            ],
            "metadata": {"result_origin": "authorized_local_simulation"},
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": "tests-1",
            "inference_edge_id": "inference-1",
            "relation": "supports",
            "rationale": "The simulation bears on the structural target.",
        },
        "limitations": ["Structural scope only."],
    }
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(proposal_file, proposal)

    verification = {
        "schema_version": "1.1",
        "decision_id": "verification-1",
        "transition_id": "transition-1",
        "proposal_sha256": proposal_sha,
        "base_graph_sha256": base_sha,
        "inference_edge_id": "inference-1",
        "result_node_id": "result-1",
        "target_node_id": "hypothesis-1",
        "relation": "supports",
        "inference_scope": "structural",
        "verifier_id": "bounded-domain-verifier-v1.1",
        "rationale": "The exact inference edge is verified only in structural scope.",
        "limitations": [],
        "domain_verified": True,
    }
    verification_file = tmp_path / "verification.json"
    _write_json(verification_file, verification)

    real_stage = module.apply_epistemic_transition_files

    def mutate_result_after_stage(**kwargs: object) -> dict[str, object]:
        staged = real_stage(**kwargs)
        result_file.write_text('{"tampered":true}\n', encoding="utf-8")
        return staged

    monkeypatch.setattr(module, "apply_epistemic_transition_files", mutate_result_after_stage)
    output = tmp_path / "out"

    with pytest.raises(EpistemicGraphError, match="checksum mismatch"):
        apply_authenticated_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            verification_decision_path=verification_file,
            program_state={"workstreams": []},
            artifact_root=tmp_path,
            output_dir=output,
        )

    assert not output.exists()
