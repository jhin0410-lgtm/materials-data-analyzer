from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from materials_data_analyzer.research_loop import input_evidence_origin_pack as module
from materials_data_analyzer.research_loop.input_evidence_origin_pack import (
    InputEvidenceOriginPackError,
    publish_input_evidence_origin_pack,
)
from materials_data_analyzer.research_loop.input_evidence_origin_request import (
    InputEvidenceOriginPayload,
)


def _json_bytes(value: dict[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _fixture(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, object], list[dict[str, str]], bytes]:
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
                "workstream_id": "ws-1",
                "planning_state": {"evidence_bindings": [dict(binding)]},
            }
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
    request_bytes = _json_bytes(request_obj)
    request_path = root / "request.json"
    request_path.write_bytes(request_bytes)
    return root, request_path, program_state, [binding], request_bytes


def _publish(tmp_path: Path) -> tuple[Path, dict[str, object], bytes]:
    root, request, program_state, bindings, request_bytes = _fixture(tmp_path)
    output = tmp_path / "pack"
    report = publish_input_evidence_origin_pack(
        request_path=request,
        proposal_input_evidence_bindings=bindings,
        program_state=program_state,
        artifact_root=root,
        output_dir=output,
    )
    return output, report, request_bytes


def test_publishes_self_contained_exact_origin_pack_without_authority(tmp_path: Path) -> None:
    output, report, request_bytes = _publish(tmp_path)
    assert output.is_dir()
    assert (output / "request.json").read_bytes() == request_bytes
    manifest_bytes = (output / "input_evidence_origin_pack_manifest.json").read_bytes()
    assert hashlib.sha256(manifest_bytes).hexdigest() == report["manifest_binding"]["sha256"]
    manifest = json.loads(manifest_bytes)
    assert manifest["schema_version"] == "1.0"
    assert manifest["items"][0]["origin_class"] == "empirical_measurement"
    assert manifest["items"][0]["evidence_artifact"]["role"] == "evidence"
    assert manifest["empirical_authority_granted"] is False
    assert manifest["scientific_status_changed"] is False
    assert report["empirical_authority_granted"] is False
    assert report["execution_authorized"] is False
    assert report["positive_closeout_granted"] is False


def test_pack_contains_exact_evidence_declaration_and_verifier_bytes(tmp_path: Path) -> None:
    root, request, program_state, bindings, _ = _fixture(tmp_path)
    expected_evidence = (root / "evidence.bin").read_bytes()
    expected_declaration = (root / "origin-declaration.json").read_bytes()
    expected_verification = (root / "origin-verification.json").read_bytes()
    output = tmp_path / "pack"
    publish_input_evidence_origin_pack(
        request_path=request,
        proposal_input_evidence_bindings=bindings,
        program_state=program_state,
        artifact_root=root,
        output_dir=output,
    )
    assert (output / "items/0000/evidence.bin").read_bytes() == expected_evidence
    assert (output / "items/0000/origin_declaration.json").read_bytes() == expected_declaration
    assert (
        output / "items/0000/origin_verification_decision.json"
    ).read_bytes() == expected_verification


def test_pack_is_relocatable_and_contains_no_authoritative_source_paths(tmp_path: Path) -> None:
    output, report, _ = _publish(tmp_path)
    manifest = json.loads((output / "input_evidence_origin_pack_manifest.json").read_bytes())
    assert "source_paths" not in manifest["items"][0]
    assert manifest["request_source_path_authoritative"] is False
    assert report["request_source"]["authoritative"] is False
    for field in (
        "evidence_artifact",
        "origin_declaration_artifact",
        "origin_verification_decision_artifact",
    ):
        assert not Path(manifest["items"][0][field]["path"]).is_absolute()


def test_rejects_existing_output_directory(tmp_path: Path) -> None:
    root, request, program_state, bindings, _ = _fixture(tmp_path)
    output = tmp_path / "pack"
    output.mkdir()
    with pytest.raises(InputEvidenceOriginPackError, match="must not already exist"):
        publish_input_evidence_origin_pack(
            request_path=request,
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
            output_dir=output,
        )


def test_rejects_symlink_request_source(tmp_path: Path) -> None:
    root, request, program_state, bindings, _ = _fixture(tmp_path)
    link = tmp_path / "request-link.json"
    try:
        os.symlink(request, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available")
    with pytest.raises(InputEvidenceOriginPackError, match="regular non-link"):
        publish_input_evidence_origin_pack(
            request_path=link,
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
            output_dir=tmp_path / "pack",
        )


def test_rejects_request_evidence_drift_before_publication(tmp_path: Path) -> None:
    root, request, program_state, bindings, _ = _fixture(tmp_path)
    (root / "evidence.bin").write_bytes(b"drift")
    with pytest.raises(InputEvidenceOriginPackError, match="request authentication failed"):
        publish_input_evidence_origin_pack(
            request_path=request,
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
            output_dir=tmp_path / "pack",
        )


def test_rejects_malformed_authenticator_report_payload_identity(monkeypatch, tmp_path: Path) -> None:
    root, request, program_state, bindings, request_bytes = _fixture(tmp_path)
    evidence = (root / "evidence.bin").read_bytes()
    declaration = (root / "origin-declaration.json").read_bytes()
    verification = (root / "origin-verification.json").read_bytes()
    wrong_binding = {
        "workstream_id": "wrong-ws",
        "role": "measurement",
        "sha256": hashlib.sha256(evidence).hexdigest(),
    }
    fake = SimpleNamespace(
        request_bytes=request_bytes,
        report={
            "items": [
                {
                    "program_evidence_binding": wrong_binding,
                    "origin_class": "empirical_measurement",
                }
            ]
        },
        payloads=(
            InputEvidenceOriginPayload(
                workstream_id="ws-1",
                role="measurement",
                evidence_sha256=hashlib.sha256(evidence).hexdigest(),
                evidence_bytes=evidence,
                origin_declaration_bytes=declaration,
                origin_verification_decision_bytes=verification,
            ),
        ),
    )
    monkeypatch.setattr(
        module,
        "authenticate_input_evidence_origin_request",
        lambda **kwargs: fake,
    )
    with pytest.raises(InputEvidenceOriginPackError, match="identity diverged"):
        publish_input_evidence_origin_pack(
            request_path=request,
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
            output_dir=tmp_path / "pack",
        )


def test_rejects_unrecognized_origin_class_from_authenticator(monkeypatch, tmp_path: Path) -> None:
    root, request, program_state, bindings, request_bytes = _fixture(tmp_path)
    evidence = (root / "evidence.bin").read_bytes()
    declaration = (root / "origin-declaration.json").read_bytes()
    verification = (root / "origin-verification.json").read_bytes()
    fake = SimpleNamespace(
        request_bytes=request_bytes,
        report={
            "items": [
                {
                    "program_evidence_binding": dict(bindings[0]),
                    "origin_class": "invented_origin",
                }
            ]
        },
        payloads=(
            InputEvidenceOriginPayload(
                workstream_id="ws-1",
                role="measurement",
                evidence_sha256=hashlib.sha256(evidence).hexdigest(),
                evidence_bytes=evidence,
                origin_declaration_bytes=declaration,
                origin_verification_decision_bytes=verification,
            ),
        ),
    )
    monkeypatch.setattr(
        module,
        "authenticate_input_evidence_origin_request",
        lambda **kwargs: fake,
    )
    with pytest.raises(InputEvidenceOriginPackError, match="unsupported origin_class"):
        publish_input_evidence_origin_pack(
            request_path=request,
            proposal_input_evidence_bindings=bindings,
            program_state=program_state,
            artifact_root=root,
            output_dir=tmp_path / "pack",
        )
