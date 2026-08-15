"""Exact-byte binding for recorded acquisition provenance.

This primitive answers one narrow question: do exact evidence bytes and an exact
acquisition-manifest JSON object satisfy an explicit, checksum-bound declaration about
what that manifest records?

It does not authenticate the external source/provider identity, TLS peer, institutional
credentials, physical origin, scientific validity, source independence, or empirical
scientific authority. Source labels are authenticated only as *recorded manifest values*.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .kernel import ResearchLoopError

ACQUISITION_RECORD_BINDING_SCHEMA_VERSION = "1.0"
ACQUISITION_RECORD_DECLARATION_SCHEMA_VERSION = "1.0"

_DECLARATION_KEYS = {
    "schema_version",
    "acquisition_id",
    "evidence_artifact_sha256",
    "acquisition_manifest_sha256",
    "evidence_role",
    "manifest_evidence_sha256_pointer",
    "manifest_claim_bindings",
    "limitations",
}
_CLAIM_KEYS = {"claim", "json_pointer", "expected_value"}
_REQUIRED_CLAIMS = {
    "source_system",
    "source_version",
    "retrieval_endpoint",
    "retrieval_status",
    "network_performed",
}


class AcquisitionRecordBindingError(ResearchLoopError):
    """Raised when exact acquisition-record provenance cannot be authenticated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AcquisitionRecordBindingError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcquisitionRecordBindingError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise AcquisitionRecordBindingError(f"{field} root must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    keys = set(value)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing or unknown:
        raise AcquisitionRecordBindingError(
            f"{field} must use the exact key set; unknown={unknown}, missing={missing}"
        )


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AcquisitionRecordBindingError(f"{field} must be non-empty text")
    if value != value.strip():
        raise AcquisitionRecordBindingError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise AcquisitionRecordBindingError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return text


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise AcquisitionRecordBindingError(f"{field} must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _strict_text(item, f"{field}[{index}]")
        if text in result:
            raise AcquisitionRecordBindingError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _claim_scalar(value: object, field: str) -> str | int | bool | None:
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str):
            return _strict_text(value, field)
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise AcquisitionRecordBindingError(
        f"{field} must be a JSON string, integer, boolean, or null"
    )


def _decode_pointer_token(value: str, *, field: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "~":
            result.append(char)
            index += 1
            continue
        if index + 1 >= len(value) or value[index + 1] not in {"0", "1"}:
            raise AcquisitionRecordBindingError(
                f"{field} contains an invalid RFC 6901 escape"
            )
        result.append("~" if value[index + 1] == "0" else "/")
        index += 2
    return "".join(result)


def _json_pointer(value: object, field: str) -> tuple[str, ...]:
    text = _strict_text(value, field)
    if not text.startswith("/"):
        raise AcquisitionRecordBindingError(
            f"{field} must be a non-root RFC 6901 JSON pointer"
        )
    raw_tokens = text[1:].split("/")
    if not raw_tokens or any(token == "" for token in raw_tokens):
        raise AcquisitionRecordBindingError(
            f"{field} must not contain empty path tokens"
        )
    return tuple(
        _decode_pointer_token(token, field=f"{field} token") for token in raw_tokens
    )


def _resolve_pointer(root: object, pointer: object, *, field: str) -> object:
    tokens = _json_pointer(pointer, field)
    current: object = root
    for index, token in enumerate(tokens):
        if isinstance(current, Mapping):
            if token not in current:
                raise AcquisitionRecordBindingError(
                    f"{field} does not resolve in the exact acquisition manifest"
                )
            current = current[token]
            continue
        if isinstance(current, list):
            if token == "-" or not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise AcquisitionRecordBindingError(
                    f"{field} contains an invalid array index at token {index}"
                )
            item_index = int(token)
            if item_index >= len(current):
                raise AcquisitionRecordBindingError(
                    f"{field} array index is outside the exact acquisition manifest"
                )
            current = current[item_index]
            continue
        raise AcquisitionRecordBindingError(
            f"{field} traverses through a non-container manifest value"
        )
    return current


def _normalize_claims(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise AcquisitionRecordBindingError(
            "manifest_claim_bindings must be a non-empty list"
        )
    result: list[dict[str, Any]] = []
    names: set[str] = set()
    pointers: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise AcquisitionRecordBindingError(
                f"manifest_claim_bindings[{index}] must be an object"
            )
        _exact_keys(item, _CLAIM_KEYS, field=f"manifest_claim_bindings[{index}]")
        name = _strict_text(item["claim"], f"manifest_claim_bindings[{index}].claim")
        pointer_text = _strict_text(
            item["json_pointer"], f"manifest_claim_bindings[{index}].json_pointer"
        )
        _json_pointer(pointer_text, f"manifest_claim_bindings[{index}].json_pointer")
        expected = _claim_scalar(
            item["expected_value"], f"manifest_claim_bindings[{index}].expected_value"
        )
        if name in names:
            raise AcquisitionRecordBindingError(
                "manifest_claim_bindings claim names must be unique"
            )
        if pointer_text in pointers:
            raise AcquisitionRecordBindingError(
                "manifest_claim_bindings JSON pointers must be unique"
            )
        names.add(name)
        pointers.add(pointer_text)
        result.append(
            {
                "claim": name,
                "json_pointer": pointer_text,
                "expected_value": expected,
            }
        )
    missing = sorted(_REQUIRED_CLAIMS - names)
    if missing:
        raise AcquisitionRecordBindingError(
            "manifest_claim_bindings are missing required recorded-provenance claims: "
            + ", ".join(missing)
        )
    by_name = {item["claim"]: item for item in result}
    for claim_name in (
        "source_system",
        "source_version",
        "retrieval_endpoint",
        "retrieval_status",
    ):
        if not isinstance(by_name[claim_name]["expected_value"], str):
            raise AcquisitionRecordBindingError(
                f"required manifest claim {claim_name!r} must declare a text value"
            )
    if not isinstance(by_name["network_performed"]["expected_value"], bool):
        raise AcquisitionRecordBindingError(
            "required manifest claim 'network_performed' must declare a boolean value"
        )
    return result


def authenticate_acquisition_record_binding(
    *,
    evidence_bytes: bytes,
    acquisition_manifest_bytes: bytes,
    acquisition_declaration_bytes: bytes,
) -> dict[str, Any]:
    """Authenticate exact recorded acquisition provenance without external-source authority."""
    evidence_sha = hashlib.sha256(evidence_bytes).hexdigest()
    manifest_sha = hashlib.sha256(acquisition_manifest_bytes).hexdigest()
    declaration_sha = hashlib.sha256(acquisition_declaration_bytes).hexdigest()

    manifest = _json_object(acquisition_manifest_bytes, field="acquisition manifest")
    declaration = _json_object(
        acquisition_declaration_bytes, field="acquisition declaration"
    )
    _exact_keys(declaration, _DECLARATION_KEYS, field="acquisition declaration")
    if declaration["schema_version"] != ACQUISITION_RECORD_DECLARATION_SCHEMA_VERSION:
        raise AcquisitionRecordBindingError(
            "unsupported acquisition declaration schema_version"
        )
    acquisition_id = _strict_text(
        declaration["acquisition_id"], "acquisition declaration acquisition_id"
    )
    declared_evidence_sha = _sha256_text(
        declaration["evidence_artifact_sha256"],
        "acquisition declaration evidence_artifact_sha256",
    )
    if declared_evidence_sha != evidence_sha:
        raise AcquisitionRecordBindingError(
            "acquisition declaration evidence SHA does not match exact evidence bytes"
        )
    declared_manifest_sha = _sha256_text(
        declaration["acquisition_manifest_sha256"],
        "acquisition declaration acquisition_manifest_sha256",
    )
    if declared_manifest_sha != manifest_sha:
        raise AcquisitionRecordBindingError(
            "acquisition declaration manifest SHA does not match exact manifest bytes"
        )
    evidence_role = _strict_text(
        declaration["evidence_role"], "acquisition declaration evidence_role"
    )
    evidence_pointer = _strict_text(
        declaration["manifest_evidence_sha256_pointer"],
        "acquisition declaration manifest_evidence_sha256_pointer",
    )
    recorded_evidence_sha = _resolve_pointer(
        manifest,
        evidence_pointer,
        field="acquisition declaration manifest_evidence_sha256_pointer",
    )
    if recorded_evidence_sha != evidence_sha:
        raise AcquisitionRecordBindingError(
            "exact acquisition manifest does not record the exact evidence SHA at the declared pointer"
        )

    claims = _normalize_claims(declaration["manifest_claim_bindings"])
    authenticated_claims: list[dict[str, Any]] = []
    for claim in claims:
        actual = _resolve_pointer(
            manifest,
            claim["json_pointer"],
            field=f"manifest claim {claim['claim']!r}",
        )
        expected = claim["expected_value"]
        if (
            isinstance(actual, (dict, list, float))
            or type(actual) is not type(expected)
            or actual != expected
        ):
            raise AcquisitionRecordBindingError(
                f"manifest claim {claim['claim']!r} does not equal its exact declared value/type"
            )
        authenticated_claims.append(dict(claim))

    limitations = _string_list(
        declaration["limitations"], "acquisition declaration limitations"
    )
    if not limitations:
        raise AcquisitionRecordBindingError(
            "acquisition declaration limitations must be non-empty"
        )
    claim_map = {item["claim"]: item["expected_value"] for item in authenticated_claims}
    return {
        "schema_version": ACQUISITION_RECORD_BINDING_SCHEMA_VERSION,
        "acquisition_id": acquisition_id,
        "evidence_artifact_sha256": evidence_sha,
        "acquisition_manifest_sha256": manifest_sha,
        "acquisition_declaration_sha256": declaration_sha,
        "evidence_role": evidence_role,
        "recorded_source_system": claim_map["source_system"],
        "recorded_source_version": claim_map["source_version"],
        "recorded_retrieval_endpoint": claim_map["retrieval_endpoint"],
        "recorded_retrieval_status": claim_map["retrieval_status"],
        "recorded_network_performed": claim_map["network_performed"],
        "authenticated_manifest_claim_bindings": authenticated_claims,
        "recorded_acquisition_provenance_authenticated": True,
        "historical_acquisition_event_authenticated": False,
        "acquisition_manifest_authorship_authenticated": False,
        "source_identity_or_credential_authenticated": False,
        "transport_peer_identity_authenticated_by_this_contract": False,
        "physical_origin_truth_authenticated": False,
        "scientific_result_validity_authenticated": False,
        "support_independence_established": False,
        "empirical_authority_granted": False,
        "scientific_status_changed": False,
        "execution_authorized": False,
        "positive_closeout_granted": False,
        "limitations": limitations,
    }


__all__ = [
    "ACQUISITION_RECORD_BINDING_SCHEMA_VERSION",
    "ACQUISITION_RECORD_DECLARATION_SCHEMA_VERSION",
    "AcquisitionRecordBindingError",
    "authenticate_acquisition_record_binding",
]
