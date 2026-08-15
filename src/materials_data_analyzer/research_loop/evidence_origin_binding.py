"""Exact-byte provenance binding for explicit evidence-origin classification.

This primitive binds three things without claiming more than it proves:
1. exact evidence artifact bytes;
2. an exact origin-declaration artifact describing the asserted origin class;
3. an exact domain-verification decision that binds that declaration and evidence digest.

A successful binding authenticates the *recorded, domain-verified origin classification*
within this contract. It does not authenticate physical truth, institutional identity,
scientific result validity, independence, calibrated confidence, execution authority, or
positive scientific closeout. In particular, this primitive alone does not grant
empirical scientific authority to an inference.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .kernel import ResearchLoopError

EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION = "1.0"
EVIDENCE_ORIGIN_DECLARATION_SCHEMA_VERSION = "1.0"
EVIDENCE_ORIGIN_VERIFICATION_SCHEMA_VERSION = "1.0"
EVIDENCE_ORIGIN_VERIFICATION_SCOPE = "origin_classification_only"

_ORIGIN_CLASSES = {
    "empirical_measurement",
    "external_physical_experiment",
    "computational_output",
    "analysis_output",
}
_DECLARATION_KEYS = {
    "schema_version",
    "evidence_id",
    "evidence_artifact_sha256",
    "origin_class",
    "origin_statement",
    "limitations",
}
_VERIFICATION_KEYS = {
    "schema_version",
    "decision_id",
    "evidence_id",
    "evidence_artifact_sha256",
    "origin_declaration_sha256",
    "origin_class",
    "verification_scope",
    "verifier_id",
    "rationale",
    "limitations",
    "domain_verified_origin",
}


class EvidenceOriginBindingError(ResearchLoopError):
    """Raised when exact evidence-origin provenance cannot be authenticated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceOriginBindingError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceOriginBindingError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise EvidenceOriginBindingError(f"{field} root must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    keys = set(value)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing or unknown:
        raise EvidenceOriginBindingError(
            f"{field} must use the exact key set; unknown={unknown}, missing={missing}"
        )


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceOriginBindingError(f"{field} must be non-empty text")
    return value.strip()


def _strict_text(value: object, field: str) -> str:
    text = _text(value, field)
    if value != text:
        raise EvidenceOriginBindingError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return text


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise EvidenceOriginBindingError(
            f"{field} must be a lowercase 64-character SHA-256"
        )
    return text


def _origin_class(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if text not in _ORIGIN_CLASSES:
        raise EvidenceOriginBindingError(
            f"{field} must be one of: {', '.join(sorted(_ORIGIN_CLASSES))}"
        )
    return text


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise EvidenceOriginBindingError(f"{field} must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _text(item, f"{field}[{index}]")
        if text in result:
            raise EvidenceOriginBindingError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _validate_declaration(
    value: Mapping[str, Any], *, evidence_sha256: str
) -> dict[str, Any]:
    _exact_keys(value, _DECLARATION_KEYS, field="origin declaration")
    if value["schema_version"] != EVIDENCE_ORIGIN_DECLARATION_SCHEMA_VERSION:
        raise EvidenceOriginBindingError(
            f"origin declaration schema_version must be {EVIDENCE_ORIGIN_DECLARATION_SCHEMA_VERSION}"
        )
    declared_sha = _sha256_text(
        value["evidence_artifact_sha256"],
        "origin declaration evidence_artifact_sha256",
    )
    if declared_sha != evidence_sha256:
        raise EvidenceOriginBindingError(
            "origin declaration evidence_artifact_sha256 does not match exact evidence bytes"
        )
    return {
        "schema_version": EVIDENCE_ORIGIN_DECLARATION_SCHEMA_VERSION,
        "evidence_id": _strict_text(value["evidence_id"], "origin declaration evidence_id"),
        "evidence_artifact_sha256": declared_sha,
        "origin_class": _origin_class(value["origin_class"], "origin declaration origin_class"),
        "origin_statement": _text(
            value["origin_statement"], "origin declaration origin_statement"
        ),
        "limitations": _string_list(value["limitations"], "origin declaration limitations"),
    }


def _validate_verification(
    value: Mapping[str, Any],
    *,
    evidence_sha256: str,
    declaration_sha256: str,
    declaration: Mapping[str, Any],
) -> dict[str, Any]:
    _exact_keys(value, _VERIFICATION_KEYS, field="origin verification decision")
    if value["schema_version"] != EVIDENCE_ORIGIN_VERIFICATION_SCHEMA_VERSION:
        raise EvidenceOriginBindingError(
            f"origin verification schema_version must be {EVIDENCE_ORIGIN_VERIFICATION_SCHEMA_VERSION}"
        )
    if value["domain_verified_origin"] is not True:
        raise EvidenceOriginBindingError(
            "origin verification decision requires domain_verified_origin=true"
        )
    scope = _strict_text(
        value["verification_scope"], "origin verification verification_scope"
    )
    if scope != EVIDENCE_ORIGIN_VERIFICATION_SCOPE:
        raise EvidenceOriginBindingError(
            f"origin verification verification_scope must be {EVIDENCE_ORIGIN_VERIFICATION_SCOPE}"
        )
    evidence_id = _strict_text(
        value["evidence_id"], "origin verification evidence_id"
    )
    if evidence_id != declaration["evidence_id"]:
        raise EvidenceOriginBindingError(
            "origin verification evidence_id does not match declaration"
        )
    bound_evidence_sha = _sha256_text(
        value["evidence_artifact_sha256"],
        "origin verification evidence_artifact_sha256",
    )
    if bound_evidence_sha != evidence_sha256:
        raise EvidenceOriginBindingError(
            "origin verification evidence_artifact_sha256 does not match exact evidence bytes"
        )
    bound_declaration_sha = _sha256_text(
        value["origin_declaration_sha256"],
        "origin verification origin_declaration_sha256",
    )
    if bound_declaration_sha != declaration_sha256:
        raise EvidenceOriginBindingError(
            "origin verification origin_declaration_sha256 does not match exact declaration bytes"
        )
    origin_class = _origin_class(
        value["origin_class"], "origin verification origin_class"
    )
    if origin_class != declaration["origin_class"]:
        raise EvidenceOriginBindingError(
            "origin verification origin_class does not match declaration"
        )
    return {
        "schema_version": EVIDENCE_ORIGIN_VERIFICATION_SCHEMA_VERSION,
        "decision_id": _strict_text(
            value["decision_id"], "origin verification decision_id"
        ),
        "evidence_id": evidence_id,
        "evidence_artifact_sha256": bound_evidence_sha,
        "origin_declaration_sha256": bound_declaration_sha,
        "origin_class": origin_class,
        "verification_scope": scope,
        "verifier_id": _text(value["verifier_id"], "origin verification verifier_id"),
        "rationale": _text(value["rationale"], "origin verification rationale"),
        "limitations": _string_list(
            value["limitations"], "origin verification limitations"
        ),
        "domain_verified_origin": True,
    }


def authenticate_evidence_origin_binding(
    *,
    evidence_bytes: bytes,
    origin_declaration_bytes: bytes,
    origin_verification_decision_bytes: bytes,
) -> dict[str, Any]:
    """Authenticate exact evidence/declaration/verification identity.

    The result authenticates a checksum-bound origin-classification record only. It does
    not independently prove that an experiment physically occurred or that the verifier's
    free-text identity represents a credentialed institution/person.
    """
    evidence_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
    declaration_sha256 = hashlib.sha256(origin_declaration_bytes).hexdigest()
    verification_sha256 = hashlib.sha256(origin_verification_decision_bytes).hexdigest()

    declaration_raw = _json_object(
        origin_declaration_bytes, field="origin declaration"
    )
    declaration = _validate_declaration(
        declaration_raw, evidence_sha256=evidence_sha256
    )
    verification_raw = _json_object(
        origin_verification_decision_bytes, field="origin verification decision"
    )
    verification = _validate_verification(
        verification_raw,
        evidence_sha256=evidence_sha256,
        declaration_sha256=declaration_sha256,
        declaration=declaration,
    )

    return {
        "schema_version": EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION,
        "evidence_id": declaration["evidence_id"],
        "evidence_artifact_sha256": evidence_sha256,
        "origin_declaration_sha256": declaration_sha256,
        "origin_verification_decision_sha256": verification_sha256,
        "origin_class": declaration["origin_class"],
        "verification_decision_id": verification["decision_id"],
        "verification_scope": EVIDENCE_ORIGIN_VERIFICATION_SCOPE,
        "origin_classification_domain_verified": True,
        "physical_origin_truth_authenticated": False,
        "verifier_identity_or_credential_authenticated": False,
        "scientific_result_validity_authenticated": False,
        "support_independence_established": False,
        "empirical_authority_granted": False,
        "scientific_status_changed": False,
        "execution_authorized": False,
        "positive_closeout_granted": False,
    }


__all__ = [
    "EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION",
    "EVIDENCE_ORIGIN_DECLARATION_SCHEMA_VERSION",
    "EVIDENCE_ORIGIN_VERIFICATION_SCHEMA_VERSION",
    "EVIDENCE_ORIGIN_VERIFICATION_SCOPE",
    "EvidenceOriginBindingError",
    "authenticate_evidence_origin_binding",
]
