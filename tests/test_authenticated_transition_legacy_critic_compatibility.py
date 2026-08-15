from __future__ import annotations

import hashlib
import json
from pathlib import Path

from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    apply_authenticated_epistemic_transition_files,
)
from materials_data_analyzer.research_loop.scientific_critic import (
    build_scientific_critic_report,
)


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_current_critic_accepts_actual_bundle_but_keeps_edge_diagnostic(
    tmp_path: Path,
) -> None:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"bounded": True})
    base_file = tmp_path / "base.json"
    base_sha = _write_json(
        base_file,
        {
            "schema_version": "1.0",
            "graph_id": "graph-v1",
            "research_scope": "producer to legacy critic compatibility",
            "nodes": [
                {
                    "node_id": "hypothesis-1",
                    "node_type": "hypothesis",
                    "statement": "Bound structural target.",
                    "metadata": {"claim_scope": "structural"},
                }
            ],
            "edges": [],
        },
    )
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(
        proposal_file,
        {
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
                "statement": "Completed bounded structural simulation.",
                "artifact_bindings": [
                    {
                        "role": "primary_result",
                        "path": str(result_file),
                        "sha256": result_sha,
                    }
                ],
                "metadata": {"result_origin": "authorized_local_simulation"},
            },
            "input_evidence_bindings": [],
            "proposed_inference": {
                "tests_edge_id": "tests-1",
                "inference_edge_id": "support-1",
                "relation": "supports",
                "rationale": "Authenticated producer proposal awaiting consumer promotion.",
            },
            "limitations": ["Diagnostic producer output only."],
        },
    )
    verifier_file = tmp_path / "verification.json"
    _write_json(
        verifier_file,
        {
            "schema_version": "1.1",
            "decision_id": "decision-1",
            "transition_id": "transition-1",
            "proposal_sha256": proposal_sha,
            "base_graph_sha256": base_sha,
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
    program_state = {
        "mission": {
            "autonomy_policy": {"reasoning_proposals": "schema_validated"}
        },
        "mission_binding": None,
        "runtime_context_binding": None,
        "workstreams": [],
        "generated_goals": [],
    }
    output = tmp_path / "bundle"

    apply_authenticated_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verifier_file,
        program_state=program_state,
        artifact_root=tmp_path,
        output_dir=output,
    )
    report = build_scientific_critic_report(
        output / "epistemic_graph.json",
        program_state=program_state,
        artifact_root=output,
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
