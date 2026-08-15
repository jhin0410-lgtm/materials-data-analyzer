from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    authenticated_epistemic_transition as module,
)
from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    AuthenticatedEpistemicTransitionError,
    apply_authenticated_epistemic_transition_files,
)
from materials_data_analyzer.research_loop.input_evidence_origin_snapshot import (
    INPUT_EVIDENCE_ORIGIN_REQUEST_SNAPSHOT_PATH,
    INPUT_EVIDENCE_ORIGIN_SNAPSHOT_MANIFEST_PATH,
)


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: dict[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _fixture(
    tmp_path: Path,
    *,
    origin_class: str = "empirical_measurement",
) -> dict[str, object]:
    result_path = tmp_path / "analysis-result.json"
    result_sha = _write_json(result_path, {"derived_metric": 1.23})

    evidence_bytes = b"measurement-input\x00\x04"
    evidence_sha = hashlib.sha256(evidence_bytes).hexdigest()
    (tmp_path / "input-evidence.bin").write_bytes(evidence_bytes)
    declaration_bytes = _json_bytes(
        {
            "schema_version": "1.0",
            "evidence_id": "evidence-1",
            "evidence_artifact_sha256": evidence_sha,
            "origin_class": origin_class,
            "origin_statement": "Exact input origin classification.",
            "limitations": ["Classification is not physical truth."],
        }
    )
    (tmp_path / "origin-declaration.json").write_bytes(declaration_bytes)
    verification_origin_bytes = _json_bytes(
        {
            "schema_version": "1.0",
            "decision_id": "origin-decision-1",
            "evidence_id": "evidence-1",
            "evidence_artifact_sha256": evidence_sha,
            "origin_declaration_sha256": hashlib.sha256(declaration_bytes).hexdigest(),
            "origin_class": origin_class,
            "verification_scope": "origin_classification_only",
            "verifier_id": "origin-reviewer",
            "rationale": "Classification provenance only.",
            "limitations": ["Verifier credentials are not authenticated."],
            "domain_verified_origin": True,
        }
    )
    (tmp_path / "origin-verification.json").write_bytes(verification_origin_bytes)

    input_binding = {
        "workstream_id": "ws-empirical",
        "role": "measurement_input",
        "sha256": evidence_sha,
    }
    program_state: dict[str, object] = {
        "schema_version": "1.0",
        "workstreams": [
            {
                "workstream_id": "ws-empirical",
                "planning_state": {"evidence_bindings": [dict(input_binding)]},
            }
        ],
    }
    base = {
        "schema_version": "1.0",
        "graph_id": "graph-v1",
        "research_scope": "empirical-derived authenticated snapshot regression",
        "nodes": [
            {
                "node_id": "question-1",
                "node_type": "research_question",
                "statement": "What does the bounded analysis indicate?",
            },
            {
                "node_id": "claim-1",
                "node_type": "claim",
                "statement": "The empirical target is supported within scope.",
                "metadata": {"claim_scope": "empirical"},
            },
        ],
        "edges": [
            {
                "edge_id": "motivation-1",
                "source_node_id": "question-1",
                "target_node_id": "claim-1",
                "relation": "motivates",
                "assessment_level": "proposal",
                "rationale": "The question motivates the claim.",
                "active": True,
            }
        ],
    }
    base_path = tmp_path / "base.json"
    base_sha = _write_json(base_path, base)
    proposal = {
        "schema_version": "1.0",
        "transition_id": "transition-empirical-1",
        "base_graph_id": "graph-v1",
        "base_graph_sha256": base_sha,
        "new_graph_id": "graph-v2",
        "target_node_id": "claim-1",
        "source_action": {
            "action_id": "analysis-action-1",
            "action_class": "existing_data_reanalysis",
            "action_version": "1.0",
            "execution_mode": "typed_local_action",
        },
        "result_node": {
            "node_id": "analysis-1",
            "node_type": "analysis",
            "statement": "A bounded analysis of the tracked measurement completed.",
            "artifact_bindings": [
                {
                    "role": "primary_result",
                    "path": "analysis-result.json",
                    "sha256": result_sha,
                }
            ],
            "metadata": {"result_origin": "authorized_local_analysis"},
        },
        "input_evidence_bindings": [dict(input_binding)],
        "proposed_inference": {
            "tests_edge_id": "tests-1",
            "inference_edge_id": "inference-1",
            "relation": "supports",
            "rationale": "The derived analysis directionally supports the empirical target.",
        },
        "limitations": ["Input origin classification is not physical truth."],
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_sha = _write_json(proposal_path, proposal)
    verification = {
        "schema_version": "1.1",
        "decision_id": "verification-1",
        "transition_id": "transition-empirical-1",
        "proposal_sha256": proposal_sha,
        "base_graph_sha256": base_sha,
        "inference_edge_id": "inference-1",
        "result_node_id": "analysis-1",
        "target_node_id": "claim-1",
        "relation": "supports",
        "inference_scope": "empirical_derived",
        "verifier_id": "bounded-domain-verifier-v1.1",
        "rationale": "Exact directional inference is verified only as empirical-derived provenance.",
        "limitations": ["No positive closeout is granted."],
        "domain_verified": True,
    }
    verification_path = tmp_path / "verification.json"
    _write_json(verification_path, verification)
    request = {
        "schema_version": "1.0",
        "items": [
            {
                **input_binding,
                "evidence_path": "input-evidence.bin",
                "origin_declaration_path": "origin-declaration.json",
                "origin_verification_decision_path": "origin-verification.json",
            }
        ],
    }
    request_path = tmp_path / "input-origin-request.json"
    request_path.write_bytes(_json_bytes(request))
    return {
        "base_path": base_path,
        "proposal_path": proposal_path,
        "verification_path": verification_path,
        "request_path": request_path,
        "program_state": program_state,
        "proposal_sha": proposal_sha,
        "evidence_bytes": evidence_bytes,
        "request_bytes": request_path.read_bytes(),
    }


def _apply(tmp_path: Path, fixture: dict[str, object], *, request: bool = True):
    output = tmp_path / "out"
    result = apply_authenticated_epistemic_transition_files(
        base_graph_path=fixture["base_path"],
        proposal_path=fixture["proposal_path"],
        verification_decision_path=fixture["verification_path"],
        program_state=fixture["program_state"],
        artifact_root=tmp_path,
        output_dir=output,
        input_evidence_origin_request_path=fixture["request_path"] if request else None,
    )
    return output, result


def test_empirical_derived_transition_snapshots_input_origin_but_remains_diagnostic(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    output, result = _apply(tmp_path, fixture)
    assert result["authenticated_transition_policy_version"] == "2.10"
    assert result["scientific_authority_applied"] is False
    assert result["inference_assessment_level"] == "diagnostic"
    assert result["verification"]["inference_scope"] == "empirical_derived"
    binding = result["input_evidence_origin_snapshot_binding"]
    assert binding["path"] == INPUT_EVIDENCE_ORIGIN_SNAPSHOT_MANIFEST_PATH
    assert binding["scientific_authority_applied"] is False
    snapshot_manifest_bytes = (output / binding["path"]).read_bytes()
    assert hashlib.sha256(snapshot_manifest_bytes).hexdigest() == binding["sha256"]
    snapshot_manifest = json.loads(snapshot_manifest_bytes)
    assert snapshot_manifest["proposal_sha256"] == fixture["proposal_sha"]
    assert snapshot_manifest["all_inputs_empirical_classified"] is True
    assert snapshot_manifest["empirical_authority_granted"] is False
    assert (output / INPUT_EVIDENCE_ORIGIN_REQUEST_SNAPSHOT_PATH).read_bytes() == fixture[
        "request_bytes"
    ]
    evidence_artifact = snapshot_manifest["items"][0]["evidence_artifact"]
    assert (output / evidence_artifact["path"]).read_bytes() == fixture["evidence_bytes"]
    graph = json.loads((output / "epistemic_graph.json").read_text())
    inference = next(edge for edge in graph["edges"] if edge["edge_id"] == "inference-1")
    assert inference["assessment_level"] == "diagnostic"
    assert "verification_artifact" not in inference


def test_nonempty_input_evidence_requires_origin_request(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="requires input_evidence_origin_request_path",
    ):
        _apply(tmp_path, fixture, request=False)
    assert not (tmp_path / "out").exists()


def test_empirical_derived_rejects_nonempirical_input_origin(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, origin_class="analysis_output")
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="every input evidence origin classification to be empirical",
    ):
        _apply(tmp_path, fixture)
    assert not (tmp_path / "out").exists()


def test_producer_publishes_captured_request_payloads_not_later_source_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path)
    original_prepare = module.prepare_input_evidence_origin_snapshots
    captured_request = fixture["request_bytes"]
    captured_evidence = fixture["evidence_bytes"]

    def wrapped_prepare(**kwargs):
        result = original_prepare(**kwargs)
        Path(fixture["request_path"]).write_bytes(b"mutated-after-authentication")
        (tmp_path / "input-evidence.bin").write_bytes(b"mutated-evidence-after-authentication")
        return result

    monkeypatch.setattr(module, "prepare_input_evidence_origin_snapshots", wrapped_prepare)
    output, result = _apply(tmp_path, fixture)
    assert (output / INPUT_EVIDENCE_ORIGIN_REQUEST_SNAPSHOT_PATH).read_bytes() == captured_request
    snapshot_manifest = json.loads(
        (output / result["input_evidence_origin_snapshot_binding"]["path"]).read_bytes()
    )
    evidence_path = snapshot_manifest["items"][0]["evidence_artifact"]["path"]
    assert (output / evidence_path).read_bytes() == captured_evidence


def test_no_input_transition_rejects_unrelated_origin_request(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    proposal_path = Path(fixture["proposal_path"])
    proposal = json.loads(proposal_path.read_bytes())
    proposal["input_evidence_bindings"] = []
    proposal["result_node"]["node_type"] = "analysis"
    proposal["result_node"]["metadata"] = {"result_origin": "authorized_local_analysis"}
    proposal["proposed_inference"]["rationale"] = "A structural analysis supports the target."
    base_path = Path(fixture["base_path"])
    base = json.loads(base_path.read_bytes())
    base["nodes"][1]["metadata"] = {"claim_scope": "structural"}
    base_sha = _write_json(base_path, base)
    proposal["base_graph_sha256"] = base_sha
    proposal_sha = _write_json(proposal_path, proposal)
    verification_path = Path(fixture["verification_path"])
    verification = json.loads(verification_path.read_bytes())
    verification["base_graph_sha256"] = base_sha
    verification["proposal_sha256"] = proposal_sha
    verification["inference_scope"] = "structural"
    _write_json(verification_path, verification)

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="not allowed when proposal input_evidence_bindings are empty",
    ):
        apply_authenticated_epistemic_transition_files(
            base_graph_path=base_path,
            proposal_path=proposal_path,
            verification_decision_path=verification_path,
            program_state=fixture["program_state"],
            artifact_root=tmp_path,
            output_dir=tmp_path / "out",
            input_evidence_origin_request_path=fixture["request_path"],
        )
