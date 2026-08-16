"""Qualify exact acquisition records under an externally supplied pinned local policy.

This layer intentionally does not authenticate where the expected policy SHA came from.
It re-authenticates exact acquisition-record provenance, requires exact policy bytes to
match that supplied pin, and evaluates a narrow local reliance rule. External provider
identity, independence, empirical scientific authority, execution, and closeout remain
out of scope.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .acquisition_record_binding import (
    AcquisitionRecordBindingError,
    authenticate_acquisition_record_binding,
)
from .kernel import ResearchLoopError

ACQUISITION_SOURCE_TRUST_POLICY_SCHEMA_VERSION = "1.0"
ACQUISITION_SOURCE_TRUST_QUALIFICATION_SCHEMA_VERSION = "1.0"

_POLICY_KEYS = {"schema_version", "policy_id", "rules", "limitations"}
_RULE_KEYS = {"rule_id", "evidence_role", "required_manifest_claims"}
_REQUIRED_CLAIM_KEYS = {"claim", "json_pointer", "allowed_values"}
_BASE_RECORDED_CLAIMS = {
    "source_system",
    "source_version",
    "retrieval_endpoint",
    "retrieval_status",
    "network_performed",
}


class AcquisitionSourceTrustPolicyError(ResearchLoopError):
    """Raised when a pinned local acquisition-reliance policy cannot be qualified."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AcquisitionSourceTrustPolicyError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcquisitionSourceTrustPolicyError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise AcquisitionSourceTrustPolicyError(f"{field} root must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    keys = set(value)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing or unknown:
        raise AcquisitionSourceTrustPolicyError(
            f"{field} must use the exact key set; unknown={unknown}, missing={missing}"
        )


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AcquisitionSourceTrustPolicyError(f"{field} must be non-empty text")
    if value != value.strip():
        raise AcquisitionSourceTrustPolicyError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise AcquisitionSourceTrustPolicyError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return text


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise AcquisitionSourceTrustPolicyError(f"{field} must be a non-empty list")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _strict_text(item, f"{field}[{index}]")
        if text in result:
            raise AcquisitionSourceTrustPolicyError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _scalar(value: object, field: str) -> str | int | bool | None:
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str):
            return _strict_text(value, field)
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise AcquisitionSourceTrustPolicyError(
        f"{field} must be a JSON string, integer, boolean, or null"
    )


def _same_scalar(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _allowed_values(value: object, field: str) -> list[str | int | bool | None]:
    if not isinstance(value, list) or not value:
        raise AcquisitionSourceTrustPolicyError(f"{field} must be a non-empty list")
    result: list[str | int | bool | None] = []
    for index, item in enumerate(value):
        scalar = _scalar(item, f"{field}[{index}]")
        if any(_same_scalar(scalar, existing) for existing in result):
            raise AcquisitionSourceTrustPolicyError(
                f"{field} must not contain duplicate typed values"
            )
        result.append(scalar)
    return result


def _normalize_rule(value: object, index: int) -> dict[str, Any]:
    field = f"source trust policy rules[{index}]"
    if not isinstance(value, Mapping):
        raise AcquisitionSourceTrustPolicyError(f"{field} must be an object")
    _exact_keys(value, _RULE_KEYS, field=field)
    rule_id = _strict_text(value["rule_id"], f"{field}.rule_id")
    evidence_role = _strict_text(value["evidence_role"], f"{field}.evidence_role")
    raw_claims = value["required_manifest_claims"]
    if not isinstance(raw_claims, list) or not raw_claims:
        raise AcquisitionSourceTrustPolicyError(
            f"{field}.required_manifest_claims must be a non-empty list"
        )
    claims: list[dict[str, Any]] = []
    names: set[str] = set()
    pointers: set[str] = set()
    for claim_index, raw_claim in enumerate(raw_claims):
        claim_field = f"{field}.required_manifest_claims[{claim_index}]"
        if not isinstance(raw_claim, Mapping):
            raise AcquisitionSourceTrustPolicyError(f"{claim_field} must be an object")
        _exact_keys(raw_claim, _REQUIRED_CLAIM_KEYS, field=claim_field)
        claim = _strict_text(raw_claim["claim"], f"{claim_field}.claim")
        pointer = _strict_text(raw_claim["json_pointer"], f"{claim_field}.json_pointer")
        if not pointer.startswith("/") or "//" in pointer:
            raise AcquisitionSourceTrustPolicyError(
                f"{claim_field}.json_pointer must be a non-root explicit JSON pointer"
            )
        allowed = _allowed_values(raw_claim["allowed_values"], f"{claim_field}.allowed_values")
        if claim in names:
            raise AcquisitionSourceTrustPolicyError(
                f"{field}.required_manifest_claims claim names must be unique"
            )
        if pointer in pointers:
            raise AcquisitionSourceTrustPolicyError(
                f"{field}.required_manifest_claims JSON pointers must be unique"
            )
        names.add(claim)
        pointers.add(pointer)
        claims.append(
            {"claim": claim, "json_pointer": pointer, "allowed_values": allowed}
        )
    missing = sorted(_BASE_RECORDED_CLAIMS - names)
    if missing:
        raise AcquisitionSourceTrustPolicyError(
            f"{field} must constrain every base recorded-provenance claim; missing={missing}"
        )
    return {
        "rule_id": rule_id,
        "evidence_role": evidence_role,
        "required_manifest_claims": claims,
    }


def _normalize_policy(raw: bytes) -> dict[str, Any]:
    policy = _json_object(raw, field="acquisition source trust policy")
    _exact_keys(policy, _POLICY_KEYS, field="acquisition source trust policy")
    if policy["schema_version"] != ACQUISITION_SOURCE_TRUST_POLICY_SCHEMA_VERSION:
        raise AcquisitionSourceTrustPolicyError("unsupported source trust policy schema_version")
    policy_id = _strict_text(policy["policy_id"], "source trust policy policy_id")
    raw_rules = policy["rules"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise AcquisitionSourceTrustPolicyError("source trust policy rules must be non-empty")
    rules = [_normalize_rule(value, index) for index, value in enumerate(raw_rules)]
    rule_ids = [rule["rule_id"] for rule in rules]
    if len(set(rule_ids)) != len(rule_ids):
        raise AcquisitionSourceTrustPolicyError("source trust policy rule_id values must be unique")
    limitations = _string_list(policy["limitations"], "source trust policy limitations")
    return {
        "schema_version": ACQUISITION_SOURCE_TRUST_POLICY_SCHEMA_VERSION,
        "policy_id": policy_id,
        "rules": rules,
        "limitations": limitations,
    }


def qualify_acquisition_record_under_pinned_policy(
    *,
    evidence_bytes: bytes,
    acquisition_manifest_bytes: bytes,
    acquisition_declaration_bytes: bytes,
    source_trust_policy_bytes: bytes,
    expected_source_trust_policy_sha256: str,
) -> dict[str, Any]:
    """Re-authenticate an acquisition record and evaluate it under exact pinned policy bytes."""
    expected_policy_sha = _sha256_text(
        expected_source_trust_policy_sha256,
        "expected_source_trust_policy_sha256",
    )
    actual_policy_sha = hashlib.sha256(source_trust_policy_bytes).hexdigest()
    if actual_policy_sha != expected_policy_sha:
        raise AcquisitionSourceTrustPolicyError(
            "source trust policy bytes do not match the supplied expected policy SHA"
        )
    policy = _normalize_policy(source_trust_policy_bytes)
    try:
        acquisition = authenticate_acquisition_record_binding(
            evidence_bytes=evidence_bytes,
            acquisition_manifest_bytes=acquisition_manifest_bytes,
            acquisition_declaration_bytes=acquisition_declaration_bytes,
        )
    except AcquisitionRecordBindingError as exc:
        raise AcquisitionSourceTrustPolicyError(
            "acquisition record failed exact provenance reauthentication"
        ) from exc

    claim_bindings = acquisition.get("authenticated_manifest_claim_bindings")
    if not isinstance(claim_bindings, list):
        raise AcquisitionSourceTrustPolicyError(
            "acquisition binding did not return authenticated manifest claim bindings"
        )
    by_claim: dict[str, Mapping[str, Any]] = {}
    for item in claim_bindings:
        if not isinstance(item, Mapping):
            raise AcquisitionSourceTrustPolicyError(
                "acquisition binding returned malformed manifest claim bindings"
            )
        claim = item.get("claim")
        if not isinstance(claim, str) or claim in by_claim:
            raise AcquisitionSourceTrustPolicyError(
                "acquisition binding returned ambiguous manifest claim identity"
            )
        by_claim[claim] = item

    matches: list[dict[str, Any]] = []
    for rule in policy["rules"]:
        if acquisition["evidence_role"] != rule["evidence_role"]:
            continue
        matched = True
        for requirement in rule["required_manifest_claims"]:
            actual = by_claim.get(requirement["claim"])
            if actual is None:
                matched = False
                break
            if actual.get("json_pointer") != requirement["json_pointer"]:
                matched = False
                break
            actual_value = actual.get("expected_value")
            if not any(
                _same_scalar(actual_value, allowed)
                for allowed in requirement["allowed_values"]
            ):
                matched = False
                break
        if matched:
            matches.append(rule)

    if not matches:
        raise AcquisitionSourceTrustPolicyError(
            "exact acquisition record does not satisfy any pinned local reliance rule"
        )
    if len(matches) != 1:
        raise AcquisitionSourceTrustPolicyError(
            "exact acquisition record ambiguously satisfies multiple pinned local reliance rules"
        )
    matched_rule = matches[0]
    return {
        "schema_version": ACQUISITION_SOURCE_TRUST_QUALIFICATION_SCHEMA_VERSION,
        "source_trust_policy_sha256": actual_policy_sha,
        "source_trust_policy_id": policy["policy_id"],
        "matched_rule_id": matched_rule["rule_id"],
        "evidence_artifact_sha256": acquisition["evidence_artifact_sha256"],
        "acquisition_manifest_sha256": acquisition["acquisition_manifest_sha256"],
        "acquisition_declaration_sha256": acquisition["acquisition_declaration_sha256"],
        "evidence_role": acquisition["evidence_role"],
        "recorded_source_system": acquisition["recorded_source_system"],
        "recorded_source_version": acquisition["recorded_source_version"],
        "recorded_retrieval_endpoint": acquisition["recorded_retrieval_endpoint"],
        "recorded_retrieval_status": acquisition["recorded_retrieval_status"],
        "recorded_network_performed": acquisition["recorded_network_performed"],
        "local_record_reliance_qualified_under_supplied_pin": True,
        "expected_policy_pin_provenance_authenticated_by_this_contract": False,
        "external_source_identity_authenticated": False,
        "external_source_credentials_authenticated": False,
        "historical_acquisition_event_authenticated": False,
        "transport_peer_identity_authenticated": False,
        "physical_origin_truth_authenticated": False,
        "scientific_result_validity_authenticated": False,
        "support_independence_established": False,
        "empirical_authority_granted": False,
        "scientific_status_changed": False,
        "execution_authorized": False,
        "positive_closeout_granted": False,
        "policy_limitations": list(policy["limitations"]),
    }


__all__ = [
    "ACQUISITION_SOURCE_TRUST_POLICY_SCHEMA_VERSION",
    "ACQUISITION_SOURCE_TRUST_QUALIFICATION_SCHEMA_VERSION",
    "AcquisitionSourceTrustPolicyError",
    "qualify_acquisition_record_under_pinned_policy",
]
