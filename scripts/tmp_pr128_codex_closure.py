from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_transition_consumer.py")
TESTS = Path("tests/test_authenticated_transition_consumer.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")

    old = '''    raw_parts = text.split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        raise AuthenticatedTransitionConsumerError(
            f"{field} must not contain empty, dot, or parent components"
        )
    return tuple(raw_parts)
'''
    new = '''    raw_parts = text.split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        raise AuthenticatedTransitionConsumerError(
            f"{field} must not contain empty, dot, or parent components"
        )
    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CLOCK$",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
    forbidden = set('<>:"\\\\|?*')
    for part in raw_parts:
        if any(ord(char) < 32 or char in forbidden for char in part):
            raise AuthenticatedTransitionConsumerError(
                f"{field} contains a Windows-nonportable path component"
            )
        if part.endswith((" ", ".")):
            raise AuthenticatedTransitionConsumerError(
                f"{field} contains a Windows-nonportable trailing space or dot"
            )
        basename = part.split(".", 1)[0].upper()
        if basename in reserved_names:
            raise AuthenticatedTransitionConsumerError(
                f"{field} contains a Windows-reserved path component"
            )
    return tuple(raw_parts)
'''
    text = replace_once(text, old, new, "portable-path")

    old = '''    normalized_metadata = dict(result_metadata)
    normalized_metadata["result_origin"] = _enum(
        result_metadata["result_origin"],
        _RESULT_ORIGINS,
        "transition proposal result_node.metadata.result_origin",
    )
    if "claim_scope" in normalized_metadata:
        normalized_metadata["claim_scope"] = _enum(
            normalized_metadata["claim_scope"],
            _TARGET_CLAIM_SCOPES,
            "transition proposal result_node.metadata.claim_scope",
        )
    if "notes" in normalized_metadata:
        normalized_metadata["notes"] = _text(
            normalized_metadata["notes"],
            "transition proposal result_node.metadata.notes",
        )
'''
    new = '''    normalized_metadata = dict(result_metadata)
    normalized_metadata["result_origin"] = _enum(
        result_metadata["result_origin"],
        _RESULT_ORIGINS,
        "transition proposal result_node.metadata.result_origin",
    )
    # Producer validation preserves optional claim_scope/notes values verbatim.
    # They are opaque result metadata here and must not be upgraded into provenance.
    result_origin = str(normalized_metadata["result_origin"])
    result_node_type = _enum(
        result_node["node_type"],
        _RESULT_NODE_TYPES,
        "transition proposal result_node.node_type",
    )
    execution_mode = str(action["execution_mode"])
    if execution_mode == "typed_local_action" and result_origin in {
        "external_physical_experiment",
        "external_analysis",
    }:
        raise AuthenticatedTransitionConsumerError(
            "external physical/analysis results require execution_mode=external_result_ingest"
        )
    if execution_mode == "external_result_ingest" and result_origin in {
        "authorized_local_analysis",
        "authorized_local_simulation",
    }:
        raise AuthenticatedTransitionConsumerError(
            "authorized local results require execution_mode=typed_local_action"
        )
    if result_node_type == "simulation" and result_origin != "authorized_local_simulation":
        raise AuthenticatedTransitionConsumerError(
            "simulation nodes require authorized_local_simulation origin"
        )
    if result_node_type == "analysis" and result_origin not in {
        "authorized_local_analysis",
        "external_analysis",
    }:
        raise AuthenticatedTransitionConsumerError(
            "analysis nodes require an analysis result origin"
        )
'''
    text = replace_once(text, old, new, "proposal-metadata-compatibility")
    text = replace_once(
        text,
        '''            "node_type": _enum(
                result_node["node_type"],
                _RESULT_NODE_TYPES,
                "transition proposal result_node.node_type",
            ),
''',
        '''            "node_type": result_node_type,
''',
        "reuse-result-node-type",
    )

    marker = '''def _validate_inference_scope(
    *,
    proposal: Mapping[str, Any],
    inference_scope: str,
    target_claim_scope: str | None,
) -> None:
'''
    replacement = marker + '''    if inference_scope in {"empirical_derived", "empirical_direct"}:
        raise AuthenticatedTransitionConsumerError(
            "empirical inference remains fail-closed until checksum-bound resolvable evidence-origin provenance is authenticated"
        )
'''
    text = replace_once(text, marker, replacement, "empirical-scope-closure")

    marker = '''def _verify_graph_realization(
'''
    if text.count(marker) != 1:
        raise SystemExit(f"successor helper insertion anchor count={text.count(marker)}")
    helper = r'''

def _artifact_role_sha_identity(value: object, *, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise AuthenticatedTransitionConsumerError(f"{field} must be a list")
    result: list[dict[str, str]] = []
    roles: set[str] = set()
    for index, item in enumerate(value):
        raw = _exact_object(
            item,
            required={"role", "path", "sha256"},
            allowed={"role", "path", "sha256"},
            field=f"{field}[{index}]",
        )
        role = _text(raw["role"], f"{field}[{index}].role")
        if role in roles:
            raise AuthenticatedTransitionConsumerError(f"{field} roles must be unique")
        roles.add(role)
        result.append(
            {
                "role": role,
                "sha256": _sha256_text(raw["sha256"], f"{field}[{index}].sha256"),
            }
        )
    return result


def _node_append_identity(value: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    result = dict(value)
    if "artifact_bindings" in result:
        result["artifact_bindings"] = _artifact_role_sha_identity(
            result["artifact_bindings"], field=f"{field}.artifact_bindings"
        )
    return result


def _edge_append_identity(value: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    result = dict(value)
    verifier = result.get("verification_artifact")
    if verifier is not None:
        raw = _exact_object(
            verifier,
            required={"role", "path", "sha256"},
            allowed={"role", "path", "sha256"},
            field=f"{field}.verification_artifact",
        )
        result["verification_artifact"] = {
            "role": _text(raw["role"], f"{field}.verification_artifact.role"),
            "sha256": _sha256_text(
                raw["sha256"], f"{field}.verification_artifact.sha256"
            ),
        }
    return result


def _lineage_artifact_identity(
    value: object, *, field: str, require_role: bool
) -> dict[str, str]:
    binding = _artifact_binding(
        value,
        field=field,
        require_role=require_role,
        expected_role=_AUTHENTICATED_VERIFIER_ROLE if require_role and "verification" in field else None,
    )
    result = {"sha256": str(binding["sha256"])}
    if require_role:
        result["role"] = str(binding["role"])
    return result


def _authenticated_lineage_append_identity(
    value: object, *, field: str
) -> dict[str, Any]:
    raw = _exact_object(
        value,
        required=set(_AUTHENTICATED_LINEAGE_KEYS),
        allowed=set(_AUTHENTICATED_LINEAGE_KEYS),
        field=field,
    )
    snapshots = raw["result_artifact_snapshots"]
    if not isinstance(snapshots, list):
        raise AuthenticatedTransitionConsumerError(
            f"{field}.result_artifact_snapshots must be a list"
        )
    return {
        "schema_version": raw["schema_version"],
        "transition_id": _text(raw["transition_id"], f"{field}.transition_id"),
        "base_graph_artifact": _lineage_artifact_identity(
            raw["base_graph_artifact"], field=f"{field}.base_graph_artifact", require_role=False
        ),
        "proposal_artifact": _lineage_artifact_identity(
            raw["proposal_artifact"], field=f"{field}.proposal_artifact", require_role=False
        ),
        "verification_decision_artifact": _lineage_artifact_identity(
            raw["verification_decision_artifact"],
            field=f"{field}.verification_decision_artifact",
            require_role=True,
        ),
        "result_artifact_snapshots": [
            _lineage_artifact_identity(
                item,
                field=f"{field}.result_artifact_snapshots[{index}]",
                require_role=True,
            )
            for index, item in enumerate(snapshots)
        ],
        "authenticated_inference_binding": dict(raw["authenticated_inference_binding"])
        if isinstance(raw["authenticated_inference_binding"], Mapping)
        else raw["authenticated_inference_binding"],
        "scientific_authority_applied": raw["scientific_authority_applied"],
    }


def _metadata_list(value: Mapping[str, Any], key: str, *, field: str) -> list[Any]:
    raw = value.get(key, [])
    if not isinstance(raw, list):
        raise AuthenticatedTransitionConsumerError(f"{field}.{key} must be a list")
    return raw


def _verify_successor_is_exact_append(
    *,
    base_graph: Mapping[str, Any],
    successor_graph: Mapping[str, Any],
    proposal: Mapping[str, Any],
) -> None:
    base_nodes = _normalized_graph_ids(
        base_graph.get("nodes"), id_field="node_id", field="base graph nodes"
    )
    base_edges = _normalized_graph_ids(
        base_graph.get("edges"), id_field="edge_id", field="base graph edges"
    )
    successor_nodes = _normalized_graph_ids(
        successor_graph.get("nodes"), id_field="node_id", field="epistemic graph nodes"
    )
    successor_edges = _normalized_graph_ids(
        successor_graph.get("edges"), id_field="edge_id", field="epistemic graph edges"
    )
    result_id = str(proposal["result_node"]["node_id"])
    tests_edge_id = str(proposal["proposed_inference"]["tests_edge_id"])
    inference_edge_id = str(proposal["proposed_inference"]["inference_edge_id"])
    if result_id in base_nodes or tests_edge_id in base_edges or inference_edge_id in base_edges:
        raise AuthenticatedTransitionConsumerError(
            "authenticated transition IDs must be absent from the exact bound base graph"
        )
    if set(successor_nodes) != set(base_nodes) | {result_id}:
        raise AuthenticatedTransitionConsumerError(
            "successor node set is not the exact bound base plus one authenticated result node"
        )
    if set(successor_edges) != set(base_edges) | {tests_edge_id, inference_edge_id}:
        raise AuthenticatedTransitionConsumerError(
            "successor edge set is not the exact bound base plus the authenticated tests/directional edges"
        )
    for node_id, base_node in base_nodes.items():
        if _node_append_identity(
            base_node, field=f"base graph node {node_id}"
        ) != _node_append_identity(
            successor_nodes[node_id], field=f"successor inherited node {node_id}"
        ):
            raise AuthenticatedTransitionConsumerError(
                f"successor inherited node {node_id} diverges from the exact bound base"
            )
    for edge_id, base_edge in base_edges.items():
        if _edge_append_identity(
            base_edge, field=f"base graph edge {edge_id}"
        ) != _edge_append_identity(
            successor_edges[edge_id], field=f"successor inherited edge {edge_id}"
        ):
            raise AuthenticatedTransitionConsumerError(
                f"successor inherited edge {edge_id} diverges from the exact bound base"
            )

    base_metadata = base_graph.get("metadata")
    successor_metadata = successor_graph.get("metadata")
    if base_metadata is None:
        base_metadata = {}
    if not isinstance(base_metadata, Mapping) or not isinstance(successor_metadata, Mapping):
        raise AuthenticatedTransitionConsumerError(
            "base/successor graph metadata must be objects for append-only verification"
        )
    lineage_keys = {"transition_lineage", "authenticated_transition_lineage"}
    base_other = {key: value for key, value in base_metadata.items() if key not in lineage_keys}
    successor_other = {
        key: value for key, value in successor_metadata.items() if key not in lineage_keys
    }
    if base_other != successor_other:
        raise AuthenticatedTransitionConsumerError(
            "successor graph rewrites non-lineage metadata from the exact bound base"
        )
    base_legacy = _metadata_list(base_metadata, "transition_lineage", field="base metadata")
    successor_legacy = _metadata_list(
        successor_metadata, "transition_lineage", field="successor metadata"
    )
    if len(successor_legacy) != len(base_legacy) + 1 or successor_legacy[:-1] != base_legacy:
        raise AuthenticatedTransitionConsumerError(
            "successor legacy transition lineage is not an exact one-record append"
        )
    base_authenticated = _metadata_list(
        base_metadata, "authenticated_transition_lineage", field="base metadata"
    )
    successor_authenticated = _metadata_list(
        successor_metadata, "authenticated_transition_lineage", field="successor metadata"
    )
    if len(successor_authenticated) != len(base_authenticated) + 1:
        raise AuthenticatedTransitionConsumerError(
            "successor authenticated lineage is not an exact one-record append"
        )
    for index, base_record in enumerate(base_authenticated):
        if _authenticated_lineage_append_identity(
            base_record, field=f"base authenticated lineage[{index}]"
        ) != _authenticated_lineage_append_identity(
            successor_authenticated[index], field=f"successor authenticated lineage[{index}]"
        ):
            raise AuthenticatedTransitionConsumerError(
                "successor rewrites inherited authenticated-lineage identity"
            )
'''
    text = text.replace(marker, helper + marker, 1)

    call_anchor = '''    _verify_graph_realization(
        graph,
        proposal=proposal,
        binding=recomputed,
        result_snapshots=result_bindings,
    )
'''
    call_replacement = '''    _verify_successor_is_exact_append(
        base_graph=base_graph,
        successor_graph=graph,
        proposal=proposal,
    )
    _verify_graph_realization(
        graph,
        proposal=proposal,
        binding=recomputed,
        result_snapshots=result_bindings,
    )
'''
    text = replace_once(text, call_anchor, call_replacement, "successor-append-call")
    SOURCE.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    text += r'''


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
'''
    # Tests use module-private validators intentionally for producer/consumer contract parity.
    import_anchor = '''from materials_data_analyzer.research_loop.authenticated_transition_consumer import (
    AuthenticatedTransitionConsumerError,
    authenticate_transition_bundle,
)
'''
    import_replacement = '''from materials_data_analyzer.research_loop import authenticated_transition_consumer as module
from materials_data_analyzer.research_loop.authenticated_transition_consumer import (
    AuthenticatedTransitionConsumerError,
    authenticate_transition_bundle,
)
'''
    text = replace_once(text, import_anchor, import_replacement, "consumer-module-import")
    TESTS.write_text(text, encoding="utf-8")


def main() -> None:
    patch_source()
    patch_tests()


if __name__ == "__main__":
    main()
