from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.input_evidence_origin_pack import (
    publish_input_evidence_origin_pack,
)
from materials_data_analyzer.research_loop.input_evidence_origin_pack_consumer import (
    InputEvidenceOriginPackConsumerError,
    authenticate_input_evidence_origin_pack,
)


def _json_bytes(value: dict[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _source_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, object], list[dict[str, str]]]:
    root = tmp_path / "artifacts"
    root.mkdir()
    evidence = b"measurement-bytes\x00\x02"
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    (root / "evidence.bin").write_bytes(evidence)

    declaration = _json_bytes(
        {
            "schema_version": "1.0",
            "evidence_id": "ev-1",
            "evidence_artifact_sha256": evidence_sha,
            "origin_class": "empirical_measurement",
            "origin_statement": "Exact bytes are classified as measurement output.",
            "limitations": ["Classification does not establish physical truth."],
        }
    )
    (root / "origin-declaration.json").write_bytes(declaration)
    verification = _json_bytes(
        {
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
    )
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
    request = _json_bytes(
        {
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
    )
    request_path = root / "request.json"
    request_path.write_bytes(request)
    return root, request_path, program_state, [binding]


def _pack(tmp_path: Path) -> Path:
    root, request, program_state, bindings = _source_fixture(tmp_path)
    output = tmp_path / "pack"
    publish_input_evidence_origin_pack(
        request_path=request,
        proposal_input_evidence_bindings=bindings,
        program_state=program_state,
        artifact_root=root,
        output_dir=output,
    )
    return output


def _manifest(pack: Path) -> dict[str, object]:
    return json.loads((pack / "input_evidence_origin_pack_manifest.json").read_bytes())


def _write_manifest(pack: Path, value: dict[str, object]) -> None:
    (pack / "input_evidence_origin_pack_manifest.json").write_bytes(
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    )


def test_independently_reauthenticates_exact_pack_origin_bytes(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    report = authenticate_input_evidence_origin_pack(pack)
    assert report["schema_version"] == "1.0"
    assert report["all_items_exact_evidence_origin_provenance_authenticated"] is True
    assert report["request_identity_set_authenticated"] is True
    assert report["manifest_origin_class_used_as_authority_without_reauthentication"] is False
    assert report["items"] == [
        {
            "program_evidence_binding": {
                "workstream_id": "ws-1",
                "role": "measurement",
                "sha256": hashlib.sha256(b"measurement-bytes\x00\x02").hexdigest(),
            },
            "origin_class": "empirical_measurement",
            "evidence_id": "ev-1",
            "origin_verification_decision_id": "origin-v-1",
            "origin_classification_domain_verified": True,
            "exact_evidence_origin_provenance_authenticated": True,
        }
    ]


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
def test_consumer_never_overclaims_authority(tmp_path: Path, field: str) -> None:
    report = authenticate_input_evidence_origin_pack(_pack(tmp_path))
    assert report[field] is False


def test_rejects_manifest_origin_class_substitution_even_if_manifest_is_rewritten(
    tmp_path: Path,
) -> None:
    pack = _pack(tmp_path)
    manifest = _manifest(pack)
    manifest["items"][0]["origin_class"] = "analysis_output"
    _write_manifest(pack, manifest)
    with pytest.raises(InputEvidenceOriginPackConsumerError, match="origin_class does not match"):
        authenticate_input_evidence_origin_pack(pack)


def test_rejects_evidence_snapshot_drift(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    (pack / "items/0000/evidence.bin").write_bytes(b"drift")
    with pytest.raises(InputEvidenceOriginPackConsumerError, match="checksum"):
        authenticate_input_evidence_origin_pack(pack)


def test_rejects_declaration_substitution_even_if_manifest_binding_is_updated(
    tmp_path: Path,
) -> None:
    pack = _pack(tmp_path)
    declaration_path = pack / "items/0000/origin_declaration.json"
    declaration = json.loads(declaration_path.read_bytes())
    declaration["origin_class"] = "analysis_output"
    raw = _json_bytes(declaration)
    declaration_path.write_bytes(raw)
    manifest = _manifest(pack)
    manifest["items"][0]["origin_declaration_artifact"]["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["items"][0]["origin_declaration_artifact"]["size_bytes"] = len(raw)
    _write_manifest(pack, manifest)
    with pytest.raises(InputEvidenceOriginPackConsumerError, match="independent reauthentication"):
        authenticate_input_evidence_origin_pack(pack)


def test_rejects_request_identity_drift_even_if_request_binding_is_updated(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    request_path = pack / "request.json"
    request = json.loads(request_path.read_bytes())
    request["items"][0]["role"] = "other-role"
    raw = _json_bytes(request)
    request_path.write_bytes(raw)
    manifest = _manifest(pack)
    manifest["request_artifact"]["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["request_artifact"]["size_bytes"] = len(raw)
    _write_manifest(pack, manifest)
    with pytest.raises(InputEvidenceOriginPackConsumerError, match="do not exactly match"):
        authenticate_input_evidence_origin_pack(pack)


def test_rejects_manifest_program_identity_substitution(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    manifest = _manifest(pack)
    manifest["items"][0]["program_evidence_binding"]["role"] = "other-role"
    _write_manifest(pack, manifest)
    with pytest.raises(InputEvidenceOriginPackConsumerError, match="request snapshot identities"):
        authenticate_input_evidence_origin_pack(pack)


def test_rejects_manifest_authority_escalation(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    manifest = _manifest(pack)
    manifest["empirical_authority_granted"] = True
    _write_manifest(pack, manifest)
    with pytest.raises(InputEvidenceOriginPackConsumerError, match="non-authority boundary"):
        authenticate_input_evidence_origin_pack(pack)


def test_rejects_one_path_reused_for_multiple_origin_roles(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    manifest = _manifest(pack)
    evidence = manifest["items"][0]["evidence_artifact"]
    declaration = manifest["items"][0]["origin_declaration_artifact"]
    declaration["path"] = evidence["path"]
    declaration["sha256"] = evidence["sha256"]
    declaration["size_bytes"] = evidence["size_bytes"]
    _write_manifest(pack, manifest)
    with pytest.raises(InputEvidenceOriginPackConsumerError, match="reuses one snapshot path"):
        authenticate_input_evidence_origin_pack(pack)


def test_rejects_symlinked_snapshot(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    real = pack / "items/0000/evidence.bin"
    target = pack / "items/0000/evidence-real.bin"
    real.rename(target)
    try:
        os.symlink(target, real)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available")
    with pytest.raises(InputEvidenceOriginPackConsumerError, match="symlink"):
        authenticate_input_evidence_origin_pack(pack)


@pytest.mark.parametrize(
    "bad_path",
    ["../evidence.bin", "file:stream", "NUL.txt", "trailing.", "dir\\file"],
)
def test_rejects_nonportable_pack_paths(tmp_path: Path, bad_path: str) -> None:
    pack = _pack(tmp_path)
    manifest = _manifest(pack)
    manifest["items"][0]["evidence_artifact"]["path"] = bad_path
    _write_manifest(pack, manifest)
    with pytest.raises(InputEvidenceOriginPackConsumerError):
        authenticate_input_evidence_origin_pack(pack)
