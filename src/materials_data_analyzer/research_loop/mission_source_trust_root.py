"""Authenticate one source-trust policy pin under an externally supplied mission root.

This contract closes one control-plane provenance gap: exact mission bytes must match an
independently supplied expected SHA-256 before a first-class mission policy pin may be
used downstream.  It does not authenticate where that expected mission SHA came from,
validate acquisition records, or grant scientific/external-source authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .kernel import ResearchLoopError
from .research_program import ResearchProgramError, validate_research_mission

MISSION_SOURCE_TRUST_ROOT_SCHEMA_VERSION = "1.0"
MISSION_SOURCE_TRUST_ROOT_POLICY_VERSION = "1.0"

_EXPECTED_MISSION_SCHEMA_VERSION = "1.1"
_EXPECTED_PROGRAM_SCHEMA_VERSION = "1.1"
_EXPECTED_PROGRAM_POLICY_VERSION = "1.0"
_EXPECTED_SOURCE_TRUST_POLICY_SCHEMA_VERSION = "1.0"
_MISSION_BINDING_KEYS = {"path", "sha256"}
_POLICY_ENVELOPE_KEYS = {"schema_version", "policy_id", "rules", "limitations"}


class MissionSourceTrustRootError(ResearchLoopError):
    """Raised when a mission-rooted source-trust policy pin cannot be authenticated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MissionSourceTrustRootError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise MissionSourceTrustRootError(f"{field} must be exact bytes")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MissionSourceTrustRootError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise MissionSourceTrustRootError(f"{field} root must be an object")
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MissionSourceTrustRootError(f"{field} must be non-empty text")
    if value != value.strip():
        raise MissionSourceTrustRootError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise MissionSourceTrustRootError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return text


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    keys = set(value)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing or unknown:
        raise MissionSourceTrustRootError(
            f"{field} must use the exact key set; unknown={unknown}, missing={missing}"
        )


def _typed_equal(left: object, right: object) -> bool:
    """Recursively compare JSON-like values without Python bool/int equivalence."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        assert isinstance(right, dict)
        if set(left) != set(right):
            return False
        return all(_typed_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        assert isinstance(right, list)
        return len(left) == len(right) and all(
            _typed_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def _policy_identity(raw: bytes) -> dict[str, str]:
    policy = _json_object(raw, field="source trust policy bytes")
    _exact_keys(
        policy,
        _POLICY_ENVELOPE_KEYS,
        field="source trust policy envelope",
    )
    if policy["schema_version"] != _EXPECTED_SOURCE_TRUST_POLICY_SCHEMA_VERSION:
        raise MissionSourceTrustRootError(
            "unsupported source trust policy schema_version"
        )
    policy_id = _strict_text(policy["policy_id"], "source trust policy policy_id")
    if not isinstance(policy["rules"], list) or not policy["rules"]:
        raise MissionSourceTrustRootError(
            "source trust policy rules must be a non-empty list"
        )
    limitations = policy["limitations"]
    if not isinstance(limitations, list) or not limitations:
        raise MissionSourceTrustRootError(
            "source trust policy limitations must be a non-empty list"
        )
    for index, item in enumerate(limitations):
        _strict_text(item, f"source trust policy limitations[{index}]")
    return {
        "policy_id": policy_id,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def authenticate_mission_source_trust_policy_pin(
    *,
    mission_bytes: bytes,
    expected_mission_sha256: str,
    program_state: Mapping[str, Any],
    policy_id: str,
    source_trust_policy_bytes: bytes,
) -> dict[str, Any]:
    """Bind one exact policy file to a first-class pin under a supplied mission root."""
    expected_mission_sha = _sha256_text(
        expected_mission_sha256,
        "expected_mission_sha256",
    )
    actual_mission_sha = hashlib.sha256(mission_bytes).hexdigest()
    if actual_mission_sha != expected_mission_sha:
        raise MissionSourceTrustRootError(
            "exact mission bytes do not match the supplied expected mission SHA"
        )

    mission_object = _json_object(mission_bytes, field="mission bytes")
    try:
        normalized_mission = validate_research_mission(mission_object)
    except ResearchProgramError as exc:
        raise MissionSourceTrustRootError(
            "exact mission bytes failed the research mission contract"
        ) from exc
    if normalized_mission.get("schema_version") != _EXPECTED_MISSION_SCHEMA_VERSION:
        raise MissionSourceTrustRootError(
            "source-trust policy pins require exact mission schema_version 1.1"
        )

    selected_policy_id = _strict_text(policy_id, "policy_id")
    mission_pins = normalized_mission.get("source_trust_policy_pins")
    if not isinstance(mission_pins, list) or not mission_pins:
        raise MissionSourceTrustRootError(
            "authenticated mission contains no first-class source-trust policy pins"
        )
    selected = [
        item
        for item in mission_pins
        if isinstance(item, Mapping) and item.get("policy_id") == selected_policy_id
    ]
    if len(selected) != 1:
        raise MissionSourceTrustRootError(
            "policy_id must identify exactly one first-class mission policy pin"
        )
    selected_pin = selected[0]
    pinned_policy_sha = _sha256_text(
        selected_pin.get("sha256"),
        "selected mission policy pin sha256",
    )

    if not isinstance(program_state, Mapping):
        raise MissionSourceTrustRootError("program_state must be an object")
    if program_state.get("schema_version") != _EXPECTED_PROGRAM_SCHEMA_VERSION:
        raise MissionSourceTrustRootError(
            "program_state schema_version must be 1.1 for mission-root authentication"
        )
    if program_state.get("program_policy_version") != _EXPECTED_PROGRAM_POLICY_VERSION:
        raise MissionSourceTrustRootError(
            "program_state program_policy_version is unsupported"
        )

    mission_binding = program_state.get("mission_binding")
    if not isinstance(mission_binding, Mapping):
        raise MissionSourceTrustRootError(
            "program_state.mission_binding must be an object"
        )
    _exact_keys(
        mission_binding,
        _MISSION_BINDING_KEYS,
        field="program_state.mission_binding",
    )
    _strict_text(mission_binding["path"], "program_state.mission_binding.path")
    program_mission_sha = _sha256_text(
        mission_binding["sha256"],
        "program_state.mission_binding.sha256",
    )
    if program_mission_sha != expected_mission_sha:
        raise MissionSourceTrustRootError(
            "program_state mission binding does not match the supplied mission root"
        )

    program_mission = program_state.get("mission")
    if not isinstance(program_mission, dict) or not _typed_equal(
        program_mission,
        normalized_mission,
    ):
        raise MissionSourceTrustRootError(
            "program_state normalized mission does not exactly match authenticated mission bytes"
        )
    program_pins = program_state.get("source_trust_policy_pins")
    if not isinstance(program_pins, list) or not _typed_equal(program_pins, mission_pins):
        raise MissionSourceTrustRootError(
            "program_state projected policy pins do not exactly match authenticated mission"
        )

    policy_identity = _policy_identity(source_trust_policy_bytes)
    if policy_identity["sha256"] != pinned_policy_sha:
        raise MissionSourceTrustRootError(
            "source trust policy bytes do not match the authenticated mission policy pin"
        )
    if policy_identity["policy_id"] != selected_policy_id:
        raise MissionSourceTrustRootError(
            "source trust policy internal policy_id does not match the selected mission pin"
        )

    return {
        "schema_version": MISSION_SOURCE_TRUST_ROOT_SCHEMA_VERSION,
        "policy_version": MISSION_SOURCE_TRUST_ROOT_POLICY_VERSION,
        "mission_sha256": actual_mission_sha,
        "mission_schema_version": _EXPECTED_MISSION_SCHEMA_VERSION,
        "program_schema_version": _EXPECTED_PROGRAM_SCHEMA_VERSION,
        "source_trust_policy_id": selected_policy_id,
        "source_trust_policy_sha256": pinned_policy_sha,
        "mission_bytes_match_supplied_root": True,
        "program_projection_matches_authenticated_mission": True,
        "policy_pin_provenance_authenticated_under_supplied_mission_root": True,
        "source_trust_policy_bytes_match_authenticated_pin": True,
        "expected_mission_root_provenance_authenticated_by_this_contract": False,
        "full_program_state_provenance_reauthenticated": False,
        "source_trust_policy_semantics_validated": False,
        "local_record_reliance_qualified": False,
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
    }


__all__ = [
    "MISSION_SOURCE_TRUST_ROOT_POLICY_VERSION",
    "MISSION_SOURCE_TRUST_ROOT_SCHEMA_VERSION",
    "MissionSourceTrustRootError",
    "authenticate_mission_source_trust_policy_pin",
]
