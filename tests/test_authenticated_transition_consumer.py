from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    authenticated_transition_consumer as module,
)
from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    apply_authenticated_epistemic_transition_files,
)
from materials_data_analyzer.research_loop.authenticated_transition_consumer import (
    AuthenticatedTransitionConsumerError,
    authenticate_transition_bundle,
)


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _base_graph() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "graph_id": "graph-v1",
        "research_scope": "independent bundle consumer regression",
        "nodes": [
            {
                "node_id": "question-1",
                "node_type": "research_question",
                "statement": "What does the bounded result establish?",
            },
            {
                "node_id": "hypothesis-1",
                "node_type": "hypothesis",
                "statement": "The target proposition holds within structural scope.",
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


def _proposal(*, base_sha: str, result_sha: str) -> dict[str, object]:
    return {
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
                {
                    "role": "primary_result",
                    "path": "result.json",
                    "sha256": result_sha,
                }
            ],
            "metadata": {"result_origin": "authorized_local_simulation"},
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": "tests-1",
            "inference_edge_id": "inference-1",
            "relation": "supports",
            "rationale": "The bounded simulation supports the structural target.",
        },
        "limitations": ["Structural scope only."],
    }


def _verification(*, proposal_sha: str, base_sha: str) -> dict[str, object]:
    return {
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
        "rationale": "The exact edge is verified only in structural scope.",
        "limitations": ["No positive closeout is granted."],
        "domain_verified": True,
    }


def _make_bundle(tmp_path: Path) -> Path:
    result = tmp_path / "result.json"
    result_sha = _write_json(result, {"rank_before": 3, "rank_after": 4})
    base = tmp_path / "base.json"
    base_sha = _write_json(base, _base_graph())
    proposal = tmp_path / "proposal.json"
    proposal_sha = _write_json(
        proposal, _proposal(base_sha=base_sha, result_sha=result_sha)
    )
    verification = tmp_path / "verification.json"
    _write_json(
        verification,
        _verification(proposal_sha=proposal_sha, base_sha=base_sha),
    )
    output = tmp_path / "bundle"
    apply_authenticated_epistemic_transition_files(
        base_graph_path=base,
        proposal_path=proposal,
        verification_decision_path=verification,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
        output_dir=output,
    )
    return output


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _rewrite_graph_and_sync_manifest(bundle: Path, graph: dict[str, object]) -> None:
    graph_sha = _write_json(bundle / "epistemic_graph.json", graph)
    manifest = _load_json(bundle / "epistemic_transition_manifest.json")
    successor = manifest["successor_graph"]
    assert isinstance(successor, dict)
    successor["sha256"] = graph_sha
    _write_json(bundle / "epistemic_transition_manifest.json", manifest)


def _current_lineage(graph: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    metadata = graph["metadata"]
    assert isinstance(metadata, dict)
    authenticated = metadata["authenticated_transition_lineage"]
    legacy = metadata["transition_lineage"]
    assert isinstance(authenticated, list) and isinstance(legacy, list)
    current = authenticated[-1]
    current_legacy = legacy[-1]
    assert isinstance(current, dict) and isinstance(current_legacy, dict)
    return current, current_legacy


def test_consumer_reauthenticates_current_transition_without_scientific_upgrade(
    tmp_path: Path,
) -> None:
    bundle = _make_bundle(tmp_path)
    report = authenticate_transition_bundle(bundle)

    assert report["current_transition_exact_provenance_authenticated"] is True
    assert report["transition_id"] == "transition-1"
    assert report["inference_edge_id"] == "inference-1"
    assert report["relation"] == "supports"
    assert report["inference_scope"] == "structural"
    boundary = report["authority_boundary"]
    assert boundary["scientific_authority_applied"] is False
    assert boundary["execution_authorized"] is False
    assert boundary["positive_closeout_granted"] is False
    assert boundary["verifier_identity_or_credential_authenticated"] is False
    assert boundary["support_independence_established"] is False
    assert boundary["empirical_origin_independently_established"] is False
    assert boundary["historical_authenticated_lineage_chain_reauthenticated"] is False
    assert boundary["manifest_authority_flags_used_as_authentication_evidence"] is False


def test_consumer_bundle_remains_valid_after_directory_relocation(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    relocated = tmp_path / "relocated" / "bundle"
    relocated.parent.mkdir()
    shutil.copytree(bundle, relocated)

    report = authenticate_transition_bundle(relocated)
    assert report["current_transition_exact_provenance_authenticated"] is True
    assert Path(report["bundle_root"]) == relocated.resolve()


def test_manifest_authority_booleans_cannot_elevate_consumer_report(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    manifest_path = bundle / "epistemic_transition_manifest.json"
    manifest = _load_json(manifest_path)
    manifest["scientific_authority_applied"] = True
    manifest["domain_verification_decision_authenticated"] = False
    boundary = manifest.get("autonomy_boundary")
    assert isinstance(boundary, dict)
    boundary["positive_closeout_granted_by_authentication"] = True
    _write_json(manifest_path, manifest)

    report = authenticate_transition_bundle(bundle)
    assert report["current_transition_exact_provenance_authenticated"] is True
    assert report["authority_boundary"]["scientific_authority_applied"] is False
    assert report["authority_boundary"]["positive_closeout_granted"] is False


def test_consumer_rejects_exact_proposal_byte_drift(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    graph = _load_json(bundle / "epistemic_graph.json")
    current, _ = _current_lineage(graph)
    proposal_binding = current["proposal_artifact"]
    assert isinstance(proposal_binding, dict)
    proposal_path = bundle / str(proposal_binding["path"])
    proposal_path.write_bytes(proposal_path.read_bytes() + b" ")

    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="proposal_artifact checksum",
    ):
        authenticate_transition_bundle(bundle)


def test_consumer_rejects_result_snapshot_drift(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    graph = _load_json(bundle / "epistemic_graph.json")
    current, _ = _current_lineage(graph)
    snapshots = current["result_artifact_snapshots"]
    assert isinstance(snapshots, list) and isinstance(snapshots[0], dict)
    result_path = bundle / str(snapshots[0]["path"])
    result_path.write_bytes(result_path.read_bytes() + b"\n")

    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match=r"result_artifact_snapshots\[0\] checksum",
    ):
        authenticate_transition_bundle(bundle)


def test_consumer_rejects_forged_stored_binding_even_if_manifest_is_synced(
    tmp_path: Path,
) -> None:
    bundle = _make_bundle(tmp_path)
    graph = _load_json(bundle / "epistemic_graph.json")
    current, _ = _current_lineage(graph)
    stored = current["authenticated_inference_binding"]
    assert isinstance(stored, dict)
    stored["inference_edge_id"] = "forged-edge"
    manifest = _load_json(bundle / "epistemic_transition_manifest.json")
    manifest["authenticated_inference_binding"] = dict(stored)
    _write_json(bundle / "epistemic_transition_manifest.json", manifest)
    _rewrite_graph_and_sync_manifest(bundle, graph)

    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="does not equal independent recomputation",
    ):
        authenticate_transition_bundle(bundle)


def test_consumer_rejects_graph_directional_edge_authority_escalation(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    graph = _load_json(bundle / "epistemic_graph.json")
    edges = graph["edges"]
    assert isinstance(edges, list)
    inference = next(
        item for item in edges if isinstance(item, dict) and item.get("edge_id") == "inference-1"
    )
    inference["assessment_level"] = "domain_verified"
    inference["verification_artifact"] = {
        "role": "forged",
        "path": "epistemic_transition_manifest.json",
        "sha256": "0" * 64,
    }
    _rewrite_graph_and_sync_manifest(bundle, graph)

    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="directional edge is not the diagnostic exact authenticated edge",
    ):
        authenticate_transition_bundle(bundle)


def test_consumer_rejects_different_graph_edge_id_for_same_triple(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    graph = _load_json(bundle / "epistemic_graph.json")
    edges = graph["edges"]
    assert isinstance(edges, list)
    inference = next(
        item for item in edges if isinstance(item, dict) and item.get("edge_id") == "inference-1"
    )
    inference["edge_id"] = "different-edge"
    _rewrite_graph_and_sync_manifest(bundle, graph)

    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="directional edge",
    ):
        authenticate_transition_bundle(bundle)


def test_consumer_rejects_bundle_path_escape_from_lineage(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    graph = _load_json(bundle / "epistemic_graph.json")
    current, _ = _current_lineage(graph)
    snapshots = current["result_artifact_snapshots"]
    assert isinstance(snapshots, list) and isinstance(snapshots[0], dict)
    snapshots[0]["path"] = "../outside.json"
    _rewrite_graph_and_sync_manifest(bundle, graph)

    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="portable relative bundle path|parent components",
    ):
        authenticate_transition_bundle(bundle)


def test_consumer_rejects_manifest_binding_substitution(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    manifest_path = bundle / "epistemic_transition_manifest.json"
    manifest = _load_json(manifest_path)
    base_binding = manifest["base_graph_binding"]
    assert isinstance(base_binding, dict)
    base_binding["sha256"] = "0" * 64
    _write_json(manifest_path, manifest)

    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="manifest base_graph_binding does not match",
    ):
        authenticate_transition_bundle(bundle)


def test_consumer_rejects_current_legacy_lineage_identity_drift(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    graph = _load_json(bundle / "epistemic_graph.json")
    _, legacy = _current_lineage(graph)
    legacy["parent_graph_id"] = "unrelated-graph"
    _rewrite_graph_and_sync_manifest(bundle, graph)

    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="current legacy lineage does not identify the same exact transition",
    ):
        authenticate_transition_bundle(bundle)



def test_consumer_rejects_extra_domain_verified_edge_not_in_bound_base(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    graph = _load_json(bundle / "epistemic_graph.json")
    edges = graph["edges"]
    assert isinstance(edges, list)
    edges.append(
        {
            "edge_id": "grafted-verified-support",
            "source_node_id": "result-1",
            "target_node_id": "hypothesis-1",
            "relation": "supports",
            "assessment_level": "domain_verified",
            "rationale": "Grafted authority must not survive independent authentication.",
            "active": True,
        }
    )
    _rewrite_graph_and_sync_manifest(bundle, graph)
    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="successor edge set is not the exact bound base",
    ):
        authenticate_transition_bundle(bundle)


def test_consumer_rejects_deleted_inherited_base_edge(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    graph = _load_json(bundle / "epistemic_graph.json")
    edges = graph["edges"]
    assert isinstance(edges, list)
    graph["edges"] = [
        item
        for item in edges
        if not (isinstance(item, dict) and item.get("edge_id") == "motivation-1")
    ]
    _rewrite_graph_and_sync_manifest(bundle, graph)
    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="successor edge set is not the exact bound base",
    ):
        authenticate_transition_bundle(bundle)


def test_consumer_keeps_empirical_direct_closed_without_origin_artifact() -> None:
    proposal = _proposal(base_sha="a" * 64, result_sha="b" * 64)
    result_node = proposal["result_node"]
    assert isinstance(result_node, dict)
    result_node["node_type"] = "experiment"
    metadata = result_node["metadata"]
    assert isinstance(metadata, dict)
    metadata["result_origin"] = "external_physical_experiment"
    source_action = proposal["source_action"]
    assert isinstance(source_action, dict)
    source_action["execution_mode"] = "external_result_ingest"
    normalized = module._normalize_proposal(proposal)
    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="evidence-origin provenance",
    ):
        module._validate_inference_scope(
            proposal=normalized,
            inference_scope="empirical_direct",
            target_claim_scope="empirical",
        )


def test_consumer_enforces_producer_action_result_origin_compatibility() -> None:
    proposal = _proposal(base_sha="a" * 64, result_sha="b" * 64)
    result_node = proposal["result_node"]
    assert isinstance(result_node, dict)
    metadata = result_node["metadata"]
    assert isinstance(metadata, dict)
    metadata["result_origin"] = "external_physical_experiment"
    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="external physical/analysis results require execution_mode=external_result_ingest",
    ):
        module._normalize_proposal(proposal)


def test_consumer_preserves_producer_supported_opaque_result_metadata() -> None:
    proposal = _proposal(base_sha="a" * 64, result_sha="b" * 64)
    result_node = proposal["result_node"]
    assert isinstance(result_node, dict)
    metadata = result_node["metadata"]
    assert isinstance(metadata, dict)
    metadata["notes"] = {"structured": [1, 2, 3]}
    metadata["claim_scope"] = {"opaque": "producer-preserved"}
    normalized = module._normalize_proposal(proposal)
    normalized_metadata = normalized["result_node"]["metadata"]
    assert normalized_metadata["notes"] == {"structured": [1, 2, 3]}
    assert normalized_metadata["claim_scope"] == {"opaque": "producer-preserved"}


@pytest.mark.parametrize(
    "value",
    [
        "provenance/file:payload.json",
        "provenance/CON/file.json",
        "provenance/trailing./file.json",
        "provenance/trailing /file.json",
        "provenance/a?b/file.json",
    ],
)
def test_consumer_rejects_windows_nonportable_bundle_components(value: str) -> None:
    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="Windows-(?:nonportable|reserved)",
    ):
        module._relative_bundle_parts(value, "binding.path")


def test_consumer_rejects_successor_that_violates_graph_schema_even_when_manifest_hash_is_synced(
    tmp_path: Path,
) -> None:
    bundle = _make_bundle(tmp_path)
    graph = _load_json(bundle / "epistemic_graph.json")
    graph["unauthenticated_authority_override"] = True
    _rewrite_graph_and_sync_manifest(bundle, graph)

    with pytest.raises(
        AuthenticatedTransitionConsumerError,
        match="epistemic graph contract",
    ):
        authenticate_transition_bundle(bundle)
