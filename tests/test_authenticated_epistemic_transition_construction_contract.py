from __future__ import annotations

from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    _proposal_result_and_edges,
)


def test_direct_construction_preserves_provenance_without_scientific_promotion() -> None:
    proposal = {
        "transition_id": "transition-1",
        "target_node_id": "target-1",
        "source_action": {
            "action_id": "action-1",
            "action_class": "existing_data_reanalysis",
            "action_version": "1.0",
            "execution_mode": "typed_local_action",
        },
        "result_node": {
            "node_id": "result-1",
            "node_type": "analysis",
            "statement": "Bound result.",
            "artifact_bindings": [
                {
                    "role": "primary_result",
                    "path": "/source/result.json",
                    "sha256": "a" * 64,
                }
            ],
            "metadata": {
                "result_origin": "authorized_local_analysis",
                "producer_note": "preserve-me",
            },
        },
        "input_evidence_bindings": [
            {
                "workstream_id": "ws",
                "role": "measurement",
                "sha256": "e" * 64,
            }
        ],
        "proposed_inference": {
            "tests_edge_id": "tests-1",
            "inference_edge_id": "inference-1",
            "relation": "contradicts",
            "rationale": "Exact bounded directional rationale.",
        },
        "limitations": ["Limit A", "Limit B"],
    }
    snapshot_bindings = [
        {
            "role": "primary_result",
            "path": "provenance/current/result_artifacts/result-000.json",
            "sha256": "a" * 64,
        }
    ]

    result_node, tests_edge, inference_edge = _proposal_result_and_edges(
        proposal,
        result_artifact_bindings=snapshot_bindings,
    )

    assert result_node["node_id"] == "result-1"
    assert result_node["statement"] == "Bound result."
    assert result_node["artifact_bindings"] == snapshot_bindings
    metadata = result_node["metadata"]
    assert metadata["result_origin"] == "authorized_local_analysis"
    assert metadata["producer_note"] == "preserve-me"
    assert metadata["source_action"] == proposal["source_action"]
    assert metadata["input_evidence_bindings"] == proposal["input_evidence_bindings"]
    assert metadata["transition_id"] == "transition-1"
    assert metadata["limitations"] == ["Limit A", "Limit B"]

    assert tests_edge == {
        "edge_id": "tests-1",
        "source_node_id": "result-1",
        "target_node_id": "target-1",
        "relation": "tests",
        "assessment_level": "proposal",
        "rationale": (
            "The completed result was introduced to test this target; execution success alone "
            "does not establish scientific support, contradiction, or falsification."
        ),
        "active": True,
    }
    assert inference_edge == {
        "edge_id": "inference-1",
        "source_node_id": "result-1",
        "target_node_id": "target-1",
        "relation": "contradicts",
        "assessment_level": "diagnostic",
        "rationale": "Exact bounded directional rationale.",
        "active": True,
    }
    assert "verification_artifact" not in inference_edge
