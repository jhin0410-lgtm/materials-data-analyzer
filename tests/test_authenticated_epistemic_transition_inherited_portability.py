from __future__ import annotations

import hashlib
import json
from pathlib import Path

from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    apply_authenticated_epistemic_transition_files,
)
from materials_data_analyzer.research_loop.authenticated_inference_binding import (
    authenticate_inference_binding,
)
from materials_data_analyzer.research_loop.epistemic_graph import (
    evaluate_epistemic_graph,
)


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_inherited_result_verifier_and_lineage_artifacts_are_bundle_portable(
    tmp_path: Path,
) -> None:
    research_scope = "portable inherited provenance regression"
    old_result = tmp_path / "old-result.json"
    old_result_sha = _write_json(old_result, {"old": "result"})
    legacy_result = tmp_path / "legacy-result.json"
    legacy_result_sha = _write_json(legacy_result, {"legacy": "result"})
    legacy_verifier = tmp_path / "legacy-verifier.json"
    legacy_verifier_sha = _write_json(legacy_verifier, {"legacy": "verifier"})

    old_parent = tmp_path / "old-parent.json"
    old_parent_graph = {
        "schema_version": "1.0",
        "graph_id": "graph-v0",
        "research_scope": research_scope,
        "nodes": [
            {
                "node_id": "hypothesis-1",
                "node_type": "hypothesis",
                "statement": "The bounded structural target holds.",
                "metadata": {"claim_scope": "structural"},
            },
            {
                "node_id": "legacy-result-node",
                "node_type": "analysis",
                "statement": "A legacy verified analysis remains inherited authority.",
                "execution_status": "completed",
                "artifact_bindings": [
                    {
                        "role": "primary_result",
                        "path": str(legacy_result),
                        "sha256": legacy_result_sha,
                    }
                ],
                "metadata": {"result_origin": "authorized_local_analysis"},
            },
        ],
        "edges": [
            {
                "edge_id": "legacy-support",
                "source_node_id": "legacy-result-node",
                "target_node_id": "hypothesis-1",
                "relation": "supports",
                "assessment_level": "domain_verified",
                "rationale": "Legacy v1.0-era verified structural support.",
                "active": True,
                "verification_artifact": {
                    "role": "domain_verification_decision",
                    "path": str(legacy_verifier),
                    "sha256": legacy_verifier_sha,
                },
            }
        ],
        "metadata": {},
    }
    old_parent_sha = _write_json(old_parent, old_parent_graph)
    old_proposal = tmp_path / "old-proposal.json"
    old_limitations = ["Historical producer lineage remains diagnostic-only."]
    old_source_action = {
        "action_id": "old-action",
        "action_class": "existing_data_reanalysis",
        "action_version": "1.0",
        "execution_mode": "typed_local_action",
    }
    old_proposal_value = {
        "schema_version": "1.0",
        "transition_id": "old-auth",
        "base_graph_id": "graph-v0",
        "base_graph_sha256": old_parent_sha,
        "new_graph_id": "graph-v1",
        "target_node_id": "hypothesis-1",
        "source_action": old_source_action,
        "result_node": {
            "node_id": "old-result-node",
            "node_type": "analysis",
            "statement": "Previously completed bounded analysis.",
            "artifact_bindings": [
                {
                    "role": "primary_result",
                    "path": str(old_result),
                    "sha256": old_result_sha,
                }
            ],
            "metadata": {"result_origin": "authorized_local_analysis"},
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": "old-tests",
            "inference_edge_id": "old-support",
            "relation": "supports",
            "rationale": "Previously authenticated structural support identity.",
        },
        "limitations": old_limitations,
    }
    old_proposal_sha = _write_json(old_proposal, old_proposal_value)
    old_auth_verifier = tmp_path / "old-auth-verifier.json"
    old_auth_verifier_value = {
        "schema_version": "1.1",
        "decision_id": "old-decision",
        "transition_id": "old-auth",
        "proposal_sha256": old_proposal_sha,
        "base_graph_sha256": old_parent_sha,
        "inference_edge_id": "old-support",
        "result_node_id": "old-result-node",
        "target_node_id": "hypothesis-1",
        "relation": "supports",
        "inference_scope": "structural",
        "verifier_id": "old-verifier-v1.1",
        "rationale": "Exact historical edge identity authenticated.",
        "limitations": [],
        "domain_verified": True,
    }
    old_auth_verifier_sha = _write_json(old_auth_verifier, old_auth_verifier_value)
    old_authenticated_binding = authenticate_inference_binding(
        proposal_bytes=old_proposal.read_bytes(),
        verification_decision_bytes=old_auth_verifier.read_bytes(),
        expected_base_graph_sha256=old_parent_sha,
    )

    old_result_metadata = {
        "result_origin": "authorized_local_analysis",
        "source_action": old_source_action,
        "input_evidence_bindings": [],
        "transition_id": "old-auth",
        "limitations": old_limitations,
    }
    base_graph = {
        "schema_version": "1.0",
        "graph_id": "graph-v1",
        "research_scope": research_scope,
        "nodes": [
            *old_parent_graph["nodes"],
            {
                "node_id": "old-result-node",
                "node_type": "analysis",
                "statement": "Previously completed bounded analysis.",
                "execution_status": "completed",
                "artifact_bindings": [
                    {
                        "role": "primary_result",
                        "path": str(old_result),
                        "sha256": old_result_sha,
                    }
                ],
                "metadata": old_result_metadata,
            },
        ],
        "edges": [
            *old_parent_graph["edges"],
            {
                "edge_id": "old-tests",
                "source_node_id": "old-result-node",
                "target_node_id": "hypothesis-1",
                "relation": "tests",
                "assessment_level": "proposal",
                "rationale": (
                    "The completed result was introduced to test this target; execution success alone "
                    "does not establish scientific support, contradiction, or falsification."
                ),
                "active": True,
            },
            {
                "edge_id": "old-support",
                "source_node_id": "old-result-node",
                "target_node_id": "hypothesis-1",
                "relation": "supports",
                "assessment_level": "diagnostic",
                "rationale": "Previously authenticated structural support identity.",
                "active": True,
            },
        ],
        "metadata": {
            "transition_lineage": [
                {
                    "transition_id": "old-auth",
                    "parent_graph_id": "graph-v0",
                    "parent_graph_sha256": old_parent_sha,
                    "proposal_sha256": old_proposal_sha,
                    "verification_decision_sha256": old_auth_verifier_sha,
                    "result_node_id": "old-result-node",
                }
            ],
            "authenticated_transition_lineage": [
                {
                    "schema_version": "1.0",
                    "transition_id": "old-auth",
                    "base_graph_artifact": {
                        "path": str(old_parent),
                        "sha256": old_parent_sha,
                    },
                    "proposal_artifact": {
                        "path": str(old_proposal),
                        "sha256": old_proposal_sha,
                    },
                    "verification_decision_artifact": {
                        "role": "authenticated_domain_verification_decision",
                        "path": str(old_auth_verifier),
                        "sha256": old_auth_verifier_sha,
                    },
                    "result_artifact_snapshots": [
                        {
                            "role": "primary_result",
                            "path": str(old_result),
                            "sha256": old_result_sha,
                        }
                    ],
                    "authenticated_inference_binding": old_authenticated_binding,
                    "scientific_authority_applied": False,
                }
            ],
        },
    }
    base_file = tmp_path / "base.json"
    base_sha = _write_json(base_file, base_graph)

    new_result = tmp_path / "new-result.json"
    new_result_sha = _write_json(new_result, {"new": "result"})
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
            "node_id": "new-result-node",
            "node_type": "simulation",
            "statement": "New bounded simulation result.",
            "artifact_bindings": [
                {
                    "role": "primary_result",
                    "path": str(new_result),
                    "sha256": new_result_sha,
                }
            ],
            "metadata": {"result_origin": "authorized_local_simulation"},
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": "new-tests",
            "inference_edge_id": "new-support",
            "relation": "supports",
            "rationale": "New diagnostic structural support proposal.",
        },
        "limitations": ["Diagnostic until consumer authentication."],
    }
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(proposal_file, proposal)
    verifier_file = tmp_path / "verification.json"
    _write_json(
        verifier_file,
        {
            "schema_version": "1.1",
            "decision_id": "decision-1",
            "transition_id": "transition-1",
            "proposal_sha256": proposal_sha,
            "base_graph_sha256": base_sha,
            "inference_edge_id": "new-support",
            "result_node_id": "new-result-node",
            "target_node_id": "hypothesis-1",
            "relation": "supports",
            "inference_scope": "structural",
            "verifier_id": "verifier-v1.1",
            "rationale": "Exact new diagnostic edge authenticated.",
            "limitations": [],
            "domain_verified": True,
        },
    )

    output = tmp_path / "bundle"
    manifest = apply_authenticated_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verifier_file,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
        output_dir=output,
    )
    boundary = manifest["autonomy_boundary"]
    assert manifest["inherited_domain_verified_relation_count"] == 1
    assert boundary["inherited_domain_verified_authority_preserved"] is True
    assert boundary["legacy_v10_verifier_promoted_by_authenticated_producer"] is False
    assert boundary["inherited_domain_verified_relations_reauthenticated_as_v11"] is False

    for source in (
        old_result,
        legacy_result,
        legacy_verifier,
        old_parent,
        old_proposal,
        old_auth_verifier,
        new_result,
        base_file,
        proposal_file,
        verifier_file,
    ):
        source.unlink()

    graph = json.loads((output / "epistemic_graph.json").read_text(encoding="utf-8"))
    old_node = next(item for item in graph["nodes"] if item["node_id"] == "old-result-node")
    assert old_node["artifact_bindings"][0]["path"].startswith("provenance/inherited/")
    old_edge = next(item for item in graph["edges"] if item["edge_id"] == "legacy-support")
    assert old_edge["verification_artifact"]["path"].startswith("provenance/inherited/")
    old_lineage = graph["metadata"]["authenticated_transition_lineage"][0]
    assert old_lineage["base_graph_artifact"]["path"].startswith("provenance/inherited/")
    assert old_lineage["proposal_artifact"]["path"].startswith("provenance/inherited/")
    assert old_lineage["verification_decision_artifact"]["path"].startswith(
        "provenance/inherited/"
    )
    assert old_lineage["result_artifact_snapshots"][0]["path"].startswith(
        "provenance/inherited/"
    )

    evaluation = evaluate_epistemic_graph(
        graph,
        program_state={"workstreams": []},
        artifact_root=output,
    )
    target = next(
        item for item in evaluation["assessments"] if item["node_id"] == "hypothesis-1"
    )
    assert target["status"] == "provisionally_supported"
    assert "legacy-support" in target["verified_support_edges"]
    assert "old-support" in target["diagnostic_relation_edges"]
    assert "new-support" in target["diagnostic_relation_edges"]
