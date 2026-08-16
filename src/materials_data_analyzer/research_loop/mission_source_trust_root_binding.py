"""Bind local acquisition-source reliance to exact mission bytes under a supplied root.

This bridge closes the software provenance chain from exact mission bytes to a pinned
source-trust policy and an exact acquisition record. The caller-supplied expected mission
SHA is an explicit root assumption, not something this contract authenticates.
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

MISSION_SOURCE_TRUST_ROOT_BINDING_SCHEMA_VERSION = "1.0"
MISSION_SOURCE_TRUST_ROOT_BINDING_POLICY_VERSION = "1.0"
_EXPECTED_MISSION_SCHEMA_VERSION = "1.1"
_EXPECTED_PROGRAM_SCHEMA_VERSION = "1.1"
_EXPECTED_PROGRAM_POLICY_VERSION = "1.0"


class MissionSourceTrustRootBindingError(ResearchLoopError):
    """Raised when a mission-root-bounded local source-trust chain cannot be established."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MissionSourceTrustRootBindingError(
                f"duplicate JSON key is not allowed in exact mission bytes: {key}"
            )
        result[key] = value
    return result


def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise MissionSourceTrustRootBindingError(f"{field} must be exact bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MissionSourceTrustRootBindingError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise MissionSourceTrustRootBindingError(f"{field} root must be an object")
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise MissionSourceTrustRootBindingError(
            f"{field} must be non-empty text without surrounding whitespace"
        )
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise MissionSourceTrustRootBindingError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return text


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MissionSourceTrustRootBindingError(
            "program state contains non-canonicalizable JSON data"
        ) from exc


def _same_json_value(left: object, right: object) -> bool:
    return _canonical_json(left) == _canonical_json(right)


def _program_mission_binding(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise MissionSourceTrustRootBindingError(
            "program_state.mission_binding must be an object"
        )
    if set(value) != {"path", "sha256"}:
        raise MissionSourceTrustRootBindingError(
            "program_state.mission_binding must use exactly path and sha256"
        )
    path = _strict_text(value["path"], "program_state.mission_binding.path")
    sha256 = _sha256_text(value["sha256"], "program_state.mission_binding.sha256")
    return {"path": path, "sha256": sha256}


def _normalized_pin_list(value: object, *, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise MissionSourceTrustRootBindingError(f"{field} must be a list")
    result: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_shas: set[str] = set()
    for index, raw in enumerate(value):
        item_field = f"{field}[{index}]"
        if not isinstance(raw, Mapping) or set(raw) != {"policy_id", "sha256"}:
            raise MissionSourceTrustRootBindingError(
                f"{item_field} must use exactly policy_id and sha256"
            )
        policy_id = _strict_text(raw["policy_id"], f"{item_field}.policy_id")
        sha256 = _sha256_text(raw["sha256"], f"{item_field}.sha256")
        if policy_id in seen_ids or sha256 in seen_shas:
            raise MissionSourceTrustRootBindingError(
                f"{field} contains duplicate policy identity"
            )
        seen_ids.add(policy_id)
        seen_shas.add(sha256)
        result.append({"policy_id": policy_id, "sha256": sha256})
    return result


def _require_exact_bytes(value: object, field: str) -> bytes:
    if not isinstance(value, bytes):
        raise MissionSourceTrustRootBindingError(f"{field} must be exact bytes")
    return value


def qualify_acquisition_record_under_supplied_mission_root(
    *,
    mission_bytes: bytes,
    program_state: Mapping[str, Any],
    expected_mission_sha256: str,
    policy_id: str,
    source_trust_policy_bytes: bytes,
    evidence_bytes: bytes,
    acquisition_manifest_bytes: bytes,
    acquisition_declaration_bytes: bytes,
) -> dict[str, Any]:
    """Qualify exact local source reliance under an explicitly supplied mission SHA root."""
    mission_bytes = _require_exact_bytes(mission_bytes, "mission_bytes")
    source_trust_policy_bytes = _require_exact_bytes(
        source_trust_policy_bytes,
        "source_trust_policy_bytes",
    )
    evidence_bytes = _require_exact_bytes(evidence_bytes, "evidence_bytes")
    acquisition_manifest_bytes = _require_exact_bytes(
        acquisition_manifest_bytes,
        "acquisition_manifest_bytes",
    )
    acquisition_declaration_bytes = _require_exact_bytes(
        acquisition_declaration_bytes,
        "acquisition_declaration_bytes",
    )

    expected_mission_sha = _sha256_text(
        expected_mission_sha256, "expected_mission_sha256"
    )
    actual_mission_sha = hashlib.sha256(mission_bytes).hexdigest()
    if actual_mission_sha != expected_mission_sha:
        raise MissionSourceTrustRootBindingError(
            "exact mission bytes do not match the supplied expected mission SHA"
        )

    mission_raw = _json_object(mission_bytes, field="exact mission bytes")
    try:
        mission = validate_research_mission(mission_raw)
    except ResearchProgramError as exc:
        raise MissionSourceTrustRootBindingError(
            "exact mission bytes failed mission-contract validation"
        ) from exc
    if mission.get("schema_version") != _EXPECTED_MISSION_SCHEMA_VERSION:
        raise MissionSourceTrustRootBindingError(
            "source-trust policy pins require exact mission schema_version 1.1"
        )

    requested_policy_id = _strict_text(policy_id, "policy_id")
    mission_pins = _normalized_pin_list(
        mission.get("source_trust_policy_pins", []),
        field="exact mission source_trust_policy_pins",
    )
    matching_pins = [
        item for item in mission_pins if item["policy_id"] == requested_policy_id
    ]
    if len(matching_pins) != 1:
        raise MissionSourceTrustRootBindingError(
            "exact mission must contain exactly one requested source-trust policy pin"
        )
    mission_policy_pin = matching_pins[0]
    actual_policy_sha = hashlib.sha256(source_trust_policy_bytes).hexdigest()
    if actual_policy_sha != mission_policy_pin["sha256"]:
        raise MissionSourceTrustRootBindingError(
            "source-trust policy bytes do not match the exact mission policy pin"
        )

    if not isinstance(program_state, Mapping):
        raise MissionSourceTrustRootBindingError("program_state must be an object")
    if program_state.get("schema_version") != _EXPECTED_PROGRAM_SCHEMA_VERSION:
        raise MissionSourceTrustRootBindingError(
            "program_state schema_version must be 1.1 for mission source-trust pins"
        )
    if program_state.get("program_policy_version") != _EXPECTED_PROGRAM_POLICY_VERSION:
        raise MissionSourceTrustRootBindingError(
            "program_state program_policy_version is unsupported"
        )
    program_binding = _program_mission_binding(program_state.get("mission_binding"))
    if program_binding["sha256"] != actual_mission_sha:
        raise MissionSourceTrustRootBindingError(
            "program_state mission_binding SHA does not match exact mission bytes"
        )
    if not _same_json_value(program_state.get("mission"), mission):
        raise MissionSourceTrustRootBindingError(
            "program_state normalized mission does not exactly agree with validated mission bytes"
        )
    program_pins = _normalized_pin_list(
        program_state.get("source_trust_policy_pins"),
        field="program_state.source_trust_policy_pins",
    )
    if not _same_json_value(program_pins, mission_pins):
        raise MissionSourceTrustRootBindingError(
            "program_state source-trust policy pins do not exactly agree with exact mission"
        )

    try:
        local_qualification = qualify_acquisition_record_under_pinned_policy(
            evidence_bytes=evidence_bytes,
            acquisition_manifest_bytes=acquisition_manifest_bytes,
            acquisition_declaration_bytes=acquisition_declaration_bytes,
            source_trust_policy_bytes=source_trust_policy_bytes,
            expected_source_trust_policy_sha256=mission_policy_pin["sha256"],
        )
    except AcquisitionSourceTrustPolicyError as exc:
        raise MissionSourceTrustRootBindingError(
            "exact acquisition record failed mission-pinned local source-trust qualification"
        ) from exc

    if local_qualification.get("source_trust_policy_id") != requested_policy_id:
        raise MissionSourceTrustRootBindingError(
            "source-trust policy internal identity does not match the authenticated mission pin"
        )
    if local_qualification.get("source_trust_policy_sha256") != mission_policy_pin["sha256"]:
        raise MissionSourceTrustRootBindingError(
            "local source-trust qualification SHA does not match the authenticated mission pin"
        )
    if local_qualification.get("local_record_reliance_qualified_under_supplied_pin") is not True:
        raise MissionSourceTrustRootBindingError(
            "local source-trust qualification did not affirm its bounded reliance result"
        )

    return {
        "schema_version": MISSION_SOURCE_TRUST_ROOT_BINDING_SCHEMA_VERSION,
        "binding_policy_version": MISSION_SOURCE_TRUST_ROOT_BINDING_POLICY_VERSION,
        "mission_sha256": actual_mission_sha,
        "mission_schema_version": mission["schema_version"],
        "program_schema_version": program_state["schema_version"],
        "program_policy_version": program_state["program_policy_version"],
        "mission_id": mission["mission_id"],
        "source_trust_policy_id": requested_policy_id,
        "source_trust_policy_sha256": mission_policy_pin["sha256"],
        "matched_source_trust_rule_id": local_qualification["matched_rule_id"],
        "evidence_artifact_sha256": local_qualification["evidence_artifact_sha256"],
        "acquisition_manifest_sha256": local_qualification[
            "acquisition_manifest_sha256"
        ],
        "acquisition_declaration_sha256": local_qualification[
            "acquisition_declaration_sha256"
        ],
        "recorded_source_system": local_qualification["recorded_source_system"],
        "recorded_source_version": local_qualification["recorded_source_version"],
        "recorded_retrieval_endpoint": local_qualification[
            "recorded_retrieval_endpoint"
        ],
        "recorded_retrieval_status": local_qualification["recorded_retrieval_status"],
        "recorded_network_performed": local_qualification["recorded_network_performed"],
        "supplied_expected_mission_sha_matched": True,
        "mission_policy_pin_authenticated_under_supplied_root": True,
        "program_state_agrees_with_exact_mission": True,
        "policy_internal_identity_matches_authenticated_mission_pin": True,
        "local_record_reliance_qualified_under_supplied_mission_root": True,
        "expected_mission_root_provenance_authenticated_by_this_contract": False,
        "full_program_state_provenance_reauthenticated": False,
        "repository_or_release_identity_authenticated": False,
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
    "MISSION_SOURCE_TRUST_ROOT_BINDING_POLICY_VERSION",
    "MISSION_SOURCE_TRUST_ROOT_BINDING_SCHEMA_VERSION",
    "MissionSourceTrustRootBindingError",
    "qualify_acquisition_record_under_supplied_mission_root",
]
