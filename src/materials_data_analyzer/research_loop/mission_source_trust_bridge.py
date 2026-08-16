"""Bind local acquisition-policy qualification to exact mission bytes under a supplied root.

This bridge intentionally treats the caller-supplied expected mission SHA-256 as the
external trust root. It authenticates neither who supplied that digest nor the security
of the channel that supplied it. Exact mission bytes, the mission's first-class source-
trust policy pin, the program projection, and the existing acquisition-policy qualifier
must all agree before local record reliance is reported.

The bridge does not authenticate provider identity, physical origin, scientific result
validity, support independence, empirical authority, execution, or positive closeout.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .acquisition_source_trust_policy import (
    AcquisitionSourceTrustPolicyError,
    qualify_acquisition_record_under_pinned_policy,
)
from .kernel import ResearchLoopError
from .research_program import ResearchProgramError, validate_research_mission

MISSION_SOURCE_TRUST_BRIDGE_SCHEMA_VERSION = "1.0"
_SUPPORTED_MISSION_SCHEMA_VERSION = "1.1"
_SUPPORTED_PROGRAM_SCHEMA_VERSION = "1.1"
_SUPPORTED_PROGRAM_POLICY_VERSION = "1.0"
_SUPPORTED_ACQUISITION_QUALIFICATION_SCHEMA_VERSION = "1.0"

_MISSION_BINDING_KEYS = {"path", "sha256"}
_ACQUISITION_QUALIFICATION_KEYS = {
    "schema_version",
    "source_trust_policy_sha256",
    "source_trust_policy_id",
    "matched_rule_id",
    "evidence_artifact_sha256",
    "acquisition_manifest_sha256",
    "acquisition_declaration_sha256",
    "evidence_role",
    "recorded_source_system",
    "recorded_source_version",
    "recorded_retrieval_endpoint",
    "recorded_retrieval_status",
    "recorded_network_performed",
    "local_record_reliance_qualified_under_supplied_pin",
    "expected_policy_pin_provenance_authenticated_by_this_contract",
    "external_source_identity_authenticated",
    "external_source_credentials_authenticated",
    "historical_acquisition_event_authenticated",
    "transport_peer_identity_authenticated",
    "physical_origin_truth_authenticated",
    "scientific_result_validity_authenticated",
    "support_independence_established",
    "empirical_authority_granted",
    "scientific_status_changed",
    "execution_authorized",
    "positive_closeout_granted",
    "policy_limitations",
}
_REQUIRED_DOWNSTREAM_FALSE_FLAGS = {
    "expected_policy_pin_provenance_authenticated_by_this_contract",
    "external_source_identity_authenticated",
    "external_source_credentials_authenticated",
    "historical_acquisition_event_authenticated",
    "transport_peer_identity_authenticated",
    "physical_origin_truth_authenticated",
    "scientific_result_validity_authenticated",
    "support_independence_established",
    "empirical_authority_granted",
    "scientific_status_changed",
    "execution_authorized",
    "positive_closeout_granted",
}


class MissionSourceTrustBridgeError(ResearchLoopError):
    """Raised when mission-rooted source-trust qualification cannot be established."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MissionSourceTrustBridgeError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MissionSourceTrustBridgeError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise MissionSourceTrustBridgeError(f"{field} root must be an object")
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MissionSourceTrustBridgeError(f"{field} must be non-empty text")
    if value != value.strip():
        raise MissionSourceTrustBridgeError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise MissionSourceTrustBridgeError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return text


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    keys = set(value)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing or unknown:
        raise MissionSourceTrustBridgeError(
            f"{field} must use the exact key set; unknown={unknown}, missing={missing}"
        )


def _normalized_mission(mission_bytes: bytes) -> dict[str, Any]:
    mission_raw = _json_object(mission_bytes, field="research mission")
    try:
        mission = validate_research_mission(mission_raw)
    except ResearchProgramError as exc:
        raise MissionSourceTrustBridgeError(
            "research mission failed the current mission contract"
        ) from exc
    if mission.get("schema_version") != _SUPPORTED_MISSION_SCHEMA_VERSION:
        raise MissionSourceTrustBridgeError(
            "mission-rooted source-trust qualification requires mission schema_version 1.1"
        )
    pins = mission.get("source_trust_policy_pins")
    if not isinstance(pins, list) or not pins:
        raise MissionSourceTrustBridgeError(
            "authenticated mission bytes must contain first-class source_trust_policy_pins"
        )
    return mission


def _selected_policy_pin(
    mission: Mapping[str, Any],
    requested_policy_id: str,
) -> dict[str, str]:
    pins = mission["source_trust_policy_pins"]
    if not isinstance(pins, list):
        raise MissionSourceTrustBridgeError("mission source trust policy pins are malformed")
    matches = [
        pin
        for pin in pins
        if isinstance(pin, dict) and pin.get("policy_id") == requested_policy_id
    ]
    if len(matches) != 1:
        raise MissionSourceTrustBridgeError(
            "requested source trust policy ID must match exactly one authenticated mission pin"
        )
    pin = matches[0]
    if set(pin) != {"policy_id", "sha256"}:
        raise MissionSourceTrustBridgeError(
            "authenticated mission source trust policy pin has an unexpected shape"
        )
    return {
        "policy_id": _strict_text(pin["policy_id"], "mission source trust policy policy_id"),
        "sha256": _sha256_text(pin["sha256"], "mission source trust policy sha256"),
    }


def _validate_program_projection(
    program_state: Mapping[str, Any],
    *,
    normalized_mission: Mapping[str, Any],
    expected_mission_sha256: str,
) -> None:
    if program_state.get("schema_version") != _SUPPORTED_PROGRAM_SCHEMA_VERSION:
        raise MissionSourceTrustBridgeError(
            "program_state schema_version is not the pinned bridge-compatible version"
        )
    if program_state.get("program_policy_version") != _SUPPORTED_PROGRAM_POLICY_VERSION:
        raise MissionSourceTrustBridgeError(
            "program_state program_policy_version is not the pinned bridge-compatible version"
        )

    binding = program_state.get("mission_binding")
    if not isinstance(binding, Mapping):
        raise MissionSourceTrustBridgeError("program_state.mission_binding must be an object")
    _exact_keys(binding, _MISSION_BINDING_KEYS, field="program_state.mission_binding")
    _strict_text(binding["path"], "program_state.mission_binding.path")
    binding_sha = _sha256_text(
        binding["sha256"], "program_state.mission_binding.sha256"
    )
    if binding_sha != expected_mission_sha256:
        raise MissionSourceTrustBridgeError(
            "program_state mission binding does not match the supplied expected mission SHA"
        )

    projected_mission = program_state.get("mission")
    if not isinstance(projected_mission, dict) or projected_mission != normalized_mission:
        raise MissionSourceTrustBridgeError(
            "program_state normalized mission does not match the authenticated mission bytes"
        )

    expected_pins = normalized_mission["source_trust_policy_pins"]
    projected_pins = program_state.get("source_trust_policy_pins")
    if not isinstance(projected_pins, list) or projected_pins != expected_pins:
        raise MissionSourceTrustBridgeError(
            "program_state projected source trust policy pins do not match the authenticated mission"
        )


def _validate_downstream_qualification(
    qualification: Mapping[str, Any],
    *,
    selected_pin: Mapping[str, str],
) -> dict[str, Any]:
    _exact_keys(
        qualification,
        _ACQUISITION_QUALIFICATION_KEYS,
        field="acquisition source trust qualification",
    )
    if qualification.get("schema_version") != _SUPPORTED_ACQUISITION_QUALIFICATION_SCHEMA_VERSION:
        raise MissionSourceTrustBridgeError(
            "downstream acquisition qualification schema_version changed"
        )
    if qualification.get("source_trust_policy_id") != selected_pin["policy_id"]:
        raise MissionSourceTrustBridgeError(
            "qualified policy ID does not match the authenticated mission policy pin"
        )
    if qualification.get("source_trust_policy_sha256") != selected_pin["sha256"]:
        raise MissionSourceTrustBridgeError(
            "qualified policy SHA does not match the authenticated mission policy pin"
        )
    if qualification.get("local_record_reliance_qualified_under_supplied_pin") is not True:
        raise MissionSourceTrustBridgeError(
            "downstream acquisition qualifier did not establish bounded local record reliance"
        )
    for flag in sorted(_REQUIRED_DOWNSTREAM_FALSE_FLAGS):
        if qualification.get(flag) is not False:
            raise MissionSourceTrustBridgeError(
                f"downstream acquisition qualifier broadened the bridge authority boundary: {flag}"
            )
    limitations = qualification.get("policy_limitations")
    if not isinstance(limitations, list) or not limitations:
        raise MissionSourceTrustBridgeError(
            "downstream acquisition qualification must retain explicit policy limitations"
        )
    return dict(qualification)


def qualify_acquisition_record_under_expected_mission_policy(
    *,
    mission_bytes: bytes,
    expected_mission_sha256: str,
    program_state: Mapping[str, Any],
    policy_id: str,
    evidence_bytes: bytes,
    acquisition_manifest_bytes: bytes,
    acquisition_declaration_bytes: bytes,
    source_trust_policy_bytes: bytes,
) -> dict[str, Any]:
    """Qualify an acquisition record only through a pin in exact mission-rooted bytes."""
    expected_mission_sha = _sha256_text(
        expected_mission_sha256, "expected_mission_sha256"
    )
    actual_mission_sha = hashlib.sha256(mission_bytes).hexdigest()
    if actual_mission_sha != expected_mission_sha:
        raise MissionSourceTrustBridgeError(
            "mission bytes do not match the supplied expected mission SHA"
        )

    requested_policy_id = _strict_text(policy_id, "policy_id")
    mission = _normalized_mission(mission_bytes)
    selected_pin = _selected_policy_pin(mission, requested_policy_id)
    _validate_program_projection(
        program_state,
        normalized_mission=mission,
        expected_mission_sha256=expected_mission_sha,
    )

    try:
        qualification = qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence_bytes,
            acquisition_manifest_bytes=acquisition_manifest_bytes,
            acquisition_declaration_bytes=acquisition_declaration_bytes,
            source_trust_policy_bytes=source_trust_policy_bytes,
            expected_source_trust_policy_sha256=selected_pin["sha256"],
        )
    except AcquisitionSourceTrustPolicyError as exc:
        raise MissionSourceTrustBridgeError(
            "acquisition record failed qualification under the mission-pinned source trust policy"
        ) from exc
    bounded_qualification = _validate_downstream_qualification(
        qualification,
        selected_pin=selected_pin,
    )

    return {
        "schema_version": MISSION_SOURCE_TRUST_BRIDGE_SCHEMA_VERSION,
        "mission_sha256": actual_mission_sha,
        "mission_schema_version": _SUPPORTED_MISSION_SCHEMA_VERSION,
        "program_schema_version": _SUPPORTED_PROGRAM_SCHEMA_VERSION,
        "program_policy_version": _SUPPORTED_PROGRAM_POLICY_VERSION,
        "selected_source_trust_policy_pin": dict(selected_pin),
        "acquisition_qualification": bounded_qualification,
        "mission_bytes_match_supplied_expected_sha256": True,
        "program_projection_consistency_established": True,
        "source_trust_policy_pin_bound_under_supplied_expected_mission_sha256": True,
        "expected_mission_sha256_provenance_authenticated_by_this_contract": False,
        "mission_authorship_authenticated": False,
        "program_state_provenance_independently_authenticated": False,
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
    "MISSION_SOURCE_TRUST_BRIDGE_SCHEMA_VERSION",
    "MissionSourceTrustBridgeError",
    "qualify_acquisition_record_under_expected_mission_policy",
]
