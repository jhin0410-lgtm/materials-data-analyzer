from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    AuthenticatedEpistemicTransitionError,
    _assert_cross_lineage_coherence,
    _atomic_publish_directory_no_replace,
    _read_staged_regular_file,
    _remap_authenticated_lineage_artifacts,
    apply_authenticated_epistemic_transition_files,
)


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _legacy_record(*, transition_id: str = "transition-old") -> dict[str, object]:
    return {
        "transition_id": transition_id,
        "parent_graph_id": "graph-parent",
        "parent_graph_sha256": "a" * 64,
        "proposal_sha256": "b" * 64,
        "verification_decision_sha256": "c" * 64,
        "result_node_id": "result-old",
    }


def _authenticated_record(
    *, transition_id: str = "transition-old", proposal_sha: str | None = None
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "transition_id": transition_id,
        "base_graph_artifact": {"sha256": "a" * 64},
        "proposal_artifact": {"sha256": proposal_sha or "b" * 64},
        "verification_decision_artifact": {"sha256": "c" * 64},
        "result_artifact_snapshots": [],
        "authenticated_inference_binding": {
            "transition_id": transition_id.strip(),
            "result_node_id": "result-old",
        },
        "scientific_authority_applied": False,
    }


def test_cross_lineage_matching_identity_must_be_coherent() -> None:
    _assert_cross_lineage_coherence(
        [_legacy_record()],
        [_authenticated_record()],
    )

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="denotes incompatible histories",
    ):
        _assert_cross_lineage_coherence(
            [_legacy_record()],
            [_authenticated_record(proposal_sha="d" * 64)],
        )


def test_malformed_inherited_authenticated_lineage_fails_closed(tmp_path: Path) -> None:
    metadata: dict[str, object] = {
        "authenticated_transition_lineage": [
            {
                "schema_version": "1.0",
                "transition_id": "old-auth",
                # Missing mandatory base_graph_artifact must never survive as
                # inherited authenticated provenance.
                "proposal_artifact": {},
                "verification_decision_artifact": {},
                "result_artifact_snapshots": [],
                "authenticated_inference_binding": {
                    "transition_id": "old-auth",
                    "result_node_id": "result-old",
                },
                "scientific_authority_applied": False,
            }
        ]
    }

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="base_graph_artifact must be an object",
    ):
        _remap_authenticated_lineage_artifacts(
            metadata,
            artifact_root=tmp_path,
            payloads={},
        )


def _write_authenticated_lineage_fixture(
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


def test_cross_lineage_binding_transition_id_must_remain_text() -> None:
    legacy = _legacy_record(transition_id="1")
    authenticated = _authenticated_record(transition_id="1")
    binding = authenticated["authenticated_inference_binding"]
    assert isinstance(binding, dict)
    binding["transition_id"] = 1

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="transition_id must be non-empty text",
    ):
        _assert_cross_lineage_coherence([legacy], [authenticated])


def test_cross_lineage_hashes_must_use_canonical_sha256_text() -> None:
    legacy = _legacy_record()
    authenticated = _authenticated_record()
    legacy["proposal_sha256"] = f" {'b' * 64} "
    proposal_artifact = authenticated["proposal_artifact"]
    assert isinstance(proposal_artifact, dict)
    proposal_artifact["sha256"] = f" {'b' * 64} "

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="proposal_sha256 must be canonical lowercase SHA-256 text",
    ):
        _assert_cross_lineage_coherence([legacy], [authenticated])


def test_staged_symlink_is_rejected_even_when_target_bytes_match(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"expected")
    link = stage / "payload.bin"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match=r"(no-follow|links or reparse|unsafe staged)",
    ):
        _read_staged_regular_file(stage, "payload.bin", field="payload")


def test_staged_intermediate_directory_symlink_is_rejected(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.bin").write_bytes(b"expected")
    linked_directory = stage / "provenance"
    try:
        linked_directory.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation unavailable: {exc}")

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match=r"(unsafe staged parent|links or reparse|no-follow)",
    ):
        _read_staged_regular_file(
            stage,
            "provenance/payload.bin",
            field="payload",
        )


def test_atomic_publication_never_replaces_newly_appeared_empty_target(
    tmp_path: Path,
) -> None:
    source = tmp_path / "staged"
    source.mkdir()
    (source / "payload.txt").write_text("candidate\n", encoding="utf-8")
    destination = tmp_path / "published"
    destination.mkdir()

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="output_dir appeared during atomic publication",
    ):
        _atomic_publish_directory_no_replace(source, destination)

    assert source.is_dir()
    assert destination.is_dir()
    assert list(destination.iterdir()) == []


def _program_state_with_evidence() -> dict[str, object]:
    return {
        "workstreams": [
            {
                "workstream_id": "benchmark",
                "planning_state": {
                    "evidence_bindings": [
                        {
                            "role": "measured_source",
                            "sha256": "e" * 64,
                        }
                    ]
                },
            }
        ]
    }


def _base_graph() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "graph_id": "graph-v1",
        "research_scope": "empirical-derived merge-gate regression",
        "nodes": [
            {
                "node_id": "question-1",
                "node_type": "research_question",
                "statement": "Does the derived analysis support the empirical claim?",
            },
            {
                "node_id": "hypothesis-1",
                "node_type": "hypothesis",
                "statement": "The empirical claim holds.",
                "metadata": {"claim_scope": "empirical"},
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


def _empirical_derived_proposal(*, base_sha: str, result_sha: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "transition_id": "transition-1",
        "base_graph_id": "graph-v1",
        "base_graph_sha256": base_sha,
        "new_graph_id": "graph-v2",
        "target_node_id": "hypothesis-1",
        "source_action": {
            "action_id": "action-1",
            "action_class": "existing_data_reanalysis",
            "action_version": "1.0",
            "execution_mode": "typed_local_action",
        },
        "result_node": {
            "node_id": "result-1",
            "node_type": "analysis",
            "statement": "A bounded analysis of measured input completed.",
            "artifact_bindings": [
                {
                    "role": "primary_result",
                    "path": "result.json",
                    "sha256": result_sha,
                }
            ],
            "metadata": {"result_origin": "authorized_local_analysis"},
        },
        "input_evidence_bindings": [
            {
                "workstream_id": "benchmark",
                "role": "measured_source",
                "sha256": "e" * 64,
            }
        ],
        "proposed_inference": {
            "tests_edge_id": "tests-1",
            "inference_edge_id": "inference-1",
            "relation": "supports",
            "rationale": "The derived analysis bears on the empirical target.",
        },
        "limitations": ["Input-origin artifact path is not first-class yet."],
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
        "inference_scope": "empirical_derived",
        "verifier_id": "bounded-verifier-v1.1",
        "rationale": "The exact derived relation was reviewed within the declared scope.",
        "limitations": ["No input artifact path contract exists yet."],
        "domain_verified": True,
    }


def test_empirical_derived_fails_closed_without_resolvable_input_artifact_contract(
    tmp_path: Path,
) -> None:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"derived": 1.0})
    base_file = tmp_path / "base_graph.json"
    base_sha = _write_json(base_file, _base_graph())
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(
        proposal_file,
        _empirical_derived_proposal(base_sha=base_sha, result_sha=result_sha),
    )
    verification_file = tmp_path / "verification.json"
    _write_json(
        verification_file,
        _verification(proposal_sha=proposal_sha, base_sha=base_sha),
    )

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="does not yet accept empirical_derived",
    ):
        apply_authenticated_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            verification_decision_path=verification_file,
            program_state=_program_state_with_evidence(),
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
        )
    assert not (tmp_path / "out").exists()
