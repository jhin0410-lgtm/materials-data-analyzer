from __future__ import annotations

import hashlib
import json
from pathlib import Path

from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE,
)
from materials_data_analyzer.research_loop.scientific_critic import (
    build_scientific_critic_report,
)


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_current_critic_sees_producer_edge_as_diagnostic_not_verified_support(
    tmp_path: Path,
) -> None:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"bounded": True})
    verifier_file = tmp_path / "verification.json"
    verifier_sha = _write_json(
        verifier_file,
        {
            "schema_version": "1.1",
            "decision_id": "decision-1",
            "transition_id": "transition-1",
            "proposal_sha256": "a" * 64,
            "base_graph_sha256": "b" * 64,
            "inference_edge_id": "support-1",
            "result_node_id": "result-1",
            "target_node_id": "hypothesis-1",
            "relation": "supports",
            "inference_scope": "structural",
            "verifier_id": "verifier-v1.1",
            "rationale": "Exact edge verifier fixture.",
            "limitations": [],
            "domain_verified": True,
        },
    )
    graph_file = tmp_path / "graph.json"
    _write_json(
        graph_file,
        {
            "schema_version": "1.0",
            "graph_id": "critic-v11-compatibility",
            "research_scope": "legacy critic compatibility with diagnostic producer edge",
            "nodes": [
                {
                    "node_id": "hypothesis-1",
                    "node_type": "hypothesis",
                    "statement": "Bound structural target.",
                    "metadata": {"claim_scope": "structural"},
                },
                {
                    "node_id": "result-1",
                    "node_type": "analysis",
                    "statement": "Completed bounded analysis.",
                    "execution_status": "completed",
                    "artifact_bindings": [
                        {
                            "role": "primary_result",
                            "path": str(result_file),
                            "sha256": result_sha,
                        }
                    ],
                },
            ],
            "edges": [
                {
                    "edge_id": "support-1",
                    "source_node_id": "result-1",
                    "target_node_id": "hypothesis-1",
                    "relation": "supports",
                    "assessment_level": "diagnostic",
                    "rationale": "Authenticated producer proposal awaiting consumer promotion.",
                    "active": True,
                }
            ],
            "metadata": {
                "authenticated_transition_lineage": [
                    {
                        "schema_version": "1.0",
                        "transition_id": "transition-1",
                        "verification_decision_artifact": {
                            "role": AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE,
                            "path": str(verifier_file),
                            "source_path": str(verifier_file),
                            "source_path_authoritative": False,
                            "sha256": verifier_sha,
                        },
                        "scientific_authority_applied": False,
                    }
                ]
            },
        },
    )
    program_state = {
        "mission": {
            "autonomy_policy": {"reasoning_proposals": "schema_validated"}
        },
        "mission_binding": None,
        "runtime_context_binding": None,
        "workstreams": [],
        "generated_goals": [],
    }

    report = build_scientific_critic_report(
        graph_file,
        program_state=program_state,
        artifact_root=tmp_path,
    )

    target = report["target_reports"][0]
    assert target["epistemic_assessment"]["status"] == "inconclusive"
    assert target["epistemic_assessment"]["verified_support_edges"] == []
    assert target["epistemic_assessment"]["diagnostic_relation_edges"] == ["support-1"]
    codes = {item["code"] for item in target["critic_findings"]}
    assert "DIRECTIONAL_RELATIONS_NOT_DOMAIN_VERIFIED" in codes
    assert "SUPPORT_INDEPENDENCE_NOT_ESTABLISHED" not in codes
    assert report["autonomy_boundary"]["automatic_action_execution_authorized"] is False
    assert report["autonomy_boundary"]["positive_scientific_closeout_granted"] is False
