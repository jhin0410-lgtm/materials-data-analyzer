from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import authenticated_epistemic_transition as module
from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    AuthenticatedEpistemicTransitionError,
    apply_authenticated_epistemic_transition_files,
)


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, bytes]:
    result_file = tmp_path / "result.json"
    result_bytes = (json.dumps({"rank_before": 3, "rank_after": 4}) + "\n").encode(
        "utf-8"
    )
    result_file.write_bytes(result_bytes)
    result_sha = hashlib.sha256(result_bytes).hexdigest()

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
    return base_file, proposal_file, verification_file, result_file, result_bytes


def test_result_drift_before_snapshot_fails_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_file, proposal_file, verification_file, result_file, _ = _fixture(tmp_path)
    real_scope_validate = module.validate_verification_decision

    def mutate_result_after_scope_validation(
        *args: object, **kwargs: object
    ) -> dict[str, object]:
        validated = real_scope_validate(*args, **kwargs)
        result_file.write_text('{"tampered":true}\n', encoding="utf-8")
        return validated

    monkeypatch.setattr(
        module,
        "validate_verification_decision",
        mutate_result_after_scope_validation,
    )
    output = tmp_path / "out"

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="checksum mismatch",
    ):
        apply_authenticated_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            verification_decision_path=verification_file,
            program_state={"workstreams": []},
            artifact_root=tmp_path,
            output_dir=output,
        )

    assert not output.exists()


def test_result_source_drift_after_snapshot_cannot_change_published_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_file, proposal_file, verification_file, result_file, original_result = _fixture(
        tmp_path
    )
    real_prepare = module._prepare_current_result_snapshots

    def mutate_result_after_snapshot(*args: object, **kwargs: object):
        prepared = real_prepare(*args, **kwargs)
        result_file.write_text('{"tampered":"after-snapshot"}\n', encoding="utf-8")
        return prepared

    monkeypatch.setattr(
        module,
        "_prepare_current_result_snapshots",
        mutate_result_after_snapshot,
    )
    output = tmp_path / "out"

    result = apply_authenticated_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verification_file,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
        output_dir=output,
    )

    snapshot = output / result["result_artifact_bindings"][0]["path"]
    assert result_file.read_bytes() != original_result
    assert snapshot.read_bytes() == original_result
    graph = json.loads((output / "epistemic_graph.json").read_text(encoding="utf-8"))
    result_node = next(item for item in graph["nodes"] if item["node_id"] == "result-1")
    assert result_node["artifact_bindings"][0]["path"] == result[
        "result_artifact_bindings"
    ][0]["path"]
    assert result["autonomy_boundary"]["bundle_published_atomically"] is True
    assert result["autonomy_boundary"]["scientific_relation_promoted_by_producer"] is False
