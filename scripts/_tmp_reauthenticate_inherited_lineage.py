from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_epistemic_transition.py")
PORTABILITY = Path("tests/test_authenticated_epistemic_transition_inherited_portability.py")
MERGE_GATE = Path("tests/test_authenticated_epistemic_transition_merge_gate.py")


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
    text = replace_once(text, "import hashlib\n", "import hashlib\nimport json\n", label="json import")
    text = replace_once(
        text,
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.4"',
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.5"',
        label="policy version",
    )

    replacement = r'''def _captured_lineage_binding(
    raw: Mapping[str, Any],
    *,
    artifact_root: Path,
    bundle_path: str,
    field: str,
    payloads: dict[str, bytes],
) -> tuple[dict[str, Any], bytes]:
    expected_sha = _lineage_sha256(raw, "sha256")
    source, data, actual_sha = _read_bound_file(
        path_value=raw.get("path"),
        expected_sha256=expected_sha,
        artifact_root=artifact_root,
        field=field,
    )
    _add_payload(payloads, bundle_path, data)
    copied = dict(raw)
    copied["path"] = bundle_path
    copied["source_path"] = (
        raw.get("source_path")
        if isinstance(raw.get("source_path"), str) and raw.get("source_path")
        else str(source)
    )
    copied["source_path_authoritative"] = False
    copied["sha256"] = actual_sha
    copied["size_bytes"] = len(data)
    return copied, data


def _proposal_result_artifact_identity(proposal_bytes: bytes) -> dict[str, str]:
    # Exact-byte JSON validity and duplicate-key rejection already succeeded in
    # authenticate_inference_binding before this helper is called.
    try:
        proposal = json.loads(proposal_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:  # defensive only
        raise AuthenticatedEpistemicTransitionError(
            "authenticated inherited proposal could not be reparsed"
        ) from exc
    if not isinstance(proposal, Mapping):
        raise AuthenticatedEpistemicTransitionError(
            "authenticated inherited proposal root must be an object"
        )
    result_node = proposal.get("result_node")
    if not isinstance(result_node, Mapping):
        raise AuthenticatedEpistemicTransitionError(
            "authenticated inherited proposal result_node must be an object"
        )
    bindings = result_node.get("artifact_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise AuthenticatedEpistemicTransitionError(
            "authenticated inherited proposal result artifacts must be non-empty"
        )
    identity: dict[str, str] = {}
    for index, raw in enumerate(bindings):
        if not isinstance(raw, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                "authenticated inherited proposal result artifact must be an object"
            )
        role = _lineage_identity(raw, "role")
        if role in identity:
            raise AuthenticatedEpistemicTransitionError(
                "authenticated inherited proposal result artifact roles must be unique"
            )
        identity[role] = _lineage_sha256(raw, "sha256")
    return identity


def _remap_authenticated_lineage_artifacts(
    metadata: dict[str, Any],
    *,
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
        if not isinstance(raw_record, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] must be an object"
            )
        record = copy.deepcopy(dict(raw_record))
        if record.get("schema_version") != AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].schema_version must be "
                f"{AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION}"
            )
        stored_binding = record.get("authenticated_inference_binding")
        if not isinstance(stored_binding, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].authenticated_inference_binding "
                "must be an object"
            )
        record_transition_id = _lineage_identity(record, "transition_id")
        if _lineage_identity(stored_binding, "transition_id") != record_transition_id:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] transition identity is inconsistent"
            )
        if record.get("scientific_authority_applied") is not False:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].scientific_authority_applied "
                "must be false for producer lineage"
            )

        captured: dict[str, tuple[dict[str, Any], bytes]] = {}
        for name in (
            "base_graph_artifact",
            "proposal_artifact",
            "verification_decision_artifact",
        ):
            raw_binding = record.get(name)
            if not isinstance(raw_binding, Mapping):
                raise AuthenticatedEpistemicTransitionError(
                    f"authenticated_transition_lineage[{index}].{name} must be an object"
                )
            if (
                name == "verification_decision_artifact"
                and raw_binding.get("role") != AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE
            ):
                raise AuthenticatedEpistemicTransitionError(
                    f"authenticated_transition_lineage[{index}].{name}.role must be "
                    f"{AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE}"
                )
            suffix_source = _resolve_file(
                raw_binding.get("path"),
                artifact_root=artifact_root,
                field=f"authenticated_transition_lineage[{index}].{name}.path",
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
                field=f"authenticated_transition_lineage[{index}].{name}",
                payloads=payloads,
            )

        base_binding, _base_bytes = captured["base_graph_artifact"]
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
                f"authenticated_transition_lineage[{index}] exact inference binding "
                "could not be re-authenticated"
            ) from exc
        if dict(stored_binding) != recomputed_binding:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] stored inference binding "
                "does not match exact proposal/verifier bytes"
            )
        if recomputed_binding["transition_id"] != record_transition_id:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] recomputed transition identity "
                "is inconsistent"
            )
        if recomputed_binding["proposal_sha256"] != _lineage_sha256(
            proposal_binding, "sha256"
        ):
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] proposal binding is inconsistent"
            )
        if recomputed_binding["verification_decision_sha256"] != _lineage_sha256(
            verifier_binding, "sha256"
        ):
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] verifier binding is inconsistent"
            )

        expected_results = _proposal_result_artifact_identity(proposal_bytes)
        raw_results = record.get("result_artifact_snapshots")
        if not isinstance(raw_results, list) or not raw_results:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].result_artifact_snapshots "
                "must be a non-empty list"
            )
        result_records: list[dict[str, Any]] = []
        actual_results: dict[str, str] = {}
        for result_index, raw_binding in enumerate(raw_results):
            if not isinstance(raw_binding, Mapping):
                raise AuthenticatedEpistemicTransitionError(
                    "authenticated lineage result artifact snapshot must be an object"
                )
            role = _lineage_identity(raw_binding, "role")
            if role in actual_results:
                raise AuthenticatedEpistemicTransitionError(
                    "authenticated lineage result artifact roles must be unique"
                )
            expected_sha = _lineage_sha256(raw_binding, "sha256")
            suffix_source = _resolve_file(
                raw_binding.get("path"),
                artifact_root=artifact_root,
                field=(
                    f"authenticated_transition_lineage[{index}]"
                    f".result_artifact_snapshots[{result_index}].path"
                ),
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
                field=(
                    f"authenticated_transition_lineage[{index}]"
                    f".result_artifact_snapshots[{result_index}]"
                ),
                payloads=payloads,
            )
            actual_results[role] = expected_sha
            result_records.append(copied)
        if actual_results != expected_results:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] result snapshots do not match "
                "the exact proposal result artifacts"
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
    SOURCE.write_text(text, encoding="utf-8")


def patch_portability() -> None:
    text = PORTABILITY.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (\n    apply_authenticated_epistemic_transition_files,\n)\n",
        "from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (\n    apply_authenticated_epistemic_transition_files,\n)\nfrom materials_data_analyzer.research_loop.authenticated_inference_binding import (\n    authenticate_inference_binding,\n)\n",
        label="portability authenticator import",
    )
    old_setup = '''    old_parent = tmp_path / "old-parent.json"\n    old_parent_sha = _write_json(old_parent, {"old": "parent"})\n    old_proposal = tmp_path / "old-proposal.json"\n    old_proposal_sha = _write_json(old_proposal, {"old": "proposal"})\n    old_auth_verifier = tmp_path / "old-auth-verifier.json"\n    old_auth_verifier_sha = _write_json(old_auth_verifier, {"old": "auth-verifier"})\n'''
    new_setup = '''    old_parent = tmp_path / "old-parent.json"\n    old_parent_sha = _write_json(old_parent, {"old": "parent"})\n    old_proposal = tmp_path / "old-proposal.json"\n    old_proposal_value = {\n        "schema_version": "1.0",\n        "transition_id": "old-auth",\n        "base_graph_id": "graph-v0",\n        "base_graph_sha256": old_parent_sha,\n        "new_graph_id": "graph-v1",\n        "target_node_id": "hypothesis-1",\n        "source_action": {\n            "action_id": "old-action",\n            "action_class": "existing_data_reanalysis",\n            "action_version": "1.0",\n            "execution_mode": "typed_local_action",\n        },\n        "result_node": {\n            "node_id": "old-result-node",\n            "node_type": "analysis",\n            "statement": "Previously completed bounded analysis.",\n            "artifact_bindings": [\n                {\n                    "role": "primary_result",\n                    "path": str(old_result),\n                    "sha256": old_result_sha,\n                }\n            ],\n            "metadata": {"result_origin": "authorized_local_analysis"},\n        },\n        "input_evidence_bindings": [],\n        "proposed_inference": {\n            "tests_edge_id": "old-tests",\n            "inference_edge_id": "old-support",\n            "relation": "supports",\n            "rationale": "Previously authenticated structural support identity.",\n        },\n        "limitations": ["Historical producer lineage remains diagnostic-only."],\n    }\n    old_proposal_sha = _write_json(old_proposal, old_proposal_value)\n    old_auth_verifier = tmp_path / "old-auth-verifier.json"\n    old_auth_verifier_value = {\n        "schema_version": "1.1",\n        "decision_id": "old-decision",\n        "transition_id": "old-auth",\n        "proposal_sha256": old_proposal_sha,\n        "base_graph_sha256": old_parent_sha,\n        "inference_edge_id": "old-support",\n        "result_node_id": "old-result-node",\n        "target_node_id": "hypothesis-1",\n        "relation": "supports",\n        "inference_scope": "structural",\n        "verifier_id": "old-verifier-v1.1",\n        "rationale": "Exact historical edge identity authenticated.",\n        "limitations": [],\n        "domain_verified": True,\n    }\n    old_auth_verifier_sha = _write_json(old_auth_verifier, old_auth_verifier_value)\n    old_authenticated_binding = authenticate_inference_binding(\n        proposal_bytes=old_proposal.read_bytes(),\n        verification_decision_bytes=old_auth_verifier.read_bytes(),\n        expected_base_graph_sha256=old_parent_sha,\n    )\n'''
    text = replace_once(text, old_setup, new_setup, label="valid inherited lineage fixture")
    old_binding = '''                    "authenticated_inference_binding": {\n                        "schema_version": "1.0",\n                        "transition_id": "old-auth",\n                        "inference_edge_id": "old-support",\n                        "result_node_id": "old-result-node",\n                    },\n'''
    text = replace_once(
        text,
        old_binding,
        '                    "authenticated_inference_binding": old_authenticated_binding,\n',
        label="portability exact binding fixture",
    )
    PORTABILITY.write_text(text, encoding="utf-8")


def patch_merge_gate() -> None:
    text = MERGE_GATE.read_text(encoding="utf-8")
    anchor = '''def test_cross_lineage_binding_transition_id_must_remain_text() -> None:\n'''
    additions = r'''def _write_authenticated_lineage_fixture(
    tmp_path: Path,
    *,
    stored_edge_id: str = "old-edge",
    padded_proposal_sha: bool = False,
    empty_results: bool = False,
    result_snapshot_sha_override: str | None = None,
) -> dict[str, object]:
    result = tmp_path / "old-result.json"
    result_sha = _write_json(result, {"result": 1})
    base = tmp_path / "old-base.json"
    base_sha = _write_json(base, {"base": 1})
    proposal = tmp_path / "old-proposal.json"
    proposal_value = {
        "schema_version": "1.0",
        "transition_id": "old-auth",
        "base_graph_id": "graph-v0",
        "base_graph_sha256": base_sha,
        "new_graph_id": "graph-v1",
        "target_node_id": "hypothesis-1",
        "result_node": {
            "node_id": "old-result",
            "artifact_bindings": [
                {
                    "role": "primary_result",
                    "path": str(result),
                    "sha256": result_sha,
                }
            ],
        },
        "proposed_inference": {
            "inference_edge_id": "old-edge",
            "relation": "supports",
        },
    }
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
        "inference_scope": "structural",
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
    return {
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


def test_inherited_authenticated_lineage_reauthenticates_exact_binding(
    tmp_path: Path,
) -> None:
    metadata = {
        "authenticated_transition_lineage": [
            _write_authenticated_lineage_fixture(tmp_path, stored_edge_id="forged-edge")
        ]
    }
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="stored inference binding does not match exact proposal/verifier bytes",
    ):
        _remap_authenticated_lineage_artifacts(
            metadata,
            artifact_root=tmp_path,
            payloads={},
        )


def test_orphan_authenticated_lineage_rejects_noncanonical_artifact_sha(
    tmp_path: Path,
) -> None:
    metadata = {
        "authenticated_transition_lineage": [
            _write_authenticated_lineage_fixture(tmp_path, padded_proposal_sha=True)
        ]
    }
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="sha256 must be canonical lowercase SHA-256 text",
    ):
        _remap_authenticated_lineage_artifacts(
            metadata,
            artifact_root=tmp_path,
            payloads={},
        )


def test_inherited_authenticated_lineage_requires_result_snapshots(
    tmp_path: Path,
) -> None:
    metadata = {
        "authenticated_transition_lineage": [
            _write_authenticated_lineage_fixture(tmp_path, empty_results=True)
        ]
    }
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="result_artifact_snapshots must be a non-empty list",
    ):
        _remap_authenticated_lineage_artifacts(
            metadata,
            artifact_root=tmp_path,
            payloads={},
        )


def test_inherited_result_snapshots_must_match_exact_proposal(
    tmp_path: Path,
) -> None:
    other = tmp_path / "other-result.json"
    other_sha = _write_json(other, {"result": 2})
    lineage = _write_authenticated_lineage_fixture(
        tmp_path,
        result_snapshot_sha_override=other_sha,
    )
    snapshots = lineage["result_artifact_snapshots"]
    assert isinstance(snapshots, list)
    snapshot = snapshots[0]
    assert isinstance(snapshot, dict)
    snapshot["path"] = str(other)
    metadata = {"authenticated_transition_lineage": [lineage]}
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="result snapshots do not match the exact proposal result artifacts",
    ):
        _remap_authenticated_lineage_artifacts(
            metadata,
            artifact_root=tmp_path,
            payloads={},
        )


'''
    if additions.strip() in text:
        raise RuntimeError("inherited lineage regression additions already present")
    text = replace_once(text, anchor, additions + anchor, label="inherited lineage regressions")
    MERGE_GATE.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    patch_portability()
    patch_merge_gate()
