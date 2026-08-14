from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.epistemic_transition import (
    EpistemicTransitionError,
    apply_epistemic_transition_files,
)


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_duplicate_transition_proposal_key_fails_closed(tmp_path: Path) -> None:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"value": 1})
    base = {
        "schema_version": "1.0",
        "graph_id": "g1",
        "research_scope": "duplicate key regression",
        "nodes": [
            {
                "node_id": "h1",
                "node_type": "hypothesis",
                "statement": "bounded hypothesis",
                "metadata": {"claim_scope": "structural"},
            }
        ],
        "edges": [],
    }
    base_file = tmp_path / "base.json"
    base_sha = _write_json(base_file, base)
    proposal_file = tmp_path / "proposal.json"
    proposal_file.write_text(
        "{" 
        '"schema_version":"1.0",'
        '"transition_id":"t1",'
        '"transition_id":"t2",'
        '"base_graph_id":"g1",'
        f'"base_graph_sha256":"{base_sha}",'
        '"new_graph_id":"g2",'
        '"target_node_id":"h1",'
        '"source_action":{"action_id":"a1","action_class":"simulation","action_version":"1.0","execution_mode":"typed_local_action"},'
        f'"result_node":{{"node_id":"r1","node_type":"simulation","statement":"result","artifact_bindings":[{{"role":"primary_result","path":"result.json","sha256":"{result_sha}"}}],"metadata":{{"result_origin":"authorized_local_simulation"}}}},'
        '"input_evidence_bindings":[],'
        '"proposed_inference":{"tests_edge_id":"e1","inference_edge_id":"e2","relation":"supports","rationale":"bounded"},'
        '"limitations":["bounded"]'
        "}",
        encoding="utf-8",
    )

    with pytest.raises(EpistemicTransitionError, match="duplicate JSON key"):
        apply_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            program_state={"workstreams": []},
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
        )
    assert not (tmp_path / "out").exists()
