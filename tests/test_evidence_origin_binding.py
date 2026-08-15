from __future__ import annotations

import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.evidence_origin_binding import (
    EvidenceOriginBindingError,
    authenticate_evidence_origin_binding,
)


def _raw(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _declaration(evidence_sha: str, *, origin_class: str = "empirical_measurement") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "evidence_id": "evidence-1",
        "evidence_artifact_sha256": evidence_sha,
        "origin_class": origin_class,
        "origin_statement": "This artifact is declared to contain an empirical measurement record.",
        "limitations": ["Origin classification is bounded to this exact artifact."],
    }


def _verification(
    evidence_sha: str,
    declaration_sha: str,
    *,
    origin_class: str = "empirical_measurement",
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "decision_id": "origin-verification-1",
        "evidence_id": "evidence-1",
        "evidence_artifact_sha256": evidence_sha,
        "origin_declaration_sha256": declaration_sha,
        "origin_class": origin_class,
        "verification_scope": "origin_classification_only",
        "verifier_id": "bounded-origin-verifier",
        "rationale": "The exact declaration and artifact are coherent within classification scope.",
        "limitations": ["This does not authenticate institutional credentials or physical truth."],
        "domain_verified_origin": True,
    }


def _fixture() -> tuple[bytes, bytes, bytes]:
    evidence = b"temperature_K,magnetization\n300,1.25\n"
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    declaration = _raw(_declaration(evidence_sha))
    declaration_sha = hashlib.sha256(declaration).hexdigest()
    verification = _raw(_verification(evidence_sha, declaration_sha))
    return evidence, declaration, verification


def test_exact_origin_binding_authenticates_record_without_empirical_authority() -> None:
    evidence, declaration, verification = _fixture()
    result = authenticate_evidence_origin_binding(
        evidence_bytes=evidence,
        origin_declaration_bytes=declaration,
        origin_verification_decision_bytes=verification,
    )
    assert result["origin_classification_domain_verified"] is True
    assert result["origin_class"] == "empirical_measurement"
    assert result["evidence_artifact_sha256"] == hashlib.sha256(evidence).hexdigest()
    assert result["physical_origin_truth_authenticated"] is False
    assert result["verifier_identity_or_credential_authenticated"] is False
    assert result["scientific_result_validity_authenticated"] is False
    assert result["support_independence_established"] is False
    assert result["empirical_authority_granted"] is False
    assert result["scientific_status_changed"] is False
    assert result["execution_authorized"] is False
    assert result["positive_closeout_granted"] is False


def test_evidence_byte_drift_invalidates_origin_declaration() -> None:
    evidence, declaration, verification = _fixture()
    with pytest.raises(EvidenceOriginBindingError, match="does not match exact evidence bytes"):
        authenticate_evidence_origin_binding(
            evidence_bytes=evidence + b"tamper",
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=verification,
        )


def test_reserialized_declaration_invalidates_exact_verification_binding() -> None:
    evidence, declaration, verification = _fixture()
    value = json.loads(declaration)
    reserialized = json.dumps(value, separators=(",", ":")).encode("utf-8")
    assert reserialized != declaration
    with pytest.raises(EvidenceOriginBindingError, match="origin_declaration_sha256"):
        authenticate_evidence_origin_binding(
            evidence_bytes=evidence,
            origin_declaration_bytes=reserialized,
            origin_verification_decision_bytes=verification,
        )


def test_verifier_cannot_change_origin_class_relative_to_declaration() -> None:
    evidence = b"artifact"
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    declaration = _raw(_declaration(evidence_sha, origin_class="empirical_measurement"))
    verification = _raw(
        _verification(
            evidence_sha,
            hashlib.sha256(declaration).hexdigest(),
            origin_class="computational_output",
        )
    )
    with pytest.raises(EvidenceOriginBindingError, match="origin_class does not match"):
        authenticate_evidence_origin_binding(
            evidence_bytes=evidence,
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=verification,
        )


def test_false_domain_verified_origin_cannot_authenticate() -> None:
    evidence, declaration, verification = _fixture()
    value = json.loads(verification)
    value["domain_verified_origin"] = False
    with pytest.raises(EvidenceOriginBindingError, match="domain_verified_origin=true"):
        authenticate_evidence_origin_binding(
            evidence_bytes=evidence,
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=_raw(value),
        )


def test_unknown_authority_field_is_rejected() -> None:
    evidence, declaration, verification = _fixture()
    value = json.loads(verification)
    value["empirical_authority_granted"] = True
    with pytest.raises(EvidenceOriginBindingError, match="exact key set"):
        authenticate_evidence_origin_binding(
            evidence_bytes=evidence,
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=_raw(value),
        )


def test_duplicate_json_key_is_rejected() -> None:
    evidence = b"artifact"
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    declaration = (
        '{"schema_version":"1.0","evidence_id":"evidence-1",'
        '"evidence_id":"forged","evidence_artifact_sha256":"'
        + evidence_sha
        + '","origin_class":"empirical_measurement",'
        '"origin_statement":"record","limitations":[]}'
    ).encode("utf-8")
    declaration_sha = hashlib.sha256(declaration).hexdigest()
    verification = _raw(_verification(evidence_sha, declaration_sha))
    with pytest.raises(EvidenceOriginBindingError, match="duplicate JSON key"):
        authenticate_evidence_origin_binding(
            evidence_bytes=evidence,
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=verification,
        )


def test_wrong_verification_scope_is_rejected() -> None:
    evidence, declaration, verification = _fixture()
    value = json.loads(verification)
    value["verification_scope"] = "scientific_truth"
    with pytest.raises(EvidenceOriginBindingError, match="origin_classification_only"):
        authenticate_evidence_origin_binding(
            evidence_bytes=evidence,
            origin_declaration_bytes=declaration,
            origin_verification_decision_bytes=_raw(value),
        )
