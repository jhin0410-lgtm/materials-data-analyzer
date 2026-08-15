from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_epistemic_transition.py")
TEST = Path("tests/test_authenticated_epistemic_transition.py")
MERGE_GATE = Path("tests/test_authenticated_epistemic_transition_merge_gate.py")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''"""Atomic, self-contained producer for authenticated directional inference provenance.\n\nThe producer authenticates exact proposal/verifier bytes and exact inference-edge identity,\nbut deliberately publishes the directional edge as *diagnostic*. Scientific authority is\nleft to a later consumer that independently re-authenticates the published bundle.\n"""''',
        '''"""Atomic, self-contained producer for authenticated directional inference provenance.\n\nThe producer authenticates exact proposal/verifier bytes and exact inference-edge identity,\nbut deliberately publishes the directional edge as *diagnostic*. Scientific authority is\nleft to a later consumer that independently re-authenticates the published bundle.\n\nFilesystem trust boundary: atomic publication and staged integrity checks assume this process\nhas exclusive write ownership of its private staging tree from creation through publication.\nThe producer is not a sandbox against a hostile process sharing the same OS identity and write\naccess to that staging parent. No provenance or security claim should be read as resisting such\na same-identity attacker.\n"""''',
        label="module trust-boundary docstring",
    )
    text = replace_once(
        text,
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.3"',
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.4"',
        label="policy version",
    )
    old_identity = '''def _lineage_identity(record: Mapping[str, Any], field: str) -> str:\n    value = record.get(field)\n    if not isinstance(value, str) or not value.strip():\n        raise AuthenticatedEpistemicTransitionError(\n            f"lineage coherence field {field} must be non-empty text"\n        )\n    return value.strip()\n'''
    new_identity = old_identity + '''\n\ndef _lineage_sha256(record: Mapping[str, Any], field: str) -> str:\n    value = record.get(field)\n    if (\n        not isinstance(value, str)\n        or value != value.strip()\n        or len(value) != 64\n        or any(character not in "0123456789abcdef" for character in value)\n    ):\n        raise AuthenticatedEpistemicTransitionError(\n            f"lineage coherence field {field} must be canonical lowercase SHA-256 text"\n        )\n    return value\n'''
    text = replace_once(text, old_identity, new_identity, label="lineage SHA validator")

    old_pairs = '''        expected_pairs = (\n            (legacy_record.get("parent_graph_sha256"), base_artifact.get("sha256")),\n            (legacy_record.get("proposal_sha256"), proposal_artifact.get("sha256")),\n            (\n                legacy_record.get("verification_decision_sha256"),\n                verifier_artifact.get("sha256"),\n            ),\n            (legacy_record.get("result_node_id"), binding.get("result_node_id")),\n            (transition_id, str(binding.get("transition_id", "")).strip()),\n        )\n'''
    new_pairs = '''        expected_pairs = (\n            (\n                _lineage_sha256(legacy_record, "parent_graph_sha256"),\n                _lineage_sha256(base_artifact, "sha256"),\n            ),\n            (\n                _lineage_sha256(legacy_record, "proposal_sha256"),\n                _lineage_sha256(proposal_artifact, "sha256"),\n            ),\n            (\n                _lineage_sha256(legacy_record, "verification_decision_sha256"),\n                _lineage_sha256(verifier_artifact, "sha256"),\n            ),\n            (\n                _lineage_identity(legacy_record, "result_node_id"),\n                _lineage_identity(binding, "result_node_id"),\n            ),\n            (transition_id, _lineage_identity(binding, "transition_id")),\n        )\n'''
    text = replace_once(text, old_pairs, new_pairs, label="cross-lineage canonical identity")

    text = replace_once(
        text,
        '''        record_transition_id = _lineage_identity(record, "transition_id")\n        if str(binding.get("transition_id", "")).strip() != record_transition_id:\n            raise AuthenticatedEpistemicTransitionError(\n                f"authenticated_transition_lineage[{index}] transition identity is inconsistent"\n            )\n''',
        '''        record_transition_id = _lineage_identity(record, "transition_id")\n        if _lineage_identity(binding, "transition_id") != record_transition_id:\n            raise AuthenticatedEpistemicTransitionError(\n                f"authenticated_transition_lineage[{index}] transition identity is inconsistent"\n            )\n''',
        label="inherited binding transition identity",
    )

    text = replace_once(
        text,
        '''    """Produce an atomic self-contained bundle with authenticated diagnostic inference."""''',
        '''    """Produce an authenticated diagnostic bundle under exclusive staging ownership.\n\n    The filesystem integrity boundary assumes no hostile same-OS-identity process can write\n    into or replace this function's private staging tree while it is being assembled.\n    """''',
        label="public function trust-boundary docstring",
    )

    text = replace_once(
        text,
        '''                "staged_symlinks_accepted": False,\n                "empirical_derived_without_resolvable_input_snapshots_allowed": False,\n''',
        '''                "staged_symlinks_accepted": False,\n                "exclusive_staging_write_ownership_assumed": True,\n                "hostile_same_os_identity_staging_tamper_resistance_claimed": False,\n                "same_identity_concurrent_staging_tamper_outside_trust_boundary": True,\n                "empirical_derived_without_resolvable_input_snapshots_allowed": False,\n''',
        label="manifest filesystem trust boundary",
    )
    SOURCE.write_text(text, encoding="utf-8")


def patch_test() -> None:
    text = TEST.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    assert boundary["inherited_artifacts_snapshotted"] is True\n    assert boundary["authenticated_v11_verifier_consumed_by_legacy_critic"] is False\n''',
        '''    assert boundary["inherited_artifacts_snapshotted"] is True\n    assert boundary["exclusive_staging_write_ownership_assumed"] is True\n    assert boundary["hostile_same_os_identity_staging_tamper_resistance_claimed"] is False\n    assert boundary["same_identity_concurrent_staging_tamper_outside_trust_boundary"] is True\n    assert boundary["authenticated_v11_verifier_consumed_by_legacy_critic"] is False\n''',
        label="trust-boundary regression assertions",
    )
    TEST.write_text(text, encoding="utf-8")


def patch_merge_gate() -> None:
    text = MERGE_GATE.read_text(encoding="utf-8")
    anchor = '''def test_staged_symlink_is_rejected_even_when_target_bytes_match(tmp_path: Path) -> None:\n'''
    additions = '''def test_cross_lineage_binding_transition_id_must_remain_text() -> None:\n    legacy = _legacy_record(transition_id="1")\n    authenticated = _authenticated_record(transition_id="1")\n    binding = authenticated["authenticated_inference_binding"]\n    assert isinstance(binding, dict)\n    binding["transition_id"] = 1\n\n    with pytest.raises(\n        AuthenticatedEpistemicTransitionError,\n        match="transition_id must be non-empty text",\n    ):\n        _assert_cross_lineage_coherence([legacy], [authenticated])\n\n\ndef test_cross_lineage_hashes_must_use_canonical_sha256_text() -> None:\n    legacy = _legacy_record()\n    authenticated = _authenticated_record()\n    legacy["proposal_sha256"] = f" {'b' * 64} "\n    proposal_artifact = authenticated["proposal_artifact"]\n    assert isinstance(proposal_artifact, dict)\n    proposal_artifact["sha256"] = f" {'b' * 64} "\n\n    with pytest.raises(\n        AuthenticatedEpistemicTransitionError,\n        match="proposal_sha256 must be canonical lowercase SHA-256 text",\n    ):\n        _assert_cross_lineage_coherence([legacy], [authenticated])\n\n\n'''
    if additions.strip() in text:
        raise RuntimeError("merge-gate additions already present")
    text = replace_once(text, anchor, additions + anchor, label="lineage regression tests")
    MERGE_GATE.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    patch_test()
    patch_merge_gate()
