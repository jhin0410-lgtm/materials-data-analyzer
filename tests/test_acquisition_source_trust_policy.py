from __future__ import annotations

import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.acquisition_source_trust_policy import (
    AcquisitionSourceTrustPolicyError,
    qualify_acquisition_record_under_pinned_policy,
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _fixture() -> tuple[bytes, bytes, bytes, bytes, str]:
    evidence = b"provider-response-bytes\x00\x03"
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    manifest = {
        "artifact": {"sha256": evidence_sha},
        "source": {
            "system": "Materials Project",
            "version": "2026.08.01",
            "endpoint": "materials.summary.search",
        },
        "retrieval": {"status": "success", "network_performed": True},
    }
    manifest_bytes = _json_bytes(manifest)
    declaration = {
        "schema_version": "1.0",
        "acquisition_id": "mp-acq-1",
        "evidence_artifact_sha256": evidence_sha,
        "acquisition_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "evidence_role": "external_structure_record",
        "manifest_evidence_sha256_pointer": "/artifact/sha256",
        "manifest_claim_bindings": [
            {
                "claim": "source_system",
                "json_pointer": "/source/system",
                "expected_value": "Materials Project",
            },
            {
                "claim": "source_version",
                "json_pointer": "/source/version",
                "expected_value": "2026.08.01",
            },
            {
                "claim": "retrieval_endpoint",
                "json_pointer": "/source/endpoint",
                "expected_value": "materials.summary.search",
            },
            {
                "claim": "retrieval_status",
                "json_pointer": "/retrieval/status",
                "expected_value": "success",
            },
            {
                "claim": "network_performed",
                "json_pointer": "/retrieval/network_performed",
                "expected_value": True,
            },
        ],
        "limitations": [
            "Manifest records are local provenance, not provider credentials."
        ],
    }
    declaration_bytes = _json_bytes(declaration)
    policy = {
        "schema_version": "1.0",
        "policy_id": "materials-project-structure-records-v1",
        "rules": [
            {
                "rule_id": "mp-summary-success",
                "evidence_role": "external_structure_record",
                "required_manifest_claims": [
                    {
                        "claim": "source_system",
                        "json_pointer": "/source/system",
                        "allowed_values": ["Materials Project"],
                    },
                    {
                        "claim": "source_version",
                        "json_pointer": "/source/version",
                        "allowed_values": ["2026.08.01"],
                    },
                    {
                        "claim": "retrieval_endpoint",
                        "json_pointer": "/source/endpoint",
                        "allowed_values": ["materials.summary.search"],
                    },
                    {
                        "claim": "retrieval_status",
                        "json_pointer": "/retrieval/status",
                        "allowed_values": ["success"],
                    },
                    {
                        "claim": "network_performed",
                        "json_pointer": "/retrieval/network_performed",
                        "allowed_values": [True],
                    },
                ],
            }
        ],
        "limitations": [
            "Local policy qualification is not external provider authentication."
        ],
    }
    policy_bytes = _json_bytes(policy)
    return (
        evidence,
        manifest_bytes,
        declaration_bytes,
        policy_bytes,
        hashlib.sha256(policy_bytes).hexdigest(),
    )


def _qualify() -> dict[str, object]:
    evidence, manifest, declaration, policy, policy_sha = _fixture()
    return qualify_acquisition_record_under_pinned_policy(
        evidence_bytes=evidence,
        acquisition_manifest_bytes=manifest,
        acquisition_declaration_bytes=declaration,
        source_trust_policy_bytes=policy,
        expected_source_trust_policy_sha256=policy_sha,
    )


def test_qualifies_exact_record_under_supplied_policy_pin_without_external_authority() -> None:
    report = _qualify()
    assert report["schema_version"] == "1.0"
    assert report["matched_rule_id"] == "mp-summary-success"
    assert report["recorded_source_system"] == "Materials Project"
    assert report["local_record_reliance_qualified_under_supplied_pin"] is True
    assert report["expected_policy_pin_provenance_authenticated_by_this_contract"] is False
    assert report["external_source_identity_authenticated"] is False
    assert report["external_source_credentials_authenticated"] is False
    assert report["support_independence_established"] is False
    assert report["empirical_authority_granted"] is False
    assert report["execution_authorized"] is False
    assert report["positive_closeout_granted"] is False


def test_rejects_policy_byte_drift_against_supplied_pin() -> None:
    evidence, manifest, declaration, policy, policy_sha = _fixture()
    with pytest.raises(AcquisitionSourceTrustPolicyError, match="do not match"):
        qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy + b" ",
            expected_source_trust_policy_sha256=policy_sha,
        )


def test_rejects_noncanonical_supplied_policy_sha() -> None:
    evidence, manifest, declaration, policy, policy_sha = _fixture()
    with pytest.raises(AcquisitionSourceTrustPolicyError, match="lowercase SHA-256"):
        qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
            expected_source_trust_policy_sha256=policy_sha.upper(),
        )


def test_reauthenticates_acquisition_record_instead_of_accepting_labels() -> None:
    evidence, manifest, declaration, policy, policy_sha = _fixture()
    changed = json.loads(manifest)
    changed["source"]["system"] = "Materials Project mirror"
    changed_bytes = _json_bytes(changed)
    with pytest.raises(AcquisitionSourceTrustPolicyError, match="provenance reauthentication"):
        qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=changed_bytes,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
            expected_source_trust_policy_sha256=policy_sha,
        )


def test_rejects_policy_claim_pointer_substitution() -> None:
    evidence, manifest, declaration, policy, _ = _fixture()
    obj = json.loads(policy)
    obj["rules"][0]["required_manifest_claims"][0]["json_pointer"] = "/source/version"
    mutated = _json_bytes(obj)
    with pytest.raises(
        AcquisitionSourceTrustPolicyError,
        match="(JSON pointers must be unique|does not satisfy any)",
    ):
        qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=mutated,
            expected_source_trust_policy_sha256=hashlib.sha256(mutated).hexdigest(),
        )


def test_rejects_policy_value_substitution() -> None:
    evidence, manifest, declaration, policy, _ = _fixture()
    obj = json.loads(policy)
    obj["rules"][0]["required_manifest_claims"][1]["allowed_values"] = ["2025.01.01"]
    mutated = _json_bytes(obj)
    with pytest.raises(AcquisitionSourceTrustPolicyError, match="does not satisfy any"):
        qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=mutated,
            expected_source_trust_policy_sha256=hashlib.sha256(mutated).hexdigest(),
        )


def test_bool_integer_substitution_does_not_match() -> None:
    evidence, manifest, declaration, policy, _ = _fixture()
    obj = json.loads(policy)
    obj["rules"][0]["required_manifest_claims"][4]["allowed_values"] = [1]
    mutated = _json_bytes(obj)
    with pytest.raises(AcquisitionSourceTrustPolicyError, match="does not satisfy any"):
        qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=mutated,
            expected_source_trust_policy_sha256=hashlib.sha256(mutated).hexdigest(),
        )


def test_rule_must_pin_evidence_role() -> None:
    evidence, manifest, declaration, policy, _ = _fixture()
    obj = json.loads(policy)
    obj["rules"][0]["evidence_role"] = "other-role"
    mutated = _json_bytes(obj)
    with pytest.raises(AcquisitionSourceTrustPolicyError, match="does not satisfy any"):
        qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=mutated,
            expected_source_trust_policy_sha256=hashlib.sha256(mutated).hexdigest(),
        )


def test_rule_must_constrain_all_base_recorded_claims() -> None:
    evidence, manifest, declaration, policy, _ = _fixture()
    obj = json.loads(policy)
    obj["rules"][0]["required_manifest_claims"] = obj["rules"][0][
        "required_manifest_claims"
    ][:-1]
    mutated = _json_bytes(obj)
    with pytest.raises(AcquisitionSourceTrustPolicyError, match="missing=.*network_performed"):
        qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=mutated,
            expected_source_trust_policy_sha256=hashlib.sha256(mutated).hexdigest(),
        )


def test_ambiguous_matching_rules_fail_closed() -> None:
    evidence, manifest, declaration, policy, _ = _fixture()
    obj = json.loads(policy)
    second = json.loads(json.dumps(obj["rules"][0]))
    second["rule_id"] = "mp-summary-success-copy"
    obj["rules"].append(second)
    mutated = _json_bytes(obj)
    with pytest.raises(AcquisitionSourceTrustPolicyError, match="ambiguously"):
        qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=mutated,
            expected_source_trust_policy_sha256=hashlib.sha256(mutated).hexdigest(),
        )


def test_duplicate_typed_allowed_values_fail_closed() -> None:
    evidence, manifest, declaration, policy, _ = _fixture()
    obj = json.loads(policy)
    obj["rules"][0]["required_manifest_claims"][0]["allowed_values"] = [
        "Materials Project",
        "Materials Project",
    ]
    mutated = _json_bytes(obj)
    with pytest.raises(AcquisitionSourceTrustPolicyError, match="duplicate typed values"):
        qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=mutated,
            expected_source_trust_policy_sha256=hashlib.sha256(mutated).hexdigest(),
        )


def test_duplicate_json_keys_in_policy_fail_closed() -> None:
    evidence, manifest, declaration, _, _ = _fixture()
    duplicate = (
        b'{"schema_version":"1.0","schema_version":"1.0","policy_id":"x",'
        b'"rules":[],"limitations":["x"]}'
    )
    with pytest.raises(AcquisitionSourceTrustPolicyError, match="duplicate JSON key"):
        qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=duplicate,
            expected_source_trust_policy_sha256=hashlib.sha256(duplicate).hexdigest(),
        )
