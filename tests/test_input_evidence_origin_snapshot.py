from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.input_evidence_origin_snapshot import (
    INPUT_EVIDENCE_ORIGIN_REQUEST_SNAPSHOT_PATH,
    INPUT_EVIDENCE_ORIGIN_SNAPSHOT_MANIFEST_PATH,
    InputEvidenceOriginSnapshotError,
    prepare_input_evidence_origin_snapshots,
)


def _json_bytes(value: dict[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _fixture(
    tmp_path: Path, *, origin_class: str = "empirical_measurement"
) -> tuple[Path, Path, dict[str, object], list[dict[str, str]], str]:
    root = tmp_path / "artifacts"
    root.mkdir()
    evidence = b"measurement-payload\x00\x03"
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    (root / "evidence.bin").write_bytes(evidence)
    declaration = _json_bytes(
        {
            "schema_version": "1.0",
            "evidence_id": "ev-1",
            "evidence_artifact_sha256": evidence_sha,
            "origin_class": origin_class,
            "origin_statement": "Exact evidence origin classification.",
            "limitations": ["Classification is not physical truth."],
        }
    )
    (root / "declaration.json").write_bytes(declaration)
    verification = _json_bytes(
        {
            "schema_version": "1.0",
            "decision_id": "origin-v-1",
            "evidence_id": "ev-1",
            "evidence_artifact_sha256": evidence_sha,
            "origin_declaration_sha256": hashlib.sha256(declaration).hexdigest(),
            "origin_class": origin_class,
            "verification_scope": "origin_classification_only",
            "verifier_id": "origin-reviewer",
            "rationale": "Origin classification provenance only.",
            "limitations": ["Credentials are outside this contract."],
            "domain_verified_origin": True,
        }
    )
    (root / "verification.json").write_bytes(verification)
    binding = {
        "workstream_id": "ws-1",
        "role": "measurement",
        "sha256": evidence_sha,
    }
    program_state: dict[str, object] = {
        "schema_version": "1.0",
        "workstreams": [
            {
                "workstream_id": "ws-1",
                "planning_state": {"evidence_bindings": [dict(binding)]},
            }
        ],
    }
    request = _json_bytes(
        {
            "schema_version": "1.0",
            "items": [
                {
                    **binding,
                    "evidence_path": "evidence.bin",
                    "origin_declaration_path": "declaration.json",
                    "origin_verification_decision_path": "verification.json",
                }
            ],
        }
    )
    request_path = tmp_path / "request.json"
    request_path.write_bytes(request)
    return root, request_path, program_state, [binding], evidence_sha


def _prepare(tmp_path: Path, *, origin_class: str = "empirical_measurement"):
    root, request_path, program_state, bindings, _ = _fixture(
        tmp_path, origin_class=origin_class
    )
    return prepare_input_evidence_origin_snapshots(
        request_path=request_path,
        proposal_input_evidence_bindings=bindings,
        program_state=program_state,
        artifact_root=root,
        transition_id="transition-1",
        proposal_sha256="a" * 64,
    )


def test_builds_deterministic_self_contained_snapshot_payloads(tmp_path: Path) -> None:
    result = _prepare(tmp_path)
    manifest = result["manifest"]
    assert manifest["transition_id"] == "transition-1"
    assert manifest["proposal_sha256"] == "a" * 64
    assert manifest["all_inputs_empirical_classified"] is True
    assert result["all_inputs_empirical_classified"] is True
    payloads = result["payloads"]
    assert INPUT_EVIDENCE_ORIGIN_REQUEST_SNAPSHOT_PATH in payloads
    assert INPUT_EVIDENCE_ORIGIN_SNAPSHOT_MANIFEST_PATH in payloads
    item = manifest["items"][0]
    evidence_artifact = item["evidence_artifact"]
    assert evidence_artifact["path"].endswith("/0000/evidence.bin")
    assert hashlib.sha256(payloads[evidence_artifact["path"]]).hexdigest() == evidence_artifact["sha256"]
    assert hashlib.sha256(result["manifest_bytes"]).hexdigest() == result["manifest_sha256"]


def test_nonempirical_origin_is_snapshotted_but_not_classified_empirical(tmp_path: Path) -> None:
    result = _prepare(tmp_path, origin_class="analysis_output")
    assert result["all_inputs_empirical_classified"] is False
    assert result["manifest"]["items"][0]["origin_class"] == "analysis_output"
    assert result["authority_boundary"]["empirical_authority_granted"] is False


@pytest.mark.parametrize(
    "field",
    [
        "program_state_provenance_reauthenticated",
        "physical_origin_truth_authenticated",
        "verifier_identity_or_credential_authenticated",
        "scientific_result_validity_authenticated",
        "support_independence_established",
        "empirical_authority_granted",
        "scientific_status_changed",
        "execution_authorized",
        "positive_closeout_granted",
    ],
)
def test_snapshot_assembler_never_overclaims_authority(tmp_path: Path, field: str) -> None:
    result = _prepare(tmp_path)
    assert result["authority_boundary"][field] is False


def test_request_snapshot_binds_exact_request_bytes(tmp_path: Path) -> None:
    root, request_path, program_state, bindings, _ = _fixture(tmp_path)
    exact_request = request_path.read_bytes()
    result = prepare_input_evidence_origin_snapshots(
        request_path=request_path,
        proposal_input_evidence_bindings=bindings,
        program_state=program_state,
        artifact_root=root,
        transition_id="transition-1",
        proposal_sha256="b" * 64,
    )
    assert result["payloads"][INPUT_EVIDENCE_ORIGIN_REQUEST_SNAPSHOT_PATH] == exact_request
    assert result["manifest"]["request_artifact"]["sha256"] == hashlib.sha256(exact_request).hexdigest()


def test_rejects_noncanonical_proposal_sha(tmp_path: Path) -> None:
    root, request_path, program_state, bindings, _ = _fixture(tmp_path)
    with pytest.raises(InputEvidenceOriginSnapshotError, match="canonical lowercase SHA-256"):
        prepare_input_evidence_origin_snapshots(
            request_path=request_path,
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
            transition_id="transition-1",
            proposal_sha256="A" * 64,
        )


def test_rejects_request_tamper_against_program_and_proposal_identity(tmp_path: Path) -> None:
    root, request_path, program_state, bindings, _ = _fixture(tmp_path)
    request = json.loads(request_path.read_bytes())
    request["items"][0]["role"] = "other-role"
    request_path.write_bytes(_json_bytes(request))
    with pytest.raises(InputEvidenceOriginSnapshotError, match="authentication failed"):
        prepare_input_evidence_origin_snapshots(
            request_path=request_path,
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
            transition_id="transition-1",
            proposal_sha256="c" * 64,
        )


def test_source_request_path_is_informational_only(tmp_path: Path) -> None:
    result = _prepare(tmp_path)
    manifest = result["manifest"]
    assert manifest["source_request_path_authoritative"] is False
    assert isinstance(manifest["source_request_path"], str)
