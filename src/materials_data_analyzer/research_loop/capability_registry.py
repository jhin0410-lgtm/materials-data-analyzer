"""Immutable lifecycle contracts for autonomous capability candidates and promotion."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

CAPABILITY_REGISTRY_SCHEMA_VERSION = "1.0"
CAPABILITY_CANDIDATE_SCHEMA_VERSION = "1.0"
CAPABILITY_VERIFICATION_SCHEMA_VERSION = "1.0"
CAPABILITY_REGISTRY_POLICY_VERSION = "1.0"

_ALLOWED_STATES = frozenset({"candidate", "verified", "rejected", "superseded"})
_ALLOWED_MECHANISMS = frozenset(
    {
        "reuse_verified_capability",
        "compose_verified_primitives",
        "generate_declarative_adapter_instance",
    }
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CapabilityRegistryError(ValueError):
    """Raised when candidate or registry provenance cannot be authenticated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CapabilityRegistryError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _strict_text(value: object, field: str) -> str:
    _require(
        isinstance(value, str) and value.strip() == value and bool(value),
        f"{field} must be non-empty trimmed text",
    )
    return value


def _validate_self_hash(value: Mapping[str, Any], hash_field: str) -> str:
    digest = value.get(hash_field)
    _require(
        isinstance(digest, str) and _HEX64.fullmatch(digest) is not None,
        f"{hash_field} is missing",
    )
    unsigned = dict(value)
    unsigned.pop(hash_field, None)
    _require(_canonical_sha(unsigned) == digest, f"{hash_field} is invalid")
    return digest


def build_initial_capability_registry(
    *,
    verified_action_classes: Sequence[str],
) -> dict[str, Any]:
    """Build an immutable in-run registry rooted in pre-existing audited action classes."""
    action_classes = [_strict_text(item, "verified_action_class") for item in verified_action_classes]
    _require(len(set(action_classes)) == len(action_classes), "verified action classes must be unique")
    records = [
        {
            "action_class": action_class,
            "state": "verified",
            "origin": "preexisting_audited_runtime",
            "candidate_sha256": None,
            "verification_sha256": None,
            "implementation_id": f"builtin:{action_class}",
        }
        for action_class in sorted(action_classes)
    ]
    registry: dict[str, Any] = {
        "schema_version": CAPABILITY_REGISTRY_SCHEMA_VERSION,
        "policy_version": CAPABILITY_REGISTRY_POLICY_VERSION,
        "artifact_type": "capability_registry",
        "predecessor_registry_sha256": None,
        "records": records,
        "candidate_self_promotion_allowed": False,
        "arbitrary_code_execution_allowed": False,
        "network_authority_synthesis_allowed": False,
    }
    registry["capability_registry_sha256_without_self_field"] = _canonical_sha(registry)
    return registry


def build_capability_candidate(
    *,
    capability_specification: Mapping[str, Any],
    factory_id: str,
    implementation_id: str,
    mechanism: str,
    required_verified_primitives: Sequence[str],
) -> dict[str, Any]:
    """Create an unverified candidate; this function grants no registry authority."""
    spec_sha = capability_specification.get(
        "capability_specification_sha256_without_self_field"
    )
    _require(
        isinstance(spec_sha, str) and _HEX64.fullmatch(spec_sha) is not None,
        "capability specification binding is missing",
    )
    unsigned_spec = dict(capability_specification)
    unsigned_spec.pop("capability_specification_sha256_without_self_field", None)
    _require(_canonical_sha(unsigned_spec) == spec_sha, "capability specification binding is invalid")
    action_class = _strict_text(
        capability_specification.get("requested_action_class"),
        "requested_action_class",
    )
    factory_id = _strict_text(factory_id, "factory_id")
    implementation_id = _strict_text(implementation_id, "implementation_id")
    mechanism = _strict_text(mechanism, "mechanism")
    _require(mechanism in _ALLOWED_MECHANISMS, "candidate mechanism is not allowed")
    spec_mechanisms = capability_specification.get("allowed_implementation_mechanisms")
    _require(
        isinstance(spec_mechanisms, list) and mechanism in spec_mechanisms,
        "candidate mechanism is not allowed by capability specification",
    )
    primitives = [_strict_text(item, "required_verified_primitive") for item in required_verified_primitives]
    _require(len(set(primitives)) == len(primitives), "required primitives must be unique")

    candidate: dict[str, Any] = {
        "schema_version": CAPABILITY_CANDIDATE_SCHEMA_VERSION,
        "policy_version": CAPABILITY_REGISTRY_POLICY_VERSION,
        "artifact_type": "capability_candidate",
        "state": "candidate",
        "action_class": action_class,
        "capability_specification_sha256": spec_sha,
        "factory_id": factory_id,
        "implementation_id": implementation_id,
        "mechanism": mechanism,
        "required_verified_primitives": sorted(primitives),
        "network_authority_granted": False,
        "execution_authority_granted": False,
        "scientific_status_change_authorized": False,
        "self_promotion_requested": False,
    }
    candidate["capability_candidate_sha256_without_self_field"] = _canonical_sha(candidate)
    return candidate


def build_capability_verification_receipt(
    *,
    capability_specification: Mapping[str, Any],
    candidate: Mapping[str, Any],
    available_verified_primitives: Sequence[str],
    verification_results: Mapping[str, bool],
) -> dict[str, Any]:
    """Independently verify a candidate against its exact spec and required test classes."""
    spec_sha = _validate_self_hash(
        capability_specification,
        "capability_specification_sha256_without_self_field",
    )
    candidate_sha = _validate_self_hash(
        candidate,
        "capability_candidate_sha256_without_self_field",
    )
    _require(candidate.get("state") == "candidate", "only candidate state may be verified")
    _require(
        candidate.get("capability_specification_sha256") == spec_sha,
        "candidate specification binding drifted",
    )
    _require(
        candidate.get("action_class") == capability_specification.get("requested_action_class"),
        "candidate action class drifted",
    )
    _require(
        candidate.get("network_authority_granted") is False
        and candidate.get("execution_authority_granted") is False
        and candidate.get("scientific_status_change_authorized") is False
        and candidate.get("self_promotion_requested") is False,
        "candidate attempted to pre-authorize itself",
    )
    available = {
        _strict_text(item, "available_verified_primitive")
        for item in available_verified_primitives
    }
    required = candidate.get("required_verified_primitives")
    _require(isinstance(required, list), "candidate required primitives missing")
    _require(set(required).issubset(available), "candidate requires an unverified primitive")

    required_checks = capability_specification.get("verification_requirements")
    _require(isinstance(required_checks, list) and required_checks, "spec verification requirements missing")
    normalized_results: dict[str, bool] = {}
    for check in required_checks:
        check_name = _strict_text(check, "verification_requirement")
        result = verification_results.get(check_name)
        _require(isinstance(result, bool), f"verification result missing for {check_name}")
        normalized_results[check_name] = result
    passed = all(normalized_results.values())
    receipt: dict[str, Any] = {
        "schema_version": CAPABILITY_VERIFICATION_SCHEMA_VERSION,
        "policy_version": CAPABILITY_REGISTRY_POLICY_VERSION,
        "artifact_type": "capability_verification_receipt",
        "action_class": candidate["action_class"],
        "capability_specification_sha256": spec_sha,
        "capability_candidate_sha256": candidate_sha,
        "verification_results": normalized_results,
        "all_required_checks_passed": passed,
        "promotion_eligible": passed,
        "execution_performed": False,
        "scientific_status_changed": False,
    }
    receipt["capability_verification_sha256_without_self_field"] = _canonical_sha(receipt)
    return receipt


def promote_verified_capability(
    *,
    registry: Mapping[str, Any],
    candidate: Mapping[str, Any],
    verification_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Promote only an independently verified candidate into an immutable successor registry."""
    registry_sha = _validate_self_hash(
        registry,
        "capability_registry_sha256_without_self_field",
    )
    candidate_sha = _validate_self_hash(
        candidate,
        "capability_candidate_sha256_without_self_field",
    )
    verification_sha = _validate_self_hash(
        verification_receipt,
        "capability_verification_sha256_without_self_field",
    )
    _require(
        registry.get("candidate_self_promotion_allowed") is False,
        "registry self-promotion boundary drifted",
    )
    _require(
        verification_receipt.get("capability_candidate_sha256") == candidate_sha,
        "verification receipt candidate binding drifted",
    )
    _require(
        verification_receipt.get("action_class") == candidate.get("action_class"),
        "verification receipt action class drifted",
    )
    _require(
        verification_receipt.get("all_required_checks_passed") is True
        and verification_receipt.get("promotion_eligible") is True,
        "candidate did not pass independent promotion gate",
    )
    records = registry.get("records")
    _require(isinstance(records, list), "registry records missing")
    action_class = _strict_text(candidate.get("action_class"), "candidate.action_class")
    _require(
        not any(
            isinstance(record, Mapping)
            and record.get("action_class") == action_class
            and record.get("state") == "verified"
            for record in records
        ),
        "verified capability already exists for action class",
    )
    successor_records = [dict(record) if isinstance(record, Mapping) else record for record in records]
    successor_records.append(
        {
            "action_class": action_class,
            "state": "verified",
            "origin": "independently_verified_capability_expansion",
            "candidate_sha256": candidate_sha,
            "verification_sha256": verification_sha,
            "implementation_id": candidate.get("implementation_id"),
        }
    )
    successor: dict[str, Any] = {
        "schema_version": CAPABILITY_REGISTRY_SCHEMA_VERSION,
        "policy_version": CAPABILITY_REGISTRY_POLICY_VERSION,
        "artifact_type": "capability_registry",
        "predecessor_registry_sha256": registry_sha,
        "records": successor_records,
        "candidate_self_promotion_allowed": False,
        "arbitrary_code_execution_allowed": False,
        "network_authority_synthesis_allowed": False,
    }
    successor["capability_registry_sha256_without_self_field"] = _canonical_sha(successor)
    return successor


def resolve_verified_capability(
    *,
    registry: Mapping[str, Any],
    action_class: str,
) -> dict[str, Any]:
    """Resolve only exact verified records; candidates and rejected records are ignored."""
    registry_sha = _validate_self_hash(
        registry,
        "capability_registry_sha256_without_self_field",
    )
    action_class = _strict_text(action_class, "action_class")
    records = registry.get("records")
    _require(isinstance(records, list), "registry records missing")
    matches = [
        record
        for record in records
        if isinstance(record, Mapping)
        and record.get("action_class") == action_class
        and record.get("state") == "verified"
    ]
    _require(len(matches) <= 1, "multiple verified capabilities exist for action class")
    if not matches:
        return {
            "resolved": False,
            "action_class": action_class,
            "registry_sha256": registry_sha,
            "implementation_id": None,
        }
    implementation_id = _strict_text(
        matches[0].get("implementation_id"),
        "implementation_id",
    )
    return {
        "resolved": True,
        "action_class": action_class,
        "registry_sha256": registry_sha,
        "implementation_id": implementation_id,
    }


__all__ = [
    "CAPABILITY_CANDIDATE_SCHEMA_VERSION",
    "CAPABILITY_REGISTRY_POLICY_VERSION",
    "CAPABILITY_REGISTRY_SCHEMA_VERSION",
    "CAPABILITY_VERIFICATION_SCHEMA_VERSION",
    "CapabilityRegistryError",
    "build_capability_candidate",
    "build_capability_verification_receipt",
    "build_initial_capability_registry",
    "promote_verified_capability",
    "resolve_verified_capability",
]
