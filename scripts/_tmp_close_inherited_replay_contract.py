from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_epistemic_transition.py")
MERGE_GATE = Path("tests/test_authenticated_epistemic_transition_merge_gate.py")
PORTABILITY = Path("tests/test_authenticated_epistemic_transition_inherited_portability.py")
DOC = Path("docs/AUTHENTICATED_EPISTEMIC_TRANSITION.md")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_block(text: str, start: str, end: str, replacement: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[:start_index] + replacement.rstrip() + "\n\n\n" + text[end_index:]


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from .epistemic_graph import evaluate_epistemic_graph, validate_epistemic_graph\n",
        "from .epistemic_graph import (\n    EpistemicGraphError,\n    evaluate_epistemic_graph,\n    validate_epistemic_graph,\n)\n",
        label="graph error import",
    )
    text = replace_once(
        text,
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.6"',
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.7"',
        label="policy version",
    )

    anchor = '''def _proposal_result_artifact_identity(proposal_bytes: bytes) -> dict[str, str]:\n'''
    helpers = r'''def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthenticatedEpistemicTransitionError(
                f"duplicate JSON key is not allowed in inherited provenance: {key}"
            )
        result[key] = value
    return result


def _json_object_from_exact_bytes(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} must be valid UTF-8"
        ) from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_json_pairs)
    except json.JSONDecodeError as exc:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} must be valid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise AuthenticatedEpistemicTransitionError(f"{field} root must be an object")
    return value


def _artifact_identity_list(value: object, *, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise AuthenticatedEpistemicTransitionError(f"{field} must be a list")
    result: list[dict[str, str]] = []
    roles: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"{field}[{index}] must be an object"
            )
        role = _lineage_identity(raw, "role")
        if role in roles:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} artifact roles must be unique"
            )
        roles.add(role)
        result.append({"role": role, "sha256": _lineage_sha256(raw, "sha256")})
    return result


def _node_semantic_identity(value: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    if "artifact_bindings" in result:
        result["artifact_bindings"] = _artifact_identity_list(
            result["artifact_bindings"], field=f"{field}.artifact_bindings"
        )
    return result


def _edge_semantic_identity(value: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    verification = result.get("verification_artifact")
    if verification is not None:
        if not isinstance(verification, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"{field}.verification_artifact must be an object"
            )
        result["verification_artifact"] = {
            "role": _lineage_identity(verification, "role"),
            "sha256": _lineage_sha256(verification, "sha256"),
        }
    return result


def _unique_id_map(
    value: object,
    *,
    id_field: str,
    field: str,
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        raise AuthenticatedEpistemicTransitionError(f"{field} must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"{field}[{index}] must be an object"
            )
        identifier = _lineage_identity(raw, id_field)
        if identifier in result:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} must not contain duplicate {id_field} values"
            )
        result[identifier] = raw
    return result


def _materialize_and_validate_historical_base_graph(
    historical_base: Mapping[str, Any],
    *,
    enclosing_graph: Mapping[str, Any],
    program_state: Mapping[str, Any],
    artifact_root: Path,
    field: str,
) -> dict[str, Any]:
    if historical_base.get("schema_version") != enclosing_graph.get("schema_version"):
        raise AuthenticatedEpistemicTransitionError(
            f"{field} schema_version is incompatible with the enclosing graph"
        )
    if historical_base.get("research_scope") != enclosing_graph.get("research_scope"):
        raise AuthenticatedEpistemicTransitionError(
            f"{field} research_scope is incompatible with the enclosing graph"
        )
    materialized = copy.deepcopy(dict(historical_base))
    historical_nodes = _unique_id_map(
        materialized.get("nodes"), id_field="node_id", field=f"{field}.nodes"
    )
    enclosing_nodes = _unique_id_map(
        enclosing_graph.get("nodes"), id_field="node_id", field="enclosing_graph.nodes"
    )
    for node_id, historical_node in historical_nodes.items():
        current = enclosing_nodes.get(node_id)
        if current is None:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} node {node_id} is absent from the enclosing graph"
            )
        if _node_semantic_identity(
            historical_node, field=f"{field}.nodes[{node_id}]"
        ) != _node_semantic_identity(
            current, field=f"enclosing_graph.nodes[{node_id}]"
        ):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} node {node_id} differs from the enclosing graph history"
            )
        historical_bindings = historical_node.get("artifact_bindings")
        if isinstance(historical_bindings, list):
            current_bindings = current.get("artifact_bindings")
            if not isinstance(current_bindings, list):
                raise AuthenticatedEpistemicTransitionError(
                    f"enclosing graph node {node_id} lost historical artifact bindings"
                )
            current_by_role = {
                _lineage_identity(item, "role"): item
                for item in current_bindings
                if isinstance(item, Mapping)
            }
            materialized_node = next(
                item
                for item in materialized["nodes"]
                if isinstance(item, dict) and item.get("node_id") == node_id
            )
            for binding in materialized_node.get("artifact_bindings", []):
                if not isinstance(binding, dict):
                    continue
                role = _lineage_identity(binding, "role")
                current_binding = current_by_role.get(role)
                if not isinstance(current_binding, Mapping):
                    raise AuthenticatedEpistemicTransitionError(
                        f"enclosing graph node {node_id} lacks historical artifact role {role}"
                    )
                binding["path"] = _lineage_identity(current_binding, "path")

    historical_edges = _unique_id_map(
        materialized.get("edges"), id_field="edge_id", field=f"{field}.edges"
    )
    enclosing_edges = _unique_id_map(
        enclosing_graph.get("edges"), id_field="edge_id", field="enclosing_graph.edges"
    )
    for edge_id, historical_edge in historical_edges.items():
        current = enclosing_edges.get(edge_id)
        if current is None:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} edge {edge_id} is absent from the enclosing graph"
            )
        if _edge_semantic_identity(
            historical_edge, field=f"{field}.edges[{edge_id}]"
        ) != _edge_semantic_identity(
            current, field=f"enclosing_graph.edges[{edge_id}]"
        ):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} edge {edge_id} differs from the enclosing graph history"
            )
        historical_verifier = historical_edge.get("verification_artifact")
        current_verifier = current.get("verification_artifact")
        if isinstance(historical_verifier, Mapping):
            if not isinstance(current_verifier, Mapping):
                raise AuthenticatedEpistemicTransitionError(
                    f"enclosing graph edge {edge_id} lost its historical verifier artifact"
                )
            materialized_edge = next(
                item
                for item in materialized["edges"]
                if isinstance(item, dict) and item.get("edge_id") == edge_id
            )
            verifier = materialized_edge.get("verification_artifact")
            if isinstance(verifier, dict):
                verifier["path"] = _lineage_identity(current_verifier, "path")
    try:
        return validate_epistemic_graph(
            materialized,
            program_state=program_state,
            artifact_root=artifact_root,
        )
    except EpistemicGraphError as exc:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} is not a valid historical epistemic graph"
        ) from exc


def _proposal_with_materialized_result_paths(
    proposal: Mapping[str, Any],
    *,
    result_paths: Mapping[str, str],
) -> dict[str, Any]:
    result = copy.deepcopy(dict(proposal))
    result_node = result.get("result_node")
    if not isinstance(result_node, dict):
        raise AuthenticatedEpistemicTransitionError(
            "authenticated inherited proposal result_node must be an object"
        )
    bindings = result_node.get("artifact_bindings")
    if not isinstance(bindings, list):
        raise AuthenticatedEpistemicTransitionError(
            "authenticated inherited proposal result artifacts must be a list"
        )
    for binding in bindings:
        if not isinstance(binding, dict):
            raise AuthenticatedEpistemicTransitionError(
                "authenticated inherited proposal result artifact must be an object"
            )
        role = _lineage_identity(binding, "role")
        path = result_paths.get(role)
        if path is None:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated inherited proposal result role {role} lacks a materialized snapshot"
            )
        binding["path"] = path
    return result


def _assert_inherited_transition_matches_enclosing_graph(
    *,
    proposal: Mapping[str, Any],
    enclosing_graph: Mapping[str, Any],
    result_artifacts: list[dict[str, str]],
    field: str,
) -> None:
    expected_node, expected_tests, expected_inference = _proposal_result_and_edges(
        proposal,
        result_artifact_bindings=result_artifacts,
    )
    nodes = _unique_id_map(
        enclosing_graph.get("nodes"), id_field="node_id", field="enclosing_graph.nodes"
    )
    edges = _unique_id_map(
        enclosing_graph.get("edges"), id_field="edge_id", field="enclosing_graph.edges"
    )
    actual_node = nodes.get(str(expected_node["node_id"]))
    if actual_node is None or _node_semantic_identity(
        actual_node, field=f"{field}.enclosing_result_node"
    ) != _node_semantic_identity(expected_node, field=f"{field}.expected_result_node"):
        raise AuthenticatedEpistemicTransitionError(
            f"{field} result node does not match the enclosing graph"
        )
    for expected, label in (
        (expected_tests, "tests edge"),
        (expected_inference, "inference edge"),
    ):
        actual = edges.get(str(expected["edge_id"]))
        if actual is None or _edge_semantic_identity(
            actual, field=f"{field}.enclosing_{label}"
        ) != _edge_semantic_identity(expected, field=f"{field}.expected_{label}"):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} {label} does not match the enclosing graph"
            )


def _inherited_domain_verified_relation_count(base_graph: Mapping[str, Any]) -> int:
    edges = base_graph.get("edges")
    if not isinstance(edges, list):
        return 0
    return sum(
        1
        for edge in edges
        if isinstance(edge, Mapping)
        and edge.get("active") is True
        and edge.get("assessment_level") == "domain_verified"
        and edge.get("relation") in {"supports", "contradicts", "falsifies"}
    )


'''
    text = replace_once(text, anchor, helpers + anchor, label="historical replay helpers")

    replacement = r'''def _remap_authenticated_lineage_artifacts(
    metadata: dict[str, Any],
    *,
    enclosing_graph: Mapping[str, Any],
    program_state: Mapping[str, Any],
    artifact_root: Path,
    payloads: dict[str, bytes],
) -> None:
    raw_lineage = metadata.get("authenticated_transition_lineage", [])
    if not isinstance(raw_lineage, list):
        raise AuthenticatedEpistemicTransitionError(
            "base graph metadata.authenticated_transition_lineage must be a list"
        )
    remapped: list[dict[str, Any]] = []
    for index, raw_record in enumerate(raw_lineage):
        field = f"authenticated_transition_lineage[{index}]"
        if not isinstance(raw_record, Mapping):
            raise AuthenticatedEpistemicTransitionError(f"{field} must be an object")
        record = copy.deepcopy(dict(raw_record))
        if record.get("schema_version") != AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION:
            raise AuthenticatedEpistemicTransitionError(
                f"{field}.schema_version must be {AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION}"
            )
        stored_binding = record.get("authenticated_inference_binding")
        if not isinstance(stored_binding, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"{field}.authenticated_inference_binding must be an object"
            )
        record_transition_id = _lineage_identity(record, "transition_id")
        if _lineage_identity(stored_binding, "transition_id") != record_transition_id:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} transition identity is inconsistent"
            )
        if record.get("scientific_authority_applied") is not False:
            raise AuthenticatedEpistemicTransitionError(
                f"{field}.scientific_authority_applied must be false for producer lineage"
            )

        captured: dict[str, tuple[dict[str, Any], bytes]] = {}
        for name in (
            "base_graph_artifact",
            "proposal_artifact",
            "verification_decision_artifact",
        ):
            raw_binding = record.get(name)
            if not isinstance(raw_binding, Mapping):
                raise AuthenticatedEpistemicTransitionError(f"{field}.{name} must be an object")
            if (
                name == "verification_decision_artifact"
                and raw_binding.get("role") != AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE
            ):
                raise AuthenticatedEpistemicTransitionError(
                    f"{field}.{name}.role must be {AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE}"
                )
            suffix_source = _resolve_file(
                raw_binding.get("path"),
                artifact_root=artifact_root,
                field=f"{field}.{name}.path",
            )
            relative = _bundle_path(
                "provenance",
                "inherited",
                f"lineage-{index:03d}",
                f"{name}{_safe_suffix(suffix_source)}",
            )
            captured[name] = _captured_lineage_binding(
                raw_binding,
                artifact_root=artifact_root,
                bundle_path=relative,
                field=f"{field}.{name}",
                payloads=payloads,
            )

        base_binding, base_bytes = captured["base_graph_artifact"]
        proposal_binding, proposal_bytes = captured["proposal_artifact"]
        verifier_binding, verifier_bytes = captured["verification_decision_artifact"]
        try:
            recomputed_binding = authenticate_inference_binding(
                proposal_bytes=proposal_bytes,
                verification_decision_bytes=verifier_bytes,
                expected_base_graph_sha256=_lineage_sha256(base_binding, "sha256"),
            )
        except AuthenticatedInferenceBindingError as exc:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} exact inference binding could not be re-authenticated"
            ) from exc
        if dict(stored_binding) != recomputed_binding:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} stored inference binding does not match exact proposal/verifier bytes"
            )
        if recomputed_binding["transition_id"] != record_transition_id:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} recomputed transition identity is inconsistent"
            )
        if recomputed_binding["proposal_sha256"] != _lineage_sha256(
            proposal_binding, "sha256"
        ):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} proposal binding is inconsistent"
            )
        if recomputed_binding["verification_decision_sha256"] != _lineage_sha256(
            verifier_binding, "sha256"
        ):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} verifier binding is inconsistent"
            )
        if recomputed_binding["inference_scope"] == "empirical_derived":
            raise AuthenticatedEpistemicTransitionError(
                f"{field} does not accept inherited empirical_derived lineage without "
                "checksum-bound resolvable input evidence snapshots"
            )

        historical_base_raw = _json_object_from_exact_bytes(
            base_bytes, field=f"{field}.base_graph_artifact"
        )
        proposal_raw = _json_object_from_exact_bytes(
            proposal_bytes, field=f"{field}.proposal_artifact"
        )
        verifier_raw = _json_object_from_exact_bytes(
            verifier_bytes, field=f"{field}.verification_decision_artifact"
        )
        raw_inputs = proposal_raw.get("input_evidence_bindings")
        if isinstance(raw_inputs, list) and raw_inputs:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} does not accept inherited input_evidence_bindings until a "
                "checksum-bound resolvable evidence-origin contract exists"
            )

        expected_results = _proposal_result_artifact_identity(proposal_bytes)
        raw_results = record.get("result_artifact_snapshots")
        if not isinstance(raw_results, list) or not raw_results:
            raise AuthenticatedEpistemicTransitionError(
                f"{field}.result_artifact_snapshots must be a non-empty list"
            )
        result_records: list[dict[str, Any]] = []
        actual_results: dict[str, str] = {}
        result_validation_paths: dict[str, str] = {}
        for result_index, raw_binding in enumerate(raw_results):
            if not isinstance(raw_binding, Mapping):
                raise AuthenticatedEpistemicTransitionError(
                    f"{field}.result_artifact_snapshots[{result_index}] must be an object"
                )
            role = _lineage_identity(raw_binding, "role")
            if role in actual_results:
                raise AuthenticatedEpistemicTransitionError(
                    f"{field} result artifact roles must be unique"
                )
            expected_sha = _lineage_sha256(raw_binding, "sha256")
            suffix_source = _resolve_file(
                raw_binding.get("path"),
                artifact_root=artifact_root,
                field=f"{field}.result_artifact_snapshots[{result_index}].path",
            )
            relative = _bundle_path(
                "provenance",
                "inherited",
                f"lineage-{index:03d}",
                "result_artifacts",
                f"result-{result_index:03d}{_safe_suffix(suffix_source)}",
            )
            copied, _data = _captured_lineage_binding(
                raw_binding,
                artifact_root=artifact_root,
                bundle_path=relative,
                field=f"{field}.result_artifact_snapshots[{result_index}]",
                payloads=payloads,
            )
            actual_results[role] = expected_sha
            result_validation_paths[role] = str(suffix_source)
            result_records.append(copied)
        if actual_results != expected_results:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} result snapshots do not match the exact proposal result artifacts"
            )

        historical_base = _materialize_and_validate_historical_base_graph(
            historical_base_raw,
            enclosing_graph=enclosing_graph,
            program_state=program_state,
            artifact_root=artifact_root,
            field=f"{field}.base_graph_artifact",
        )
        proposal_validation_view = _proposal_with_materialized_result_paths(
            proposal_raw, result_paths=result_validation_paths
        )
        try:
            validated_proposal = validate_transition_proposal(
                proposal_validation_view,
                base_graph=historical_base,
                base_graph_sha256=_lineage_sha256(base_binding, "sha256"),
                program_state=program_state,
                artifact_root=artifact_root,
            )
            scope_validation = validate_verification_decision(
                _legacy_scope_decision(verifier_raw),
                proposal=validated_proposal,
                proposal_sha256=_lineage_sha256(proposal_binding, "sha256"),
                verification_sha256=_lineage_sha256(verifier_binding, "sha256"),
            )
        except EpistemicTransitionError as exc:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} does not satisfy the full historical transition/verifier contract"
            ) from exc
        if scope_validation["inference_scope"] != recomputed_binding["inference_scope"]:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} exact inference scope diverges from full verifier scope validation"
            )
        result_graph_bindings = [
            {
                "role": role,
                "path": result_validation_paths[role],
                "sha256": sha256,
            }
            for role, sha256 in actual_results.items()
        ]
        _assert_inherited_transition_matches_enclosing_graph(
            proposal=validated_proposal,
            enclosing_graph=enclosing_graph,
            result_artifacts=result_graph_bindings,
            field=field,
        )

        record["base_graph_artifact"] = base_binding
        record["proposal_artifact"] = proposal_binding
        record["verification_decision_artifact"] = verifier_binding
        record["result_artifact_snapshots"] = result_records
        record["authenticated_inference_binding"] = dict(recomputed_binding)
        remapped.append(record)
    metadata["authenticated_transition_lineage"] = remapped
'''
    text = replace_block(
        text,
        "def _remap_authenticated_lineage_artifacts(",
        "def _remap_base_graph_artifacts(",
        replacement,
    )

    text = replace_once(
        text,
        '''def _remap_base_graph_artifacts(\n    base_graph: Mapping[str, Any],\n    *,\n    artifact_root: Path,\n    payloads: dict[str, bytes],\n) -> tuple[dict[str, Any], list[dict[str, Any]]]:\n    graph = copy.deepcopy(dict(base_graph))\n    inherited_provenance: list[dict[str, Any]] = []\n\n    raw_nodes = graph.get("nodes")\n''',
        '''def _remap_base_graph_artifacts(\n    base_graph: Mapping[str, Any],\n    *,\n    program_state: Mapping[str, Any],\n    artifact_root: Path,\n    payloads: dict[str, bytes],\n) -> tuple[dict[str, Any], list[dict[str, Any]]]:\n    graph = copy.deepcopy(dict(base_graph))\n    inherited_provenance: list[dict[str, Any]] = []\n\n    metadata = graph.get("metadata")\n    if metadata is None:\n        metadata = {}\n        graph["metadata"] = metadata\n    if not isinstance(metadata, dict):\n        raise AuthenticatedEpistemicTransitionError("base graph metadata must be an object")\n    _remap_authenticated_lineage_artifacts(\n        metadata,\n        enclosing_graph=graph,\n        program_state=program_state,\n        artifact_root=artifact_root,\n        payloads=payloads,\n    )\n\n    raw_nodes = graph.get("nodes")\n''',
        label="remap base signature and early lineage validation",
    )
    old_metadata_tail = '''    metadata = graph.get("metadata")\n    if metadata is None:\n        metadata = {}\n        graph["metadata"] = metadata\n    if not isinstance(metadata, dict):\n        raise AuthenticatedEpistemicTransitionError("base graph metadata must be an object")\n    _remap_authenticated_lineage_artifacts(\n        metadata,\n        artifact_root=artifact_root,\n        payloads=payloads,\n    )\n    return graph, inherited_provenance\n'''
    text = replace_once(
        text,
        old_metadata_tail,
        "    return graph, inherited_provenance\n",
        label="remove late lineage validation",
    )
    text = replace_once(
        text,
        '''    if scope_validation["inference_scope"] == "empirical_derived":\n        raise AuthenticatedEpistemicTransitionError(\n            "authenticated self-contained transition does not yet accept empirical_derived "\n            "inference because program evidence bindings do not provide a first-class "\n            "checksum-bound resolvable artifact contract"\n        )\n\n    metadata = base_raw.get("metadata")\n''',
        '''    if scope_validation["inference_scope"] == "empirical_derived":\n        raise AuthenticatedEpistemicTransitionError(\n            "authenticated self-contained transition does not yet accept empirical_derived "\n            "inference because program evidence bindings do not provide a first-class "\n            "checksum-bound resolvable artifact contract"\n        )\n    if proposal["input_evidence_bindings"]:\n        raise AuthenticatedEpistemicTransitionError(\n            "authenticated self-contained transition does not yet accept input_evidence_bindings "\n            "until a checksum-bound resolvable evidence-origin contract exists"\n        )\n\n    metadata = base_raw.get("metadata")\n''',
        label="current input evidence fail closed",
    )
    text = replace_once(
        text,
        '''    payloads: dict[str, bytes] = {}\n    remapped_base, inherited_provenance = _remap_base_graph_artifacts(\n        base_raw,\n        artifact_root=artifacts,\n        payloads=payloads,\n    )\n''',
        '''    inherited_domain_verified_count = _inherited_domain_verified_relation_count(base_raw)\n    payloads: dict[str, bytes] = {}\n    remapped_base, inherited_provenance = _remap_base_graph_artifacts(\n        base_raw,\n        program_state=program_state,\n        artifact_root=artifacts,\n        payloads=payloads,\n    )\n''',
        label="production remap call and authority count",
    )
    text = replace_once(
        text,
        '''            "inference_assessment_level": "diagnostic",\n            "domain_verification_decision_authenticated": True,\n            "scientific_authority_applied": False,\n''',
        '''            "inference_assessment_level": "diagnostic",\n            "domain_verification_decision_authenticated": True,\n            "scientific_authority_applied": False,\n            "inherited_domain_verified_relation_count": inherited_domain_verified_count,\n''',
        label="manifest inherited authority count",
    )
    text = replace_once(
        text,
        '''                "opaque_graph_metadata_used_as_authority": False,\n                "legacy_v10_verifier_used_as_authenticated_authority": False,\n                "authenticated_v11_verifier_consumed_by_legacy_critic": False,\n''',
        '''                "opaque_graph_metadata_used_as_authority": False,\n                "inherited_domain_verified_authority_preserved": (\n                    inherited_domain_verified_count > 0\n                ),\n                "legacy_v10_verifier_promoted_by_authenticated_producer": False,\n                "inherited_domain_verified_relations_reauthenticated_as_v11": False,\n                "authenticated_v11_verifier_consumed_by_legacy_critic": False,\n''',
        label="accurate inherited legacy authority disclosure",
    )
    SOURCE.write_text(text, encoding="utf-8")


def write_portability() -> None:
    current = PORTABILITY.read_text(encoding="utf-8")
    header = current.split("def test_inherited_result_verifier_and_lineage_artifacts_are_bundle_portable", 1)[0]
    body = r'''def test_inherited_result_verifier_and_lineage_artifacts_are_bundle_portable(
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
            }
        ],
        "edges": [],
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
            old_parent_graph["nodes"][0],
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
'''
    PORTABILITY.write_text(header + body, encoding="utf-8")


def patch_merge_gate() -> None:
    text = MERGE_GATE.read_text(encoding="utf-8")
    old_start = text.index("def test_malformed_inherited_authenticated_lineage_fails_closed")
    old_end = text.index("def test_cross_lineage_binding_transition_id_must_remain_text", old_start)
    replacement = r'''def _valid_historical_lineage_fixture(
    tmp_path: Path,
    *,
    stored_edge_id: str = "old-edge",
    padded_proposal_sha: bool = False,
    empty_results: bool = False,
    result_snapshot_sha_override: str | None = None,
    invalid_schema: bool = False,
    inference_scope: str = "structural",
) -> tuple[dict[str, object], dict[str, object]]:
    result = tmp_path / "old-result.json"
    result_sha = _write_json(result, {"result": 1})
    historical_base_value = {
        "schema_version": "1.0",
        "graph_id": "graph-v0",
        "research_scope": "inherited replay regression",
        "nodes": [
            {
                "node_id": "hypothesis-1",
                "node_type": "hypothesis",
                "statement": "Historical target.",
                "metadata": {"claim_scope": "structural"},
            }
        ],
        "edges": [],
        "metadata": {},
    }
    base = tmp_path / "old-base.json"
    base_sha = _write_json(base, historical_base_value)
    source_action = {
        "action_id": "old-action",
        "action_class": "existing_data_reanalysis",
        "action_version": "1.0",
        "execution_mode": "typed_local_action",
    }
    limitations = ["Historical diagnostic producer lineage."]
    proposal_value: dict[str, object] = {
        "schema_version": "1.0",
        "transition_id": "old-auth",
        "base_graph_id": "graph-v0",
        "base_graph_sha256": base_sha,
        "new_graph_id": "graph-v1",
        "target_node_id": "hypothesis-1",
        "source_action": source_action,
        "result_node": {
            "node_id": "old-result",
            "node_type": "analysis",
            "statement": "Historical result.",
            "artifact_bindings": [
                {
                    "role": "primary_result",
                    "path": str(result),
                    "sha256": result_sha,
                }
            ],
            "metadata": {"result_origin": "authorized_local_analysis"},
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": "old-tests",
            "inference_edge_id": "old-edge",
            "relation": "supports",
            "rationale": "Historical diagnostic support.",
        },
        "limitations": limitations,
    }
    if invalid_schema:
        proposal_value.pop("source_action")
    proposal = tmp_path / "old-proposal.json"
    proposal_sha = _write_json(proposal, proposal_value)
    verifier = tmp_path / "old-verifier.json"
    verifier_value = {
        "schema_version": "1.1",
        "decision_id": "old-decision",
        "transition_id": "old-auth",
        "proposal_sha256": proposal_sha,
        "base_graph_sha256": base_sha,
        "inference_edge_id": "old-edge",
        "result_node_id": "old-result",
        "target_node_id": "hypothesis-1",
        "relation": "supports",
        "inference_scope": inference_scope,
        "verifier_id": "old-verifier",
        "rationale": "Exact inherited identity.",
        "limitations": [],
        "domain_verified": True,
    }
    verifier_sha = _write_json(verifier, verifier_value)
    from materials_data_analyzer.research_loop.authenticated_inference_binding import (
        authenticate_inference_binding,
    )

    binding = authenticate_inference_binding(
        proposal_bytes=proposal.read_bytes(),
        verification_decision_bytes=verifier.read_bytes(),
        expected_base_graph_sha256=base_sha,
    )
    binding["inference_edge_id"] = stored_edge_id
    result_snapshots: list[dict[str, object]] = []
    if not empty_results:
        result_snapshots.append(
            {
                "role": "primary_result",
                "path": str(result),
                "sha256": result_snapshot_sha_override or result_sha,
            }
        )
    lineage = {
        "schema_version": "1.0",
        "transition_id": "old-auth",
        "base_graph_artifact": {"path": str(base), "sha256": base_sha},
        "proposal_artifact": {
            "path": str(proposal),
            "sha256": f" {proposal_sha} " if padded_proposal_sha else proposal_sha,
        },
        "verification_decision_artifact": {
            "role": "authenticated_domain_verification_decision",
            "path": str(verifier),
            "sha256": verifier_sha,
        },
        "result_artifact_snapshots": result_snapshots,
        "authenticated_inference_binding": binding,
        "scientific_authority_applied": False,
    }
    result_metadata = {
        "result_origin": "authorized_local_analysis",
        "source_action": source_action,
        "input_evidence_bindings": [],
        "transition_id": "old-auth",
        "limitations": limitations,
    }
    enclosing = {
        "schema_version": "1.0",
        "graph_id": "graph-v1",
        "research_scope": "inherited replay regression",
        "nodes": [
            historical_base_value["nodes"][0],
            {
                "node_id": "old-result",
                "node_type": "analysis",
                "statement": "Historical result.",
                "execution_status": "completed",
                "artifact_bindings": [
                    {
                        "role": "primary_result",
                        "path": str(result),
                        "sha256": result_sha,
                    }
                ],
                "metadata": result_metadata,
            },
        ],
        "edges": [
            {
                "edge_id": "old-tests",
                "source_node_id": "old-result",
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
                "edge_id": "old-edge",
                "source_node_id": "old-result",
                "target_node_id": "hypothesis-1",
                "relation": "supports",
                "assessment_level": "diagnostic",
                "rationale": "Historical diagnostic support.",
                "active": True,
            },
        ],
        "metadata": {},
    }
    return lineage, enclosing


def _remap_one_lineage(
    tmp_path: Path,
    lineage: dict[str, object],
    enclosing: dict[str, object],
) -> None:
    _remap_authenticated_lineage_artifacts(
        {"authenticated_transition_lineage": [lineage]},
        enclosing_graph=enclosing,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
        payloads={},
    )


def test_malformed_inherited_authenticated_lineage_fails_closed(tmp_path: Path) -> None:
    _, enclosing = _valid_historical_lineage_fixture(tmp_path)
    malformed: dict[str, object] = {
        "schema_version": "1.0",
        "transition_id": "old-auth",
        "proposal_artifact": {},
        "verification_decision_artifact": {},
        "result_artifact_snapshots": [],
        "authenticated_inference_binding": {
            "transition_id": "old-auth",
            "result_node_id": "result-old",
        },
        "scientific_authority_applied": False,
    }
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="base_graph_artifact must be an object",
    ):
        _remap_one_lineage(tmp_path, malformed, enclosing)


def test_inherited_authenticated_lineage_reauthenticates_exact_binding(tmp_path: Path) -> None:
    lineage, enclosing = _valid_historical_lineage_fixture(
        tmp_path, stored_edge_id="forged-edge"
    )
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="stored inference binding does not match exact proposal/verifier bytes",
    ):
        _remap_one_lineage(tmp_path, lineage, enclosing)


def test_orphan_authenticated_lineage_rejects_noncanonical_artifact_sha(tmp_path: Path) -> None:
    lineage, enclosing = _valid_historical_lineage_fixture(
        tmp_path, padded_proposal_sha=True
    )
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="sha256 must be canonical lowercase SHA-256 text",
    ):
        _remap_one_lineage(tmp_path, lineage, enclosing)


def test_inherited_authenticated_lineage_requires_result_snapshots(tmp_path: Path) -> None:
    lineage, enclosing = _valid_historical_lineage_fixture(tmp_path, empty_results=True)
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="result_artifact_snapshots must be a non-empty list",
    ):
        _remap_one_lineage(tmp_path, lineage, enclosing)


def test_inherited_result_snapshots_must_match_exact_proposal(tmp_path: Path) -> None:
    other = tmp_path / "other-result.json"
    other_sha = _write_json(other, {"result": 2})
    lineage, enclosing = _valid_historical_lineage_fixture(
        tmp_path, result_snapshot_sha_override=other_sha
    )
    snapshots = lineage["result_artifact_snapshots"]
    assert isinstance(snapshots, list)
    snapshot = snapshots[0]
    assert isinstance(snapshot, dict)
    snapshot["path"] = str(other)
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="result snapshots do not match the exact proposal result artifacts",
    ):
        _remap_one_lineage(tmp_path, lineage, enclosing)


def test_inherited_transition_must_satisfy_full_proposal_schema(tmp_path: Path) -> None:
    lineage, enclosing = _valid_historical_lineage_fixture(tmp_path, invalid_schema=True)
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="full historical transition/verifier contract",
    ):
        _remap_one_lineage(tmp_path, lineage, enclosing)


def test_inherited_transition_must_match_enclosing_graph(tmp_path: Path) -> None:
    lineage, enclosing = _valid_historical_lineage_fixture(tmp_path)
    nodes = enclosing["nodes"]
    assert isinstance(nodes, list)
    result = next(item for item in nodes if isinstance(item, dict) and item.get("node_id") == "old-result")
    result["statement"] = "Substituted unrelated result."
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="result node does not match the enclosing graph",
    ):
        _remap_one_lineage(tmp_path, lineage, enclosing)


def test_inherited_empirical_derived_lineage_fails_closed(tmp_path: Path) -> None:
    lineage, enclosing = _valid_historical_lineage_fixture(
        tmp_path, inference_scope="empirical_derived"
    )
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="does not accept inherited empirical_derived lineage",
    ):
        _remap_one_lineage(tmp_path, lineage, enclosing)


'''
    MERGE_GATE.write_text(
        text[:old_start] + replacement + text[old_end:], encoding="utf-8"
    )


def patch_doc() -> None:
    text = DOC.read_text(encoding="utf-8")
    text += '''\n## Historical replay validation\n\nInherited authenticated lineage is accepted only when its exact historical base graph can be\nmaterialized against the enclosing graph's still-operative artifact bindings and passes the graph\nvalidator, its exact proposal passes the full transition proposal contract using the snapshotted\nresult artifacts, and its v1.1 decision passes both exact-edge authentication and the established\nscope validator. The historical result node, tests edge, and diagnostic inference edge must also\nbe present with matching semantics in the enclosing graph. Copying a self-consistent lineage\nrecord into an unrelated graph is therefore not sufficient.\n\nAny inherited or current transition carrying unresolved `input_evidence_bindings` remains\nfail-closed until the separate evidence-origin contract provides checksum-bound resolvable input\nsnapshots. Existing inherited `domain_verified` relations from the legacy graph contract may still\nretain their prior evaluator authority; the authenticated producer reports that retention explicitly\nand does not describe those relations as re-authenticated v1.1 authority.\n'''
    DOC.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    write_portability()
    patch_merge_gate()
    patch_doc()
