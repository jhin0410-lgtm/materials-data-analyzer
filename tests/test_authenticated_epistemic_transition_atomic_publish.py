from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import authenticated_epistemic_transition as module
from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    AuthenticatedEpistemicTransitionError,
    apply_authenticated_epistemic_transition_files,
)


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    result_file = tmp_path / "result.json"
    result_sha = _write_json(result_file, {"bounded": True})
    base_file = tmp_path / "base.json"
    base_sha = _write_json(
        base_file,
        {
            "schema_version": "1.0",
            "graph_id": "graph-v1",
            "research_scope": "atomic bundle publication regression",
            "nodes": [
                {
                    "node_id": "hypothesis-1",
                    "node_type": "hypothesis",
                    "statement": "Bound structural target.",
                    "metadata": {"claim_scope": "structural"},
                }
            ],
            "edges": [],
        },
    )
    proposal_file = tmp_path / "proposal.json"
    proposal_sha = _write_json(
        proposal_file,
        {
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
                "statement": "Bound structural simulation.",
                "artifact_bindings": [
                    {
                        "role": "primary_result",
                        "path": str(result_file),
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
                "rationale": "Authenticated diagnostic proposal.",
            },
            "limitations": ["Diagnostic until consumer promotion."],
        },
    )
    verifier_file = tmp_path / "verification.json"
    _write_json(
        verifier_file,
        {
            "schema_version": "1.1",
            "decision_id": "decision-1",
            "transition_id": "transition-1",
            "proposal_sha256": proposal_sha,
            "base_graph_sha256": base_sha,
            "inference_edge_id": "inference-1",
            "result_node_id": "result-1",
            "target_node_id": "hypothesis-1",
            "relation": "supports",
            "inference_scope": "structural",
            "verifier_id": "verifier-v1.1",
            "rationale": "Exact edge authenticated.",
            "limitations": [],
            "domain_verified": True,
        },
    )
    return base_file, proposal_file, verifier_file


def test_output_directory_is_not_visible_until_bundle_validation_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_file, proposal_file, verifier_file = _fixture(tmp_path)
    output = tmp_path / "published"
    real_validate = module._validate_written_bundle
    observations: list[tuple[bool, bool]] = []

    def validate_hidden_bundle(root: Path, **kwargs: object):
        observations.append((output.exists(), root.exists()))
        result = real_validate(root, **kwargs)
        observations.append((output.exists(), root.exists()))
        return result

    monkeypatch.setattr(module, "_validate_written_bundle", validate_hidden_bundle)

    apply_authenticated_epistemic_transition_files(
        base_graph_path=base_file,
        proposal_path=proposal_file,
        verification_decision_path=verifier_file,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
        output_dir=output,
    )

    assert observations == [(False, True), (False, True)]
    assert output.is_dir()
    assert not [path for path in tmp_path.iterdir() if path.name.startswith(".published.tmp-")]


def test_tampered_temporary_snapshot_fails_before_publication_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_file, proposal_file, verifier_file = _fixture(tmp_path)
    output = tmp_path / "published"
    real_validate = module._validate_written_bundle

    def tamper_then_validate(root: Path, **kwargs: object):
        payloads = kwargs["payloads"]
        assert isinstance(payloads, dict)
        relative = next(iter(payloads))
        (root / relative).write_bytes(b"tampered")
        return real_validate(root, **kwargs)

    monkeypatch.setattr(module, "_validate_written_bundle", tamper_then_validate)

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="snapshot bytes changed before atomic publication",
    ):
        apply_authenticated_epistemic_transition_files(
            base_graph_path=base_file,
            proposal_path=proposal_file,
            verification_decision_path=verifier_file,
            program_state={"workstreams": []},
            artifact_root=tmp_path,
            output_dir=output,
        )

    assert not output.exists()
    assert not [path for path in tmp_path.iterdir() if path.name.startswith(".published.tmp-")]
