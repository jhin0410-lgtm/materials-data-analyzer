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


def test_external_physical_result_cannot_claim_typed_local_execution(tmp_path: Path) -> None:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"measurement": 1.0})
    base_file = tmp_path / "base.json"
    base_sha = _write_json(
        base_file,
        {
            "schema_version": "1.0",
            "graph_id": "g1",
            "research_scope": "external boundary",
            "nodes": [
                {
                    "node_id": "h1",
                    "node_type": "hypothesis",
                    "statement": "bounded empirical hypothesis",
                    "metadata": {"claim_scope": "empirical"},
                }
            ],
            "edges": [],
        },
    )
    proposal_file = tmp_path / "proposal.json"
    _write_json(
        proposal_file,
        {
            "schema_version": "1.0",
            "transition_id": "t1",
            "base_graph_id": "g1",
            "base_graph_sha256": base_sha,
            "new_graph_id": "g2",
            "target_node_id": "h1",
            "source_action": {
                "action_id": "external-physical-1",
                "action_class": "physical_experiment",
                "action_version": "1.0",
                "execution_mode": "typed_local_action",
            },
            "result_node": {
                "node_id": "r1",
                "node_type": "experiment",
                "statement": "External measurement result.",
                "artifact_bindings": [
                    {"role": "primary_result", "path": "result.json", "sha256": result_sha}
                ],
                "metadata": {"result_origin": "external_physical_experiment"},
            },
            "input_evidence_bindings": [],
            "proposed_inference": {
                "tests_edge_id": "tests-1",
                "inference_edge_id": "inference-1",
                "relation": "supports",
                "rationale": "bounded",
            },
            "limitations": ["external execution only"],
        },
    )

    with pytest.raises(EpistemicTransitionError, match="external physical/analysis results"):
        apply_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            program_state={"workstreams": []},
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
        )
