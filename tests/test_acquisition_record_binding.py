from __future__ import annotations

import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.acquisition_record_binding import (
    AcquisitionRecordBindingError,
    authenticate_acquisition_record_binding,
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _fixture() -> tuple[bytes, bytes, bytes]:
    evidence = b'{"material_id":"mp-1","energy_above_hull":0.0}\n'
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    manifest = {
        "manifest_schema_version": "1.0",
        "dataset_name": "Fe-Si Materials Project acquisition",
        "source_system": "Materials Project",
        "endpoint": "materials.summary.search",
        "materials_project_database_version": "2026.08.01",
        "execution_status": "success",
        "preflight_status": "passed",
        "network_called": True,
        "raw_sha256": evidence_sha,
        "raw_row_count": 1,
    }
    manifest_bytes = _json_bytes(manifest)
    declaration = {
        "schema_version": "1.0",
        "acquisition_id": "mp-fe-si-v1.3-20260815",
        "evidence_artifact_sha256": evidence_sha,
        "acquisition_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "evidence_role": "raw_source_records",
        "manifest_evidence_sha256_pointer": "/raw_sha256",
        "manifest_claim_bindings": [
            {
                "claim": "source_system",
                "json_pointer": "/source_system",
                "expected_value": "Materials Project",
            },
            {
                "claim": "source_version",
                "json_pointer": "/materials_project_database_version",
                "expected_value": "2026.08.01",
            },
            {
                "claim": "retrieval_endpoint",
                "json_pointer": "/endpoint",
                "expected_value": "materials.summary.search",
            },
            {
                "claim": "retrieval_status",
                "json_pointer": "/execution_status",
                "expected_value": "success",
            },
            {
                "claim": "network_performed",
                "json_pointer": "/network_called",
                "expected_value": True,
            },
            {
                "claim": "preflight_status",
                "json_pointer": "/preflight_status",
                "expected_value": "passed",
            },
            {
                "claim": "row_count",
                "json_pointer": "/raw_row_count",
                "expected_value": 1,
            },
        ],
        "limitations": [
            "The source-system label is a recorded manifest value, not a cryptographic provider identity."
        ],
    }
    return evidence, manifest_bytes, _json_bytes(declaration)


def test_authenticates_exact_recorded_acquisition_provenance_only() -> None:
    evidence, manifest, declaration = _fixture()
    report = authenticate_acquisition_record_binding(
        evidence_bytes=evidence,
        acquisition_manifest_bytes=manifest,
        acquisition_declaration_bytes=declaration,
    )
    assert report["recorded_acquisition_provenance_authenticated"] is True
    assert report["recorded_source_system"] == "Materials Project"
    assert report["recorded_source_version"] == "2026.08.01"
    assert report["recorded_retrieval_status"] == "success"
    assert report["recorded_network_performed"] is True
    assert report["source_identity_or_credential_authenticated"] is False
    assert report["transport_peer_identity_authenticated_by_this_contract"] is False
    assert report["physical_origin_truth_authenticated"] is False
    assert report["support_independence_established"] is False
    assert report["empirical_authority_granted"] is False
    assert report["scientific_status_changed"] is False
    assert report["execution_authorized"] is False
    assert report["positive_closeout_granted"] is False


def test_rejects_evidence_byte_drift() -> None:
    evidence, manifest, declaration = _fixture()
    with pytest.raises(AcquisitionRecordBindingError, match="evidence SHA"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence + b"drift",
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
        )


def test_rejects_manifest_byte_drift() -> None:
    evidence, manifest, declaration = _fixture()
    with pytest.raises(AcquisitionRecordBindingError, match="manifest SHA"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest + b" ",
            acquisition_declaration_bytes=declaration,
        )


def test_rejects_manifest_rewrite_even_when_declaration_manifest_sha_is_updated() -> None:
    evidence, manifest_bytes, declaration_bytes = _fixture()
    manifest = json.loads(manifest_bytes)
    manifest["source_system"] = "Attacker Source"
    rewritten_manifest = _json_bytes(manifest)
    declaration = json.loads(declaration_bytes)
    declaration["acquisition_manifest_sha256"] = hashlib.sha256(rewritten_manifest).hexdigest()
    rewritten_declaration = _json_bytes(declaration)
    with pytest.raises(AcquisitionRecordBindingError, match="source_system"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=rewritten_manifest,
            acquisition_declaration_bytes=rewritten_declaration,
        )


def test_rejects_manifest_evidence_pointer_substitution() -> None:
    evidence, manifest_bytes, declaration_bytes = _fixture()
    manifest = json.loads(manifest_bytes)
    manifest["other_sha"] = manifest["raw_sha256"]
    rewritten_manifest = _json_bytes(manifest)
    declaration = json.loads(declaration_bytes)
    declaration["acquisition_manifest_sha256"] = hashlib.sha256(rewritten_manifest).hexdigest()
    declaration["manifest_evidence_sha256_pointer"] = "/missing_sha"
    with pytest.raises(AcquisitionRecordBindingError, match="does not resolve"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=rewritten_manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_rejects_duplicate_claim_names() -> None:
    evidence, manifest, declaration_bytes = _fixture()
    declaration = json.loads(declaration_bytes)
    declaration["manifest_claim_bindings"].append(
        {
            "claim": "source_system",
            "json_pointer": "/dataset_name",
            "expected_value": "Fe-Si Materials Project acquisition",
        }
    )
    with pytest.raises(AcquisitionRecordBindingError, match="claim names must be unique"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_rejects_duplicate_claim_pointers() -> None:
    evidence, manifest, declaration_bytes = _fixture()
    declaration = json.loads(declaration_bytes)
    declaration["manifest_claim_bindings"].append(
        {
            "claim": "source_system_alias",
            "json_pointer": "/source_system",
            "expected_value": "Materials Project",
        }
    )
    with pytest.raises(AcquisitionRecordBindingError, match="JSON pointers must be unique"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_rejects_missing_required_recorded_provenance_claim() -> None:
    evidence, manifest, declaration_bytes = _fixture()
    declaration = json.loads(declaration_bytes)
    declaration["manifest_claim_bindings"] = [
        item
        for item in declaration["manifest_claim_bindings"]
        if item["claim"] != "source_version"
    ]
    with pytest.raises(AcquisitionRecordBindingError, match="source_version"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_rejects_boolean_integer_type_confusion() -> None:
    evidence, manifest_bytes, declaration_bytes = _fixture()
    manifest = json.loads(manifest_bytes)
    manifest["network_called"] = 1
    rewritten_manifest = _json_bytes(manifest)
    declaration = json.loads(declaration_bytes)
    declaration["acquisition_manifest_sha256"] = hashlib.sha256(rewritten_manifest).hexdigest()
    with pytest.raises(AcquisitionRecordBindingError, match="network_performed"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=rewritten_manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_rejects_float_claim_values() -> None:
    evidence, manifest, declaration_bytes = _fixture()
    declaration = json.loads(declaration_bytes)
    declaration["manifest_claim_bindings"].append(
        {
            "claim": "float_claim",
            "json_pointer": "/raw_row_count",
            "expected_value": 1.0,
        }
    )
    with pytest.raises(AcquisitionRecordBindingError, match="string, integer, boolean, or null"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_supports_rfc6901_escaped_object_keys() -> None:
    evidence, manifest_bytes, declaration_bytes = _fixture()
    manifest = json.loads(manifest_bytes)
    manifest["source/info"] = {"version~id": "v-special"}
    rewritten_manifest = _json_bytes(manifest)
    declaration = json.loads(declaration_bytes)
    declaration["acquisition_manifest_sha256"] = hashlib.sha256(rewritten_manifest).hexdigest()
    declaration["manifest_claim_bindings"].append(
        {
            "claim": "escaped_pointer",
            "json_pointer": "/source~1info/version~0id",
            "expected_value": "v-special",
        }
    )
    report = authenticate_acquisition_record_binding(
        evidence_bytes=evidence,
        acquisition_manifest_bytes=rewritten_manifest,
        acquisition_declaration_bytes=_json_bytes(declaration),
    )
    assert any(
        item["claim"] == "escaped_pointer"
        for item in report["authenticated_manifest_claim_bindings"]
    )


def test_rejects_duplicate_json_keys_in_manifest() -> None:
    evidence, _manifest, declaration_bytes = _fixture()
    manifest = (
        b'{"source_system":"Materials Project","source_system":"Other",'
        b'"materials_project_database_version":"2026.08.01",'
        b'"endpoint":"materials.summary.search","execution_status":"success",'
        b'"preflight_status":"passed","network_called":true,"raw_row_count":1,'
        + b'"raw_sha256":"'
        + hashlib.sha256(evidence).hexdigest().encode()
        + b'"}\n'
    )
    declaration = json.loads(declaration_bytes)
    declaration["acquisition_manifest_sha256"] = hashlib.sha256(manifest).hexdigest()
    with pytest.raises(AcquisitionRecordBindingError, match="duplicate JSON key"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )



@pytest.mark.parametrize(
    "claim_name,bad_value",
    [
        ("source_system", 1),
        ("source_version", True),
        ("retrieval_endpoint", None),
        ("retrieval_status", 1),
    ],
)
def test_rejects_non_text_required_source_claims(
    claim_name: str,
    bad_value: object,
) -> None:
    evidence, manifest_bytes, declaration_bytes = _fixture()
    manifest = json.loads(manifest_bytes)
    declaration = json.loads(declaration_bytes)
    target = next(
        item
        for item in declaration["manifest_claim_bindings"]
        if item["claim"] == claim_name
    )
    target["expected_value"] = bad_value
    manifest_pointer_key = target["json_pointer"].removeprefix("/")
    manifest[manifest_pointer_key] = bad_value
    rewritten_manifest = _json_bytes(manifest)
    declaration["acquisition_manifest_sha256"] = hashlib.sha256(rewritten_manifest).hexdigest()
    with pytest.raises(AcquisitionRecordBindingError, match="must declare a text value"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=rewritten_manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_rejects_non_boolean_required_network_claim() -> None:
    evidence, manifest_bytes, declaration_bytes = _fixture()
    manifest = json.loads(manifest_bytes)
    declaration = json.loads(declaration_bytes)
    target = next(
        item
        for item in declaration["manifest_claim_bindings"]
        if item["claim"] == "network_performed"
    )
    target["expected_value"] = 1
    manifest["network_called"] = 1
    rewritten_manifest = _json_bytes(manifest)
    declaration["acquisition_manifest_sha256"] = hashlib.sha256(rewritten_manifest).hexdigest()
    with pytest.raises(AcquisitionRecordBindingError, match="must declare a boolean value"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=rewritten_manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_requires_explicit_nonempty_limitations() -> None:
    evidence, manifest, declaration_bytes = _fixture()
    declaration = json.loads(declaration_bytes)
    declaration["limitations"] = []
    with pytest.raises(AcquisitionRecordBindingError, match="limitations must be non-empty"):
        authenticate_acquisition_record_binding(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=_json_bytes(declaration),
        )


def test_reports_historical_and_authorship_boundaries() -> None:
    evidence, manifest, declaration = _fixture()
    report = authenticate_acquisition_record_binding(
        evidence_bytes=evidence,
        acquisition_manifest_bytes=manifest,
        acquisition_declaration_bytes=declaration,
    )
    assert report["historical_acquisition_event_authenticated"] is False
    assert report["acquisition_manifest_authorship_authenticated"] is False
