from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_epistemic_transition.py")
TEST = Path("tests/test_authenticated_epistemic_transition.py")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.7"',
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.8"',
        label="policy version",
    )
    text = replace_once(
        text,
        '''    proposal = validate_transition_proposal(\n        proposal_raw,\n        base_graph=base_validated,\n        base_graph_sha256=base_sha,\n        program_state=program_state,\n        artifact_root=artifacts,\n    )\n    if authenticated_binding["transition_id"] != proposal["transition_id"]:\n''',
        '''    proposal = validate_transition_proposal(\n        proposal_raw,\n        base_graph=base_validated,\n        base_graph_sha256=base_sha,\n        program_state=program_state,\n        artifact_root=artifacts,\n    )\n    exact_current_result_identity = _proposal_result_artifact_identity(proposal_bytes)\n    if authenticated_binding["transition_id"] != proposal["transition_id"]:\n''',
        label="exact current proposal result identity",
    )
    text = replace_once(
        text,
        '''    result_bindings, result_provenance = _prepare_current_result_snapshots(\n        proposal,\n        payloads=payloads,\n    )\n    result_node, tests_edge, inference_edge = _proposal_result_and_edges(\n''',
        '''    result_bindings, result_provenance = _prepare_current_result_snapshots(\n        proposal,\n        payloads=payloads,\n    )\n    published_current_result_identity = {\n        _lineage_identity(binding, "role"): _lineage_sha256(binding, "sha256")\n        for binding in result_bindings\n    }\n    if published_current_result_identity != exact_current_result_identity:\n        raise AuthenticatedEpistemicTransitionError(\n            "current result snapshots do not match the exact proposal result artifact identity"\n        )\n    result_node, tests_edge, inference_edge = _proposal_result_and_edges(\n''',
        label="published current result identity comparison",
    )
    SOURCE.write_text(text, encoding="utf-8")


def patch_test() -> None:
    text = TEST.read_text(encoding="utf-8")
    addition = r'''

def test_current_proposal_result_sha_must_be_canonical_for_replay(tmp_path: Path) -> None:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"rank_before": 3, "rank_after": 4})
    base_file = tmp_path / "base_graph.json"
    base_sha = _write_json(base_file, _base_graph())
    proposal = _proposal(base_sha=base_sha, result_sha=f" {result_sha} ")
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(proposal_file, proposal)
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
    if "def test_current_proposal_result_sha_must_be_canonical_for_replay" in text:
        raise RuntimeError("current-result canonical regression already exists")
    TEST.write_text(text.rstrip() + addition + "\n", encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    patch_test()
