from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_epistemic_transition.py")
MERGE_GATE = Path("tests/test_authenticated_epistemic_transition_merge_gate.py")
CORE_TEST = Path("tests/test_authenticated_epistemic_transition.py")
DOC = Path("docs/AUTHENTICATED_EPISTEMIC_TRANSITION.md")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.8"',
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.9"',
        label="policy version",
    )
    text = replace_once(
        text,
        'AUTHENTICATED_TRANSITION_SUPPORTED_PUBLICATION_PLATFORMS = ("linux", "windows")\n',
        '''AUTHENTICATED_TRANSITION_SUPPORTED_PUBLICATION_PLATFORMS = ("linux", "windows")\n_AUTHENTICATED_TRANSITION_LINEAGE_KEYS = frozenset(\n    {\n        "schema_version",\n        "transition_id",\n        "base_graph_artifact",\n        "proposal_artifact",\n        "verification_decision_artifact",\n        "result_artifact_snapshots",\n        "authenticated_inference_binding",\n        "scientific_authority_applied",\n    }\n)\n''',
        label="lineage key contract",
    )

    anchor = 'def _materialize_and_validate_historical_base_graph(\n'
    helpers = r'''def _assert_current_base_artifact_hashes_canonical(
    base_graph: Mapping[str, Any],
) -> None:
    nodes = base_graph.get("nodes")
    if isinstance(nodes, list):
        for node_index, node in enumerate(nodes):
            if not isinstance(node, Mapping):
                continue
            bindings = node.get("artifact_bindings")
            if not isinstance(bindings, list):
                continue
            for artifact_index, binding in enumerate(bindings):
                if not isinstance(binding, Mapping):
                    continue
                _lineage_sha256(
                    binding,
                    "sha256",
                )
                _lineage_identity(binding, "role")
    edges = base_graph.get("edges")
    if isinstance(edges, list):
        for edge_index, edge in enumerate(edges):
            if not isinstance(edge, Mapping):
                continue
            verifier = edge.get("verification_artifact")
            if not isinstance(verifier, Mapping):
                continue
            _lineage_sha256(verifier, "sha256")
            _lineage_identity(verifier, "role")


def _payload_json_object(
    binding: Mapping[str, Any],
    *,
    payloads: Mapping[str, bytes],
    field: str,
) -> tuple[dict[str, Any], bytes, str]:
    path = _lineage_identity(binding, "path")
    expected_sha = _lineage_sha256(binding, "sha256")
    raw = payloads.get(path)
    if raw is None:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} payload is absent from the staged provenance set"
        )
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} staged payload hash diverges from its authenticated binding"
        )
    return _json_object_from_exact_bytes(raw, field=field), raw, actual_sha


def _graph_structure_ids(
    graph: Mapping[str, Any], *, field: str
) -> tuple[set[str], set[str]]:
    nodes = _unique_id_map(graph.get("nodes"), id_field="node_id", field=f"{field}.nodes")
    edges = _unique_id_map(graph.get("edges"), id_field="edge_id", field=f"{field}.edges")
    return set(nodes), set(edges)


def _assert_authenticated_lineage_chain(
    metadata: Mapping[str, Any],
    *,
    enclosing_graph: Mapping[str, Any],
    enclosing_graph_bytes: bytes,
    enclosing_graph_sha256: str,
    program_state: Mapping[str, Any],
    artifact_root: Path,
    payloads: Mapping[str, bytes],
) -> None:
    authenticated = _lineage_records(
        metadata, field="authenticated_transition_lineage"
    )
    if not authenticated:
        return
    legacy = _lineage_records(metadata, field="transition_lineage")
    if len(authenticated) > len(legacy):
        raise AuthenticatedEpistemicTransitionError(
            "authenticated lineage cannot exceed legacy transition history"
        )
    authenticated_ids = [
        _lineage_identity(item, "transition_id") for item in authenticated
    ]
    legacy_suffix = legacy[-len(authenticated) :]
    legacy_suffix_ids = [
        _lineage_identity(item, "transition_id") for item in legacy_suffix
    ]
    if authenticated_ids != legacy_suffix_ids:
        raise AuthenticatedEpistemicTransitionError(
            "authenticated lineage must form a consecutive suffix of transition_lineage"
        )

    canonical_enclosing_sha = _lineage_sha256(
        {"sha256": enclosing_graph_sha256}, "sha256"
    )
    if hashlib.sha256(enclosing_graph_bytes).hexdigest() != canonical_enclosing_sha:
        raise AuthenticatedEpistemicTransitionError(
            "enclosing graph bytes do not match the authenticated current base SHA-256"
        )
    parsed_enclosing = _json_object_from_exact_bytes(
        enclosing_graph_bytes, field="enclosing_graph"
    )
    if parsed_enclosing != dict(enclosing_graph):
        raise AuthenticatedEpistemicTransitionError(
            "enclosing graph object diverges from its exact authenticated bytes"
        )

    parsed_entries: list[dict[str, Any]] = []
    for index, record in enumerate(authenticated):
        field = f"authenticated_transition_lineage[{index}]"
        base_binding = record.get("base_graph_artifact")
        proposal_binding = record.get("proposal_artifact")
        if not isinstance(base_binding, Mapping) or not isinstance(proposal_binding, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} lacks graph-chain artifact bindings"
            )
        base_graph, base_bytes, base_sha = _payload_json_object(
            base_binding,
            payloads=payloads,
            field=f"{field}.base_graph_artifact",
        )
        proposal, _, _ = _payload_json_object(
            proposal_binding,
            payloads=payloads,
            field=f"{field}.proposal_artifact",
        )
        parsed_entries.append(
            {
                "record": record,
                "base_graph": base_graph,
                "base_bytes": base_bytes,
                "base_sha256": base_sha,
                "proposal": proposal,
            }
        )

    for index, entry in enumerate(parsed_entries):
        field = f"authenticated_transition_lineage[{index}]"
        record = entry["record"]
        base_graph = entry["base_graph"]
        proposal = entry["proposal"]
        legacy_record = legacy_suffix[index]
        parent_graph_id = _lineage_identity(legacy_record, "parent_graph_id")
        exact_base_graph_id = _lineage_identity(base_graph, "graph_id")
        if parent_graph_id != exact_base_graph_id:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} legacy parent_graph_id does not match the exact authenticated base graph"
            )
        if _lineage_sha256(legacy_record, "parent_graph_sha256") != entry["base_sha256"]:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} legacy parent graph SHA-256 does not match the exact authenticated base"
            )

        if index + 1 < len(parsed_entries):
            successor = parsed_entries[index + 1]["base_graph"]
            successor_bytes = parsed_entries[index + 1]["base_bytes"]
            successor_sha = parsed_entries[index + 1]["base_sha256"]
        else:
            successor = enclosing_graph
            successor_bytes = enclosing_graph_bytes
            successor_sha = canonical_enclosing_sha
        if hashlib.sha256(successor_bytes).hexdigest() != successor_sha:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} successor graph bytes do not match the next authenticated base SHA-256"
            )
        new_graph_id = _lineage_identity(proposal, "new_graph_id")
        successor_graph_id = _lineage_identity(successor, "graph_id")
        if new_graph_id != successor_graph_id:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} proposal new_graph_id does not continue to the next authenticated graph"
            )

        historical_base = _materialize_and_validate_historical_base_graph(
            base_graph,
            enclosing_graph=successor,
            program_state=program_state,
            artifact_root=artifact_root,
            field=f"{field}.chain_base_graph",
        )
        result_snapshots = record.get("result_artifact_snapshots")
        if not isinstance(result_snapshots, list):
            raise AuthenticatedEpistemicTransitionError(
                f"{field}.result_artifact_snapshots must be a list"
            )
        result_artifacts = [
            {
                "role": _lineage_identity(item, "role"),
                "path": _lineage_identity(item, "path"),
                "sha256": _lineage_sha256(item, "sha256"),
            }
            for item in result_snapshots
            if isinstance(item, Mapping)
        ]
        _assert_inherited_transition_matches_enclosing_graph(
            proposal=proposal,
            enclosing_graph=successor,
            result_artifacts=result_artifacts,
            field=f"{field}.chain_successor",
        )
        base_node_ids, base_edge_ids = _graph_structure_ids(
            historical_base, field=f"{field}.chain_base_graph"
        )
        expected_node, expected_tests, expected_inference = _proposal_result_and_edges(
            proposal, result_artifact_bindings=result_artifacts
        )
        successor_node_ids, successor_edge_ids = _graph_structure_ids(
            successor, field=f"{field}.chain_successor"
        )
        expected_node_ids = base_node_ids | {str(expected_node["node_id"])}
        expected_edge_ids = base_edge_ids | {
            str(expected_tests["edge_id"]),
            str(expected_inference["edge_id"]),
        }
        if successor_node_ids != expected_node_ids or successor_edge_ids != expected_edge_ids:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} successor graph contains structure outside the authenticated transition"
            )

'''
    text = replace_once(text, anchor, helpers + anchor, label="graph-chain helpers")

    text = replace_once(
        text,
        '''        record = copy.deepcopy(dict(raw_record))\n        if record.get("schema_version") != AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION:\n''',
        '''        raw_keys = set(raw_record)\n        if raw_keys != _AUTHENTICATED_TRANSITION_LINEAGE_KEYS:\n            unknown = sorted(raw_keys - _AUTHENTICATED_TRANSITION_LINEAGE_KEYS)\n            missing = sorted(_AUTHENTICATED_TRANSITION_LINEAGE_KEYS - raw_keys)\n            raise AuthenticatedEpistemicTransitionError(\n                f"{field} must use the exact producer lineage key set; "\n                f"unknown={unknown}, missing={missing}"\n            )\n        record = {\n            key: copy.deepcopy(raw_record[key])\n            for key in _AUTHENTICATED_TRANSITION_LINEAGE_KEYS\n        }\n        if record.get("schema_version") != AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION:\n''',
        label="exact lineage key set",
    )

    text = replace_once(
        text,
        '''def _remap_authenticated_lineage_artifacts(\n    metadata: dict[str, Any],\n    *,\n    enclosing_graph: Mapping[str, Any],\n    program_state: Mapping[str, Any],\n    artifact_root: Path,\n    payloads: dict[str, bytes],\n) -> None:\n''',
        '''def _remap_authenticated_lineage_artifacts(\n    metadata: dict[str, Any],\n    *,\n    enclosing_graph: Mapping[str, Any],\n    enclosing_graph_bytes: bytes,\n    enclosing_graph_sha256: str,\n    program_state: Mapping[str, Any],\n    artifact_root: Path,\n    payloads: dict[str, bytes],\n) -> None:\n''',
        label="authenticated remap signature",
    )
    text = replace_once(
        text,
        '''    metadata["authenticated_transition_lineage"] = remapped\n\n\ndef _remap_base_graph_artifacts(\n''',
        '''    metadata["authenticated_transition_lineage"] = remapped\n    _assert_authenticated_lineage_chain(\n        metadata,\n        enclosing_graph=enclosing_graph,\n        enclosing_graph_bytes=enclosing_graph_bytes,\n        enclosing_graph_sha256=enclosing_graph_sha256,\n        program_state=program_state,\n        artifact_root=artifact_root,\n        payloads=payloads,\n    )\n\n\ndef _remap_base_graph_artifacts(\n''',
        label="run authenticated graph chain",
    )
    text = replace_once(
        text,
        '''def _remap_base_graph_artifacts(\n    base_graph: Mapping[str, Any],\n    *,\n    program_state: Mapping[str, Any],\n    artifact_root: Path,\n    payloads: dict[str, bytes],\n) -> tuple[dict[str, Any], list[dict[str, Any]]]:\n''',
        '''def _remap_base_graph_artifacts(\n    base_graph: Mapping[str, Any],\n    *,\n    enclosing_graph_bytes: bytes,\n    enclosing_graph_sha256: str,\n    program_state: Mapping[str, Any],\n    artifact_root: Path,\n    payloads: dict[str, bytes],\n) -> tuple[dict[str, Any], list[dict[str, Any]]]:\n''',
        label="base remap signature",
    )
    text = replace_once(
        text,
        '''    _remap_authenticated_lineage_artifacts(\n        metadata,\n        enclosing_graph=graph,\n        program_state=program_state,\n''',
        '''    _remap_authenticated_lineage_artifacts(\n        metadata,\n        enclosing_graph=graph,\n        enclosing_graph_bytes=enclosing_graph_bytes,\n        enclosing_graph_sha256=enclosing_graph_sha256,\n        program_state=program_state,\n''',
        label="base remap passes exact enclosing bytes",
    )
    text = replace_once(
        text,
        '''    base_validated = validate_epistemic_graph(\n        base_raw,\n        program_state=program_state,\n        artifact_root=artifacts,\n    )\n''',
        '''    _assert_current_base_artifact_hashes_canonical(base_raw)\n    base_validated = validate_epistemic_graph(\n        base_raw,\n        program_state=program_state,\n        artifact_root=artifacts,\n    )\n''',
        label="current base canonical artifact preflight",
    )
    text = replace_once(
        text,
        '''    remapped_base, inherited_provenance = _remap_base_graph_artifacts(\n        base_raw,\n        program_state=program_state,\n''',
        '''    remapped_base, inherited_provenance = _remap_base_graph_artifacts(\n        base_raw,\n        enclosing_graph_bytes=base_bytes,\n        enclosing_graph_sha256=base_sha,\n        program_state=program_state,\n''',
        label="production exact base chain anchor",
    )
    SOURCE.write_text(text, encoding="utf-8")


def patch_merge_gate() -> None:
    text = MERGE_GATE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''        "metadata": {},\n    }\n    return lineage, enclosing\n''',
        '''        "metadata": {\n            "transition_lineage": [\n                {\n                    "transition_id": "old-auth",\n                    "parent_graph_id": "graph-v0",\n                    "parent_graph_sha256": base_sha,\n                    "proposal_sha256": proposal_sha,\n                    "verification_decision_sha256": verifier_sha,\n                    "result_node_id": "old-result",\n                }\n            ]\n        },\n    }\n    return lineage, enclosing\n''',
        label="valid fixture legacy lineage",
    )
    old_remap = '''def _remap_one_lineage(\n    tmp_path: Path,\n    lineage: dict[str, object],\n    enclosing: dict[str, object],\n) -> None:\n    _remap_authenticated_lineage_artifacts(\n        {"authenticated_transition_lineage": [lineage]},\n        enclosing_graph=enclosing,\n        program_state={"workstreams": []},\n        artifact_root=tmp_path,\n        payloads={},\n    )\n'''
    new_remap = '''def _remap_one_lineage(\n    tmp_path: Path,\n    lineage: dict[str, object],\n    enclosing: dict[str, object],\n) -> None:\n    metadata = enclosing.get("metadata")\n    assert isinstance(metadata, dict)\n    metadata["authenticated_transition_lineage"] = [lineage]\n    enclosing_bytes = (\n        json.dumps(enclosing, indent=2, sort_keys=True) + "\\n"\n    ).encode("utf-8")\n    _remap_authenticated_lineage_artifacts(\n        metadata,\n        enclosing_graph=enclosing,\n        enclosing_graph_bytes=enclosing_bytes,\n        enclosing_graph_sha256=hashlib.sha256(enclosing_bytes).hexdigest(),\n        program_state={"workstreams": []},\n        artifact_root=tmp_path,\n        payloads={},\n    )\n'''
    text = replace_once(text, old_remap, new_remap, label="direct lineage helper chain anchor")

    anchor = 'def test_cross_lineage_binding_transition_id_must_remain_text() -> None:\n'
    additions = r'''def test_inherited_lineage_rejects_unknown_authority_claim(tmp_path: Path) -> None:
    lineage, enclosing = _valid_historical_lineage_fixture(tmp_path)
    lineage["positive_closeout_granted"] = True
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="exact producer lineage key set",
    ):
        _remap_one_lineage(tmp_path, lineage, enclosing)


def test_inherited_legacy_parent_graph_id_must_match_exact_base(tmp_path: Path) -> None:
    lineage, enclosing = _valid_historical_lineage_fixture(tmp_path)
    metadata = enclosing["metadata"]
    assert isinstance(metadata, dict)
    legacy = metadata["transition_lineage"]
    assert isinstance(legacy, list)
    record = legacy[0]
    assert isinstance(record, dict)
    record["parent_graph_id"] = "wrong-parent"
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="parent_graph_id does not match the exact authenticated base graph",
    ):
        _remap_one_lineage(tmp_path, lineage, enclosing)


def test_inherited_authenticated_history_must_be_consecutive_legacy_suffix(
    tmp_path: Path,
) -> None:
    lineage, enclosing = _valid_historical_lineage_fixture(tmp_path)
    metadata = enclosing["metadata"]
    assert isinstance(metadata, dict)
    legacy = metadata["transition_lineage"]
    assert isinstance(legacy, list)
    legacy.append(
        {
            "transition_id": "legacy-after-auth",
            "parent_graph_id": "graph-v1",
            "parent_graph_sha256": "a" * 64,
            "proposal_sha256": "b" * 64,
            "verification_decision_sha256": "c" * 64,
            "result_node_id": "legacy-result",
        }
    )
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="consecutive suffix",
    ):
        _remap_one_lineage(tmp_path, lineage, enclosing)


def test_inherited_authenticated_successor_cannot_graft_extra_structure(
    tmp_path: Path,
) -> None:
    lineage, enclosing = _valid_historical_lineage_fixture(tmp_path)
    nodes = enclosing["nodes"]
    assert isinstance(nodes, list)
    nodes.append(
        {
            "node_id": "grafted-question",
            "node_type": "research_question",
            "statement": "Unrelated grafted structure.",
        }
    )
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="structure outside the authenticated transition",
    ):
        _remap_one_lineage(tmp_path, lineage, enclosing)


'''
    if "test_inherited_lineage_rejects_unknown_authority_claim" in text:
        raise RuntimeError("graph-chain regressions already present")
    text = replace_once(text, anchor, additions + anchor, label="graph-chain regressions")
    MERGE_GATE.write_text(text, encoding="utf-8")


def patch_core_test() -> None:
    text = CORE_TEST.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''            base,\n            program_state={"workstreams": []},\n            artifact_root=tmp_path,\n            payloads={},\n''',
        '''            base,\n            enclosing_graph_bytes=(json.dumps(base, sort_keys=True) + "\\n").encode("utf-8"),\n            enclosing_graph_sha256=hashlib.sha256(\n                (json.dumps(base, sort_keys=True) + "\\n").encode("utf-8")\n            ).hexdigest(),\n            program_state={"workstreams": []},\n            artifact_root=tmp_path,\n            payloads={},\n''',
        label="direct base remap test signature",
    )
    addition = r'''

def test_current_base_artifact_sha_must_be_canonical_for_replay(tmp_path: Path) -> None:
    inherited_result = tmp_path / "inherited-result.json"
    inherited_sha = _write_json(inherited_result, {"prior": 1})
    base = _base_graph()
    nodes = base["nodes"]
    assert isinstance(nodes, list)
    nodes.append(
        {
            "node_id": "prior-result",
            "node_type": "analysis",
            "statement": "Prior completed result.",
            "execution_status": "completed",
            "artifact_bindings": [
                {
                    "role": "primary_result",
                    "path": str(inherited_result),
                    "sha256": f" {inherited_sha} ",
                }
            ],
            "metadata": {"result_origin": "authorized_local_analysis"},
        }
    )
    base_file = tmp_path / "base_graph.json"
    base_sha = _write_json(base_file, base)
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"rank_before": 3, "rank_after": 4})
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(
        proposal_file,
        _proposal(base_sha=base_sha, result_sha=result_sha),
    )
    verification_file = tmp_path / "verification.json"
    _write_json(
        verification_file,
        _verification(proposal_sha=proposal_sha, base_sha=base_sha),
    )
    output = tmp_path / "out"

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="sha256 must be canonical lowercase SHA-256 text",
    ):
        apply_authenticated_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            verification_decision_path=verification_file,
            program_state=_program_state(),
            artifact_root=tmp_path,
            output_dir=output,
        )
    assert not output.exists()
'''
    if "test_current_base_artifact_sha_must_be_canonical_for_replay" in text:
        raise RuntimeError("current-base canonical regression already present")
    CORE_TEST.write_text(text.rstrip() + addition + "\n", encoding="utf-8")


def patch_doc() -> None:
    text = DOC.read_text(encoding="utf-8")
    text += '''\n## Authenticated graph-chain continuity\n\nInherited authenticated transitions must form a consecutive suffix of the legacy transition\nlineage. For each hop, the exact historical `parent_graph_id`/SHA must match that record's exact\nbase snapshot, and the proposal `new_graph_id` must lead to the next authenticated record's exact\nbase graph. The final inherited hop is anchored to the exact current base bytes/SHA authenticated\nby the current v1.1 verifier. Each immediate successor must contain exactly the base structure plus\nthe authenticated result/tests/diagnostic-inference additions; unrelated grafted structure is\nrejected. This provides a forward-anchored graph-ID/SHA replay chain rather than accepting a\nself-consistent historical subgraph merely because it appears somewhere in the current graph.\n\nAuthenticated lineage records use an exact top-level key set. Unknown authority or credential\nclaims are rejected instead of being copied through opaque metadata. Exact current-base node\nartifact and edge-verifier SHA bindings are also required to be canonical lowercase SHA-256 text\nso every published bundle remains consumable by the same replay contract.\n'''
    DOC.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    patch_merge_gate()
    patch_core_test()
    patch_doc()
