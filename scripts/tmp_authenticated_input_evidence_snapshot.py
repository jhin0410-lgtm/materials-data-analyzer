from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_epistemic_transition.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''from .epistemic_graph import (\n''',
        '''from .input_evidence_origin_snapshot import (\n    INPUT_EVIDENCE_ORIGIN_SNAPSHOT_MANIFEST_PATH,\n    InputEvidenceOriginSnapshotError,\n    prepare_input_evidence_origin_snapshots,\n)\nfrom .epistemic_graph import (\n''',
        "snapshot-import",
    )
    text = replace_once(
        text,
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.9"',
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.10"',
        "policy-version",
    )
    text = replace_once(
        text,
        '''    artifact_root: str | Path,\n    output_dir: str | Path,\n) -> dict[str, Any]:\n''',
        '''    artifact_root: str | Path,\n    output_dir: str | Path,\n    input_evidence_origin_request_path: str | Path | None = None,\n) -> dict[str, Any]:\n''',
        "signature",
    )
    old = '''    if scope_validation["inference_scope"] == "empirical_derived":\n        raise AuthenticatedEpistemicTransitionError(\n            "authenticated self-contained transition does not yet accept empirical_derived "\n            "inference because program evidence bindings do not provide a first-class "\n            "checksum-bound resolvable artifact contract"\n        )\n    if proposal["input_evidence_bindings"]:\n        raise AuthenticatedEpistemicTransitionError(\n            "authenticated self-contained transition does not yet accept input_evidence_bindings "\n            "until a checksum-bound resolvable evidence-origin contract exists"\n        )\n\n    metadata = base_raw.get("metadata")\n'''
    new = '''    input_evidence_snapshot: dict[str, Any] | None = None\n    has_input_evidence = bool(proposal["input_evidence_bindings"])\n    if has_input_evidence and input_evidence_origin_request_path is None:\n        raise AuthenticatedEpistemicTransitionError(\n            "authenticated self-contained transition requires input_evidence_origin_request_path "\n            "when proposal input_evidence_bindings are non-empty"\n        )\n    if not has_input_evidence and input_evidence_origin_request_path is not None:\n        raise AuthenticatedEpistemicTransitionError(\n            "input_evidence_origin_request_path is not allowed when proposal input_evidence_bindings are empty"\n        )\n    if has_input_evidence:\n        try:\n            input_evidence_snapshot = prepare_input_evidence_origin_snapshots(\n                request_path=input_evidence_origin_request_path,\n                proposal_input_evidence_bindings=proposal["input_evidence_bindings"],\n                program_state=program_state,\n                artifact_root=artifacts,\n                transition_id=str(proposal["transition_id"]),\n                proposal_sha256=proposal_sha,\n            )\n        except InputEvidenceOriginSnapshotError as exc:\n            raise AuthenticatedEpistemicTransitionError(\n                "input evidence origin snapshot authentication failed"\n            ) from exc\n    if scope_validation["inference_scope"] == "empirical_derived":\n        if input_evidence_snapshot is None:\n            raise AuthenticatedEpistemicTransitionError(\n                "empirical_derived authenticated transition requires self-contained input evidence origin snapshots"\n            )\n        if input_evidence_snapshot["all_inputs_empirical_classified"] is not True:\n            raise AuthenticatedEpistemicTransitionError(\n                "empirical_derived authenticated transition requires every input evidence origin classification to be empirical"\n            )\n\n    metadata = base_raw.get("metadata")\n'''
    text = replace_once(text, old, new, "input-evidence-policy")

    text = replace_once(
        text,
        '''    payloads: dict[str, bytes] = {}\n    remapped_base, inherited_provenance = _remap_base_graph_artifacts(\n''',
        '''    payloads: dict[str, bytes] = {}\n    if input_evidence_snapshot is not None:\n        snapshot_payloads = input_evidence_snapshot.get("payloads")\n        if not isinstance(snapshot_payloads, Mapping):\n            raise AuthenticatedEpistemicTransitionError(\n                "input evidence origin snapshot payloads are malformed"\n            )\n        for snapshot_path, snapshot_bytes in snapshot_payloads.items():\n            if not isinstance(snapshot_path, str) or not isinstance(snapshot_bytes, bytes):\n                raise AuthenticatedEpistemicTransitionError(\n                    "input evidence origin snapshot payload entries are malformed"\n                )\n            _add_payload(payloads, snapshot_path, snapshot_bytes)\n    remapped_base, inherited_provenance = _remap_base_graph_artifacts(\n''',
        "snapshot-payloads",
    )

    text = replace_once(
        text,
        '''        manifest = {\n            "schema_version": TRANSITION_SCHEMA_VERSION,\n''',
        '''        manifest = {\n            "schema_version": TRANSITION_SCHEMA_VERSION,\n''',
        "manifest-anchor",
    )
    anchor = '''            "verification": {\n                **scope_validation,\n                "schema_version": DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION,\n                "inference_edge_id": edge_id,\n                "verification_sha256": verification_sha,\n            },\n            "autonomy_boundary": {\n'''
    replacement = '''            "verification": {\n                **scope_validation,\n                "schema_version": DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION,\n                "inference_edge_id": edge_id,\n                "verification_sha256": verification_sha,\n            },\n            "autonomy_boundary": {\n'''
    text = replace_once(text, anchor, replacement, "manifest-verification")

    insertion_anchor = '''        manifest_bytes = _canonical_json_bytes(manifest)\n'''
    insertion = '''        if input_evidence_snapshot is not None:\n            snapshot_manifest_bytes = input_evidence_snapshot.get("manifest_bytes")\n            snapshot_manifest_sha = input_evidence_snapshot.get("manifest_sha256")\n            if not isinstance(snapshot_manifest_bytes, bytes) or not isinstance(\n                snapshot_manifest_sha, str\n            ):\n                raise AuthenticatedEpistemicTransitionError(\n                    "input evidence origin snapshot manifest binding is malformed"\n                )\n            if hashlib.sha256(snapshot_manifest_bytes).hexdigest() != snapshot_manifest_sha:\n                raise AuthenticatedEpistemicTransitionError(\n                    "input evidence origin snapshot manifest SHA diverged before publication"\n                )\n            manifest["input_evidence_origin_snapshot_binding"] = {\n                "path": INPUT_EVIDENCE_ORIGIN_SNAPSHOT_MANIFEST_PATH,\n                "sha256": snapshot_manifest_sha,\n                "size_bytes": len(snapshot_manifest_bytes),\n                "scientific_authority_applied": False,\n            }\n        manifest_bytes = _canonical_json_bytes(manifest)\n'''
    text = replace_once(text, insertion_anchor, insertion, "manifest-sidecar-binding")
    SOURCE.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
