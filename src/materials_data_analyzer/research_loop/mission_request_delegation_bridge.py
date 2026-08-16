"""Authenticate bounded request-delegation policy bytes under an expected mission root.

The caller-supplied expected mission SHA-256 is the external trust root. This module
establishes only consistency between exact mission bytes, their program projection,
a first-class mission policy pin, and exact delegation-policy bytes. It does not
authenticate the root supplier or authorship and grants no execution or scientific
authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .kernel import ResearchLoopError
from .research_program import ResearchProgramError, validate_research_mission

MISSION_REQUEST_DELEGATION_BRIDGE_SCHEMA_VERSION = "1.0"
REQUEST_DELEGATION_POLICY_SCHEMA_VERSION = "1.0"
_SUPPORTED_MISSION_SCHEMA_VERSION = "1.2"
_SUPPORTED_PROGRAM_SCHEMA_VERSION = "1.2"
_SUPPORTED_PROGRAM_POLICY_VERSION = "1.0"
_MISSION_BINDING_KEYS = {"path", "sha256"}
_POLICY_REQUIRED_KEYS = {
    "schema_version",
    "policy_id",
    "adapter_id",
    "allowed_actions",
    "max_cost_units_per_request",
    "network_access",
    "physical_experiment_execution",
    "generic_command_execution",
    "limitations",
}
_POLICY_ALLOWED_KEYS = _POLICY_REQUIRED_KEYS | {"metadata"}
_ACTION_KEYS = {"action_type", "action_version", "max_cost_units"}


class MissionRequestDelegationBridgeError(ResearchLoopError):
    """Raised when mission-rooted delegation-policy trust cannot be established."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MissionRequestDelegationBridgeError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> None:
    raise MissionRequestDelegationBridgeError(
        f"non-standard JSON constant is not allowed: {value}"
    )


def _exact_bytes(value: object, field: str) -> bytes:
    if not isinstance(value, bytes):
        raise MissionRequestDelegationBridgeError(f"{field} must be exact bytes")
    return value


def _json_object(raw: bytes, field: str) -> dict[str, Any]:
    try:
        value = json.loads(
            _exact_bytes(raw, field).decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MissionRequestDelegationBridgeError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise MissionRequestDelegationBridgeError(f"{field} root must be an object")
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MissionRequestDelegationBridgeError(f"{field} must be non-empty text")
    if value != value.strip():
        raise MissionRequestDelegationBridgeError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise MissionRequestDelegationBridgeError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MissionRequestDelegationBridgeError(f"{field} must be a positive integer")
    return value


def _exact_object(
    value: object,
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MissionRequestDelegationBridgeError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise MissionRequestDelegationBridgeError(
            f"{field} is missing required keys: {', '.join(missing)}"
        )
    if unknown:
        raise MissionRequestDelegationBridgeError(
            f"{field} has unknown keys: {', '.join(unknown)}"
        )
    return value


def _same_json_value(left: object, right: object) -> bool:
    """Compare JSON values without Python's bool/int equality aliasing."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        assert isinstance(right, dict)
        return set(left) == set(right) and all(
            _same_json_value(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        assert isinstance(right, list)
        return len(left) == len(right) and all(
            _same_json_value(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _normalized_mission(mission_bytes: bytes) -> dict[str, Any]:
    raw = _json_object(mission_bytes, "research mission")
    try:
        mission = validate_research_mission(raw)
    except ResearchProgramError as exc:
        raise MissionRequestDelegationBridgeError(
            "research mission failed the current mission contract"
        ) from exc
    if mission.get("schema_version") != _SUPPORTED_MISSION_SCHEMA_VERSION:
        raise MissionRequestDelegationBridgeError(
            "mission-rooted request delegation requires mission schema_version 1.2"
        )
    pins = mission.get("request_delegation_policy_pins")
    if not isinstance(pins, list) or not pins:
        raise MissionRequestDelegationBridgeError(
            "authenticated mission bytes must contain first-class request_delegation_policy_pins"
        )
    return mission


def _selected_policy_pin(
    mission: Mapping[str, Any], policy_id: str
) -> dict[str, str]:
    pins = mission.get("request_delegation_policy_pins")
    if not isinstance(pins, list):
        raise MissionRequestDelegationBridgeError(
            "mission request-delegation policy pins are malformed"
        )
    matches = [
        pin
        for pin in pins
        if isinstance(pin, dict) and pin.get("policy_id") == policy_id
    ]
    if len(matches) != 1:
        raise MissionRequestDelegationBridgeError(
            "requested delegation policy ID must match exactly one authenticated mission pin"
        )
    pin = matches[0]
    if set(pin) != {"policy_id", "sha256"}:
        raise MissionRequestDelegationBridgeError(
            "authenticated mission request-delegation policy pin has an unexpected shape"
        )
    return {
        "policy_id": _strict_text(pin["policy_id"], "mission policy pin policy_id"),
        "sha256": _sha256_text(pin["sha256"], "mission policy pin sha256"),
    }


def _validate_program_projection(
    program_state: Mapping[str, Any],
    *,
    mission: Mapping[str, Any],
    expected_mission_sha256: str,
) -> None:
    if not isinstance(program_state, Mapping):
        raise MissionRequestDelegationBridgeError("program_state must be an object")
    if program_state.get("schema_version") != _SUPPORTED_PROGRAM_SCHEMA_VERSION:
        raise MissionRequestDelegationBridgeError(
            "program_state schema_version is not the pinned request-delegation bridge version"
        )
    if program_state.get("program_policy_version") != _SUPPORTED_PROGRAM_POLICY_VERSION:
        raise MissionRequestDelegationBridgeError(
            "program_state program_policy_version is not the pinned bridge-compatible version"
        )
    binding = program_state.get("mission_binding")
    if not isinstance(binding, Mapping) or set(binding) != _MISSION_BINDING_KEYS:
        raise MissionRequestDelegationBridgeError(
            "program_state.mission_binding must use exactly path and sha256"
        )
    _strict_text(binding["path"], "program_state.mission_binding.path")
    if _sha256_text(
        binding["sha256"], "program_state.mission_binding.sha256"
    ) != expected_mission_sha256:
        raise MissionRequestDelegationBridgeError(
            "program_state mission binding does not match the supplied expected mission SHA"
        )
    projected_mission = program_state.get("mission")
    if not isinstance(projected_mission, dict) or not _same_json_value(
        projected_mission, mission
    ):
        raise MissionRequestDelegationBridgeError(
            "program_state normalized mission does not match the authenticated mission bytes"
        )
    for key, expected in (
        ("request_delegation_policy_pins", mission["request_delegation_policy_pins"]),
        ("source_trust_policy_pins", mission.get("source_trust_policy_pins", [])),
    ):
        projected = program_state.get(key)
        if not isinstance(projected, list) or not _same_json_value(projected, expected):
            raise MissionRequestDelegationBridgeError(
                f"program_state projected {key.replace('_', '-')} do not match the authenticated mission"
            )


def _normalize_policy(
    policy_bytes: bytes, selected_pin: Mapping[str, str]
) -> tuple[dict[str, Any], str]:
    exact = _exact_bytes(policy_bytes, "request_delegation_policy_bytes")
    digest = hashlib.sha256(exact).hexdigest()
    if digest != selected_pin["sha256"]:
        raise MissionRequestDelegationBridgeError(
            "request-delegation policy bytes do not match the authenticated mission pin"
        )
    policy = _exact_object(
        _json_object(exact, "request-delegation policy"),
        required=_POLICY_REQUIRED_KEYS,
        allowed=_POLICY_ALLOWED_KEYS,
        field="request-delegation policy",
    )
    if policy["schema_version"] != REQUEST_DELEGATION_POLICY_SCHEMA_VERSION:
        raise MissionRequestDelegationBridgeError(
            "unsupported request-delegation policy schema_version"
        )
    policy_id = _strict_text(policy["policy_id"], "request-delegation policy policy_id")
    if policy_id != selected_pin["policy_id"]:
        raise MissionRequestDelegationBridgeError(
            "request-delegation policy ID does not match the authenticated mission pin"
        )
    adapter_id = _strict_text(policy["adapter_id"], "request-delegation policy adapter_id")
    request_cost = _positive_int(
        policy["max_cost_units_per_request"],
        "request-delegation policy max_cost_units_per_request",
    )
    for field in (
        "network_access",
        "physical_experiment_execution",
        "generic_command_execution",
    ):
        if policy[field] is not False:
            raise MissionRequestDelegationBridgeError(
                f"request-delegation policy must set {field}=false"
            )
    raw_actions = policy["allowed_actions"]
    if not isinstance(raw_actions, list) or not raw_actions:
        raise MissionRequestDelegationBridgeError(
            "request-delegation policy allowed_actions must be a non-empty list"
        )
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw_action in enumerate(raw_actions):
        action = _exact_object(
            raw_action,
            required=_ACTION_KEYS,
            allowed=_ACTION_KEYS,
            field=f"request-delegation policy allowed_actions[{index}]",
        )
        action_type = _strict_text(action["action_type"], f"allowed_actions[{index}].action_type")
        action_version = _strict_text(
            action["action_version"], f"allowed_actions[{index}].action_version"
        )
        key = (action_type, action_version)
        if key in seen:
            raise MissionRequestDelegationBridgeError(
                "request-delegation policy contains duplicate action/version entries"
            )
        seen.add(key)
        actions.append(
            {
                "action_type": action_type,
                "action_version": action_version,
                "max_cost_units": _positive_int(
                    action["max_cost_units"], f"allowed_actions[{index}].max_cost_units"
                ),
            }
        )
    raw_limitations = policy["limitations"]
    if not isinstance(raw_limitations, list) or not raw_limitations:
        raise MissionRequestDelegationBridgeError(
            "delegation policy limitations must be a non-empty list"
        )
    limitations: list[str] = []
    for index, item in enumerate(raw_limitations):
        text = _strict_text(item, f"delegation policy limitations[{index}]")
        if text in limitations:
            raise MissionRequestDelegationBridgeError(
                "delegation policy limitations must not contain duplicates"
            )
        limitations.append(text)
    normalized: dict[str, Any] = {
        "schema_version": REQUEST_DELEGATION_POLICY_SCHEMA_VERSION,
        "policy_id": policy_id,
        "adapter_id": adapter_id,
        "allowed_actions": actions,
        "max_cost_units_per_request": request_cost,
        "network_access": False,
        "physical_experiment_execution": False,
        "generic_command_execution": False,
        "limitations": limitations,
    }
    if "metadata" in policy:
        if not isinstance(policy["metadata"], dict):
            raise MissionRequestDelegationBridgeError(
                "request-delegation policy metadata must be an object when provided"
            )
        normalized["metadata"] = policy["metadata"]
    return normalized, digest


def authenticate_request_delegation_policy_under_expected_mission_root(
    *,
    mission_bytes: bytes,
    expected_mission_sha256: str,
    program_state: Mapping[str, Any],
    policy_id: str,
    request_delegation_policy_bytes: bytes,
) -> dict[str, Any]:
    """Authenticate exact bounded delegation-policy bytes under a supplied mission root."""
    exact_mission = _exact_bytes(mission_bytes, "mission_bytes")
    expected = _sha256_text(expected_mission_sha256, "expected_mission_sha256")
    actual = hashlib.sha256(exact_mission).hexdigest()
    if actual != expected:
        raise MissionRequestDelegationBridgeError(
            "mission bytes do not match the supplied expected mission SHA"
        )
    mission = _normalized_mission(exact_mission)
    selected_pin = _selected_policy_pin(mission, _strict_text(policy_id, "policy_id"))
    _validate_program_projection(
        program_state, mission=mission, expected_mission_sha256=expected
    )
    policy, policy_sha = _normalize_policy(
        request_delegation_policy_bytes, selected_pin
    )
    return {
        "schema_version": MISSION_REQUEST_DELEGATION_BRIDGE_SCHEMA_VERSION,
        "mission_sha256": actual,
        "mission_schema_version": _SUPPORTED_MISSION_SCHEMA_VERSION,
        "program_schema_version": _SUPPORTED_PROGRAM_SCHEMA_VERSION,
        "program_policy_version": _SUPPORTED_PROGRAM_POLICY_VERSION,
        "request_delegation_policy_id": selected_pin["policy_id"],
        "request_delegation_policy_sha256": policy_sha,
        "selected_request_delegation_policy_pin": dict(selected_pin),
        "normalized_request_delegation_policy": policy,
        "mission_bytes_match_supplied_expected_sha256": True,
        "program_projection_consistency_established": True,
        "request_delegation_policy_pin_bound_under_supplied_expected_mission_sha256": True,
        "request_delegation_policy_bytes_match_authenticated_pin": True,
        "expected_mission_sha256_provenance_authenticated_by_this_contract": False,
        "expected_mission_root_supplier_authenticated": False,
        "mission_authorship_authenticated": False,
        "delegation_policy_authorship_authenticated": False,
        "human_authorship_authenticated": False,
        "operator_identity_authenticated": False,
        "machine_request_authorship_authorized": False,
        "execution_authorized": False,
        "network_access_authorized": False,
        "physical_experiment_execution_authorized": False,
        "generic_command_execution_authorized": False,
        "scientific_evidence_upgraded": False,
        "scientific_status_changed": False,
        "empirical_authority_granted": False,
        "positive_closeout_granted": False,
        "bridge_limitations": [
            "The supplied expected mission SHA-256 is an external trust root whose supplier and channel are not authenticated by this contract.",
            "The authenticated delegation policy is a bounded data contract and does not authorize machine request authorship or execution.",
            "Scientific evidence, empirical authority, scientific status, and positive closeout are unchanged.",
        ],
    }


__all__ = [
    "MISSION_REQUEST_DELEGATION_BRIDGE_SCHEMA_VERSION",
    "REQUEST_DELEGATION_POLICY_SCHEMA_VERSION",
    "MissionRequestDelegationBridgeError",
    "authenticate_request_delegation_policy_under_expected_mission_root",
]
