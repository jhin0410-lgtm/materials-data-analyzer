from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.input_evidence_origin_request import (
    InputEvidenceOriginRequestError,
    authenticate_input_evidence_origin_request,
)


def _json_bytes(value: dict[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _fixture(tmp_path: Path) -> tuple[Path, dict[str, object], list[dict[str, str]], bytes]:
    root = tmp_path / "artifacts"
    root.mkdir()
    evidence = b"measurement-bytes\x00\x02"
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    (root / "evidence.bin").write_bytes(evidence)

    declaration_obj: dict[str, object] = {
        "schema_version": "1.0",
        "evidence_id": "ev-1",
        "evidence_artifact_sha256": evidence_sha,
        "origin_class": "empirical_measurement",
        "origin_statement": "Exact bytes are classified as measurement output.",
        "limitations": ["Classification does not establish physical truth."],
    }
    declaration = _json_bytes(declaration_obj)
    (root / "origin-declaration.json").write_bytes(declaration)

    verification_obj: dict[str, object] = {
        "schema_version": "1.0",
        "decision_id": "origin-v-1",
        "evidence_id": "ev-1",
        "evidence_artifact_sha256": evidence_sha,
        "origin_declaration_sha256": hashlib.sha256(declaration).hexdigest(),
        "origin_class": "empirical_measurement",
        "verification_scope": "origin_classification_only",
        "verifier_id": "origin-reviewer",
        "rationale": "Classification provenance only.",
        "limitations": ["Credentials are not authenticated."],
        "domain_verified_origin": True,
    }
    verification = _json_bytes(verification_obj)
    (root / "origin-verification.json").write_bytes(verification)

    binding = {
        "workstream_id": "ws-1",
        "role": "measurement",
        "sha256": evidence_sha,
    }
    program_state: dict[str, object] = {
        "schema_version": "1.0",
        "workstreams": [
            {
                "workstream_id": "ws-disabled",
                "planning_state": None,
            },
            {
                "workstream_id": "ws-1",
                "planning_state": {"evidence_bindings": [dict(binding)]},
            },
        ],
    }
    request_obj: dict[str, object] = {
        "schema_version": "1.0",
        "items": [
            {
                **binding,
                "evidence_path": "evidence.bin",
                "origin_declaration_path": "origin-declaration.json",
                "origin_verification_decision_path": "origin-verification.json",
            }
        ],
    }
    return root, program_state, [binding], _json_bytes(request_obj)


def _authenticate(tmp_path: Path):
    root, program_state, bindings, request_bytes = _fixture(tmp_path)
    return authenticate_input_evidence_origin_request(
        request_bytes=request_bytes,
        proposal_input_evidence_bindings=bindings,
        program_state=program_state,
        artifact_root=root,
    )


def test_authenticates_exact_request_and_preserves_snapshot_bytes(tmp_path: Path) -> None:
    result = _authenticate(tmp_path)
    assert result.report["schema_version"] == "1.0"
    assert result.report["all_origin_classification_records_authenticated"] is True
    assert result.report["empirical_authority_granted"] is False
    assert len(result.payloads) == 1
    payload = result.payloads[0]
    assert hashlib.sha256(payload.evidence_bytes).hexdigest() == payload.evidence_sha256
    item = result.report["items"][0]
    assert item["origin_class"] == "empirical_measurement"
    assert item["source_paths"]["authoritative"] is False


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
def test_request_contract_never_overclaims_authority(tmp_path: Path, field: str) -> None:
    result = _authenticate(tmp_path)
    assert result.report[field] is False


def test_rejects_request_identity_not_exactly_matching_proposal(tmp_path: Path) -> None:
    root, program_state, bindings, request_bytes = _fixture(tmp_path)
    request = json.loads(request_bytes)
    request["items"][0]["role"] = "other-role"
    with pytest.raises(InputEvidenceOriginRequestError, match="exactly match"):
        authenticate_input_evidence_origin_request(
            request_bytes=_json_bytes(request),
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
        )


def test_rejects_extra_request_identity(tmp_path: Path) -> None:
    root, program_state, bindings, request_bytes = _fixture(tmp_path)
    request = json.loads(request_bytes)
    extra = dict(request["items"][0])
    extra["workstream_id"] = "ws-extra"
    request["items"].append(extra)
    with pytest.raises(InputEvidenceOriginRequestError, match="exactly match"):
        authenticate_input_evidence_origin_request(
            request_bytes=_json_bytes(request),
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
        )


def test_rejects_duplicate_request_identity(tmp_path: Path) -> None:
    root, program_state, bindings, request_bytes = _fixture(tmp_path)
    request = json.loads(request_bytes)
    request["items"].append(dict(request["items"][0]))
    with pytest.raises(InputEvidenceOriginRequestError, match="duplicate program evidence identity"):
        authenticate_input_evidence_origin_request(
            request_bytes=_json_bytes(request),
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
        )


def test_rejects_evidence_bytes_drifting_from_program_sha(tmp_path: Path) -> None:
    root, program_state, bindings, request_bytes = _fixture(tmp_path)
    (root / "evidence.bin").write_bytes(b"drift")
    with pytest.raises(InputEvidenceOriginRequestError, match="do not match proposal"):
        authenticate_input_evidence_origin_request(
            request_bytes=request_bytes,
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
        )


def test_rejects_origin_verification_substitution(tmp_path: Path) -> None:
    root, program_state, bindings, request_bytes = _fixture(tmp_path)
    verification_path = root / "origin-verification.json"
    verification = json.loads(verification_path.read_bytes())
    verification["origin_class"] = "analysis_output"
    verification_path.write_bytes(_json_bytes(verification))
    with pytest.raises(InputEvidenceOriginRequestError, match="bridge rejected"):
        authenticate_input_evidence_origin_request(
            request_bytes=request_bytes,
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
        )


def test_rejects_caller_supplied_origin_class_in_request(tmp_path: Path) -> None:
    root, program_state, bindings, request_bytes = _fixture(tmp_path)
    request = json.loads(request_bytes)
    request["items"][0]["origin_class"] = "empirical_measurement"
    with pytest.raises(InputEvidenceOriginRequestError, match="unknown keys"):
        authenticate_input_evidence_origin_request(
            request_bytes=_json_bytes(request),
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
        )


@pytest.mark.parametrize(
    "bad_path",
    [
        "../evidence.bin",
        "/tmp/evidence.bin",
        "dir\\evidence.bin",
        "evidence.bin:stream",
        "NUL.txt",
        "trailing.",
    ],
)
def test_rejects_nonportable_or_escaping_paths(tmp_path: Path, bad_path: str) -> None:
    root, program_state, bindings, request_bytes = _fixture(tmp_path)
    request = json.loads(request_bytes)
    request["items"][0]["evidence_path"] = bad_path
    with pytest.raises(InputEvidenceOriginRequestError):
        authenticate_input_evidence_origin_request(
            request_bytes=_json_bytes(request),
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
        )


def test_rejects_symlinked_source_file(tmp_path: Path) -> None:
    root, program_state, bindings, request_bytes = _fixture(tmp_path)
    target = root / "real-evidence.bin"
    target.write_bytes((root / "evidence.bin").read_bytes())
    link = root / "linked-evidence.bin"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available")
    request = json.loads(request_bytes)
    request["items"][0]["evidence_path"] = "linked-evidence.bin"
    with pytest.raises(InputEvidenceOriginRequestError, match="symlink"):
        authenticate_input_evidence_origin_request(
            request_bytes=_json_bytes(request),
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
        )


def test_rejects_empty_proposal_bindings(tmp_path: Path) -> None:
    root, program_state, _bindings, request_bytes = _fixture(tmp_path)
    with pytest.raises(InputEvidenceOriginRequestError, match="at least one"):
        authenticate_input_evidence_origin_request(
            request_bytes=request_bytes,
            proposal_input_evidence_bindings=[],
            program_state=program_state,
            artifact_root=root,
        )


def test_request_sha_binds_exact_request_bytes(tmp_path: Path) -> None:
    root, program_state, bindings, request_bytes = _fixture(tmp_path)
    result = authenticate_input_evidence_origin_request(
        request_bytes=request_bytes,
        proposal_input_evidence_bindings=bindings,
        program_state=program_state,
        artifact_root=root,
    )
    assert result.report["request_sha256"] == hashlib.sha256(request_bytes).hexdigest()
