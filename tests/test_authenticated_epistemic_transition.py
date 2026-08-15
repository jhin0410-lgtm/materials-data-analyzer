from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import authenticated_epistemic_transition as module
from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE,
    AuthenticatedEpistemicTransitionError,
    apply_authenticated_epistemic_transition_files,
)


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _program_state() -> dict[str, object]:
    return {"workstreams": []}


def _base_graph() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "graph_id": "graph-v1",
        "research_scope": "authenticated transition regression",
        "nodes": [
            {
                "node_id": "question-1",
                "node_type": "research_question",
                "statement": "What does the bounded result establish?",
            },
            {
                "node_id": "hypothesis-1",
                "node_type": "hypothesis",
                "statement": "The target proposition holds within the declared scope.",
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
                {"role": "primary_result", "path": "result.json", "sha256": result_sha}
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


def _verification(
    *,
    proposal_sha: str,
    base_sha: str,
    inference_edge_id: str = "inference-1",
    schema_version: str = "1.1",
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "decision_id": "verification-1",
        "transition_id": "transition-1",
        "proposal_sha256": proposal_sha,
        "base_graph_sha256": base_sha,
        "inference_edge_id": inference_edge_id,
        "result_node_id": "result-1",
        "target_node_id": "hypothesis-1",
        "relation": "supports",
        "inference_scope": "structural",
        "verifier_id": "bounded-domain-verifier-v1.1",
        "rationale": "The exact inference edge is verified only in structural scope.",
        "limitations": ["No positive closeout is granted."],
        "domain_verified": True,
    }


def _fixture_files(tmp_path: Path) -> tuple[Path, Path, Path, str, str, str]:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"rank_before": 3, "rank_after": 4})
    base_file = tmp_path / "base_graph.json"
    base_sha = _write_json(base_file, _base_graph())
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(
        proposal_file,
        _proposal(base_sha=base_sha, result_sha=result_sha),
    )
    verification_file = tmp_path / "verification.json"
    verification_sha = _write_json(
        verification_file,
        _verification(proposal_sha=proposal_sha, base_sha=base_sha),
    )
    return (
        base_file,
        proposal_file,
        verification_file,
        base_sha,
        proposal_sha,
        verification_sha,
    )


def test_authenticated_transition_binds_self_contained_snapshots_and_exact_edge(
    tmp_path: Path,
) -> None:
    (
        base_file,
        proposal_file,
        verification_file,
        base_sha,
        proposal_sha,
        verification_sha,
    ) = _fixture_files(tmp_path)
    result_source = tmp_path / "result.json"
    result_source_bytes = result_source.read_bytes()
    result_sha = hashlib.sha256(result_source_bytes).hexdigest()
    output = tmp_path / "out"

    result = apply_authenticated_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verification_file,
        program_state=_program_state(),
        artifact_root=tmp_path,
        output_dir=output,
    )

    assert result["domain_verification_applied"] is True
    assert result["inference_assessment_level"] == "domain_verified"
    assert result["target_after"]["status"] == "provisionally_supported"
    binding = result["authenticated_inference_binding"]
    assert binding["inference_edge_id"] == "inference-1"
    assert binding["base_graph_sha256"] == base_sha
    assert binding["proposal_sha256"] == proposal_sha
    assert binding["verification_decision_sha256"] == verification_sha
    boundary = result["autonomy_boundary"]
    assert boundary["exact_inference_edge_identity_authenticated"] is True
    assert boundary["source_file_toctou_changes_transition_bytes"] is False
    assert boundary["provenance_snapshots_self_contained"] is True
    assert boundary["result_artifact_snapshots_self_contained"] is True
    assert boundary["result_artifact_source_drift_changes_published_evidence"] is False
    assert boundary["temporary_transition_staging_used"] is False
    assert boundary["authenticated_v11_verifier_consumed_by_legacy_critic"] is False
    assert boundary["verifier_identity_or_credential_authenticated"] is False
    assert boundary["execution_authorized_by_authentication"] is False
    assert boundary["positive_closeout_granted_by_authentication"] is False

    base_snapshot = output / "provenance" / "base_graph.json"
    proposal_snapshot = output / "provenance" / "proposal.json"
    verification_snapshot = output / "provenance" / "verification_decision.json"
    result_snapshot = output / "provenance" / "result_artifacts" / "result-000.json"
    assert hashlib.sha256(base_snapshot.read_bytes()).hexdigest() == base_sha
    assert hashlib.sha256(proposal_snapshot.read_bytes()).hexdigest() == proposal_sha
    assert hashlib.sha256(verification_snapshot.read_bytes()).hexdigest() == verification_sha
    assert result_snapshot.read_bytes() == result_source_bytes
    assert hashlib.sha256(result_snapshot.read_bytes()).hexdigest() == result_sha

    graph = json.loads((output / "epistemic_graph.json").read_text(encoding="utf-8"))
    edge = next(item for item in graph["edges"] if item["edge_id"] == "inference-1")
    assert edge["assessment_level"] == "domain_verified"
    assert edge["verification_artifact"] == {
        "role": AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE,
        "path": str(verification_snapshot.resolve()),
        "sha256": verification_sha,
    }
    result_node = next(item for item in graph["nodes"] if item["node_id"] == "result-1")
    assert result_node["artifact_bindings"] == [
        {
            "role": "primary_result",
            "path": str(result_snapshot.resolve()),
            "sha256": result_sha,
        }
    ]

    lineage = graph["metadata"]["authenticated_transition_lineage"][-1]
    assert lineage["base_graph_artifact"]["path"] == str(base_snapshot.resolve())
    assert lineage["base_graph_artifact"]["source_path"] == str(base_file.resolve())
    assert lineage["base_graph_artifact"]["source_path_authoritative"] is False
    assert lineage["proposal_artifact"]["path"] == str(proposal_snapshot.resolve())
    assert lineage["proposal_artifact"]["source_path"] == str(proposal_file.resolve())
    assert lineage["proposal_artifact"]["source_path_authoritative"] is False
    assert lineage["proposal_artifact"]["sha256"] == proposal_sha
    assert lineage["verification_decision_artifact"]["path"] == str(
        verification_snapshot.resolve()
    )
    assert lineage["verification_decision_artifact"]["source_path"] == str(
        verification_file.resolve()
    )
    assert lineage["verification_decision_artifact"]["source_path_authoritative"] is False
    assert lineage["result_artifact_snapshots"] == [
        {
            "role": "primary_result",
            "path": str(result_snapshot.resolve()),
            "source_path": str(result_source.resolve()),
            "source_path_authoritative": False,
            "sha256": result_sha,
            "size_bytes": len(result_source_bytes),
        }
    ]
    assert lineage["authenticated_inference_binding"] == binding


def test_v10_verifier_cannot_enter_authenticated_transition_path(tmp_path: Path) -> None:
    base_file, proposal_file, verification_file, _, proposal_sha, _ = _fixture_files(tmp_path)
    base_sha = hashlib.sha256(base_file.read_bytes()).hexdigest()
    _write_json(
        verification_file,
        _verification(
            proposal_sha=proposal_sha,
            base_sha=base_sha,
            schema_version="1.0",
        ),
    )

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="requires verification decision schema v1.1",
    ):
        apply_authenticated_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            verification_decision_path=verification_file,
            program_state=_program_state(),
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
        )
    assert not (tmp_path / "out").exists()


def test_same_triple_wrong_edge_id_fails_before_output(tmp_path: Path) -> None:
    base_file, proposal_file, verification_file, base_sha, proposal_sha, _ = _fixture_files(
        tmp_path
    )
    _write_json(
        verification_file,
        _verification(
            proposal_sha=proposal_sha,
            base_sha=base_sha,
            inference_edge_id="different-edge",
        ),
    )

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="inference_edge_id does not match proposal",
    ):
        apply_authenticated_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            verification_decision_path=verification_file,
            program_state=_program_state(),
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
        )
    assert not (tmp_path / "out").exists()


def test_source_mutation_after_validation_does_not_change_authenticated_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_file, proposal_file, verification_file, base_sha, proposal_sha, verification_sha = (
        _fixture_files(tmp_path)
    )
    initial_base = base_file.read_bytes()
    initial_proposal = proposal_file.read_bytes()
    initial_verification = verification_file.read_bytes()
    real_validate = module.validate_transition_proposal

    def mutating_validate(*args: object, **kwargs: object) -> dict[str, object]:
        validated = real_validate(*args, **kwargs)
        base_file.write_text('{"tampered":"base"}\n', encoding="utf-8")
        proposal_file.write_text('{"tampered":"proposal"}\n', encoding="utf-8")
        verification_file.write_text('{"tampered":"verification"}\n', encoding="utf-8")
        return validated

    monkeypatch.setattr(module, "validate_transition_proposal", mutating_validate)
    output = tmp_path / "out"
    result = apply_authenticated_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verification_file,
        program_state=_program_state(),
        artifact_root=tmp_path,
        output_dir=output,
    )

    assert base_file.read_bytes() != initial_base
    assert proposal_file.read_bytes() != initial_proposal
    assert verification_file.read_bytes() != initial_verification
    assert (output / "provenance" / "base_graph.json").read_bytes() == initial_base
    assert (output / "provenance" / "proposal.json").read_bytes() == initial_proposal
    assert (output / "provenance" / "verification_decision.json").read_bytes() == initial_verification
    assert result["base_graph_binding"]["sha256"] == base_sha
    assert result["proposal_binding"]["sha256"] == proposal_sha
    assert result["verification_decision_binding"]["sha256"] == verification_sha


def test_verifier_checksum_is_bound_to_final_snapshot_not_source_file(
    tmp_path: Path,
) -> None:
    base_file, proposal_file, verification_file, _, _, verification_sha = _fixture_files(
        tmp_path
    )
    output = tmp_path / "out"

    apply_authenticated_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verification_file,
        program_state=_program_state(),
        artifact_root=tmp_path,
        output_dir=output,
    )

    graph = json.loads((output / "epistemic_graph.json").read_text(encoding="utf-8"))
    edge = next(item for item in graph["edges"] if item["edge_id"] == "inference-1")
    verifier_snapshot = output / "provenance" / "verification_decision.json"
    assert edge["verification_artifact"]["sha256"] == verification_sha
    assert edge["verification_artifact"]["path"] == str(verifier_snapshot.resolve())
