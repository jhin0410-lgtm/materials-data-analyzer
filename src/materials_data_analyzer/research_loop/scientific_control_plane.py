"""Strict public facade for the canonical scientific control-plane contract.

The reviewed 1.2 architecture tables remain preserved in ``scientific_control_plane_impl``.
This facade closes the remaining compatibility-boundary gaps: legacy projections are accepted
only from the exact authenticated whole mission bytes, execution-bearing structured mission
fields receive deterministic Science/Governance projections, known controller action limits are
explicit, and contract validation is type-exact rather than Python-equality based.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from . import scientific_control_plane_impl as _impl

CONTROL_PLANE_SCHEMA_VERSION = _impl.CONTROL_PLANE_SCHEMA_VERSION
CONTROL_PLANE_POLICY_VERSION = _impl.CONTROL_PLANE_POLICY_VERSION
CANONICAL_RESEARCH_STATE_ENTITIES = _impl.CANONICAL_RESEARCH_STATE_ENTITIES
CANONICAL_RESEARCH_STAGES = _impl.CANONICAL_RESEARCH_STAGES
CANONICAL_TERMINAL_CLASSES = _impl.CANONICAL_TERMINAL_CLASSES
GOVERNANCE_RUN_STOP_REASONS = _impl.GOVERNANCE_RUN_STOP_REASONS
SCIENCE_PLANE_RESPONSIBILITIES = _impl.SCIENCE_PLANE_RESPONSIBILITIES
GOVERNANCE_PLANE_RESPONSIBILITIES = _impl.GOVERNANCE_PLANE_RESPONSIBILITIES
PROVIDER_TO_EVIDENCE_FLOW = _impl.PROVIDER_TO_EVIDENCE_FLOW
CONTROLLER_CLASSIFICATIONS = _impl.CONTROLLER_CLASSIFICATIONS
ControllerRecord = _impl.ControllerRecord
LegacyStopProjection = _impl.LegacyStopProjection
LegacyMissionFieldProjection = _impl.LegacyMissionFieldProjection
LegacyMissionItemProjection = _impl.LegacyMissionItemProjection
LEGACY_STOP_STATUS_COMPATIBILITY = _impl.LEGACY_STOP_STATUS_COMPATIBILITY
LEGACY_MISSION_FIELD_PROJECTIONS = _impl.LEGACY_MISSION_FIELD_PROJECTIONS
LEGACY_MISSION_ITEM_PROJECTIONS = _impl.LEGACY_MISSION_ITEM_PROJECTIONS
ScientificControlPlaneError = _impl.ScientificControlPlaneError

_IN625_MISSION_ID = "autonomous-in625-production-v1"
_IN625_MISSION_SHA256 = "7de1c78d1411805623a4687a6d1956517edc009abe5790a0870e89ab6ccb4e88"

# The implementation inventory is immutable. Replace only the one previously unknown hard bound.
CONTROLLER_INVENTORY = tuple(
    ControllerRecord(
        record.surface_id,
        record.classification,
        record.role,
        32 if record.surface_id == "policy_authorized_closed_loop" else record.maximum_actions_per_call,
        record.automatic_looping,
        record.scientific_authority_applied,
    )
    for record in _impl.CONTROLLER_INVENTORY
)

# These tables classify the exact execution-bearing structured fields of the current legacy
# mission. Values themselves come only from the authenticated whole mission bytes below.
_WORKSTREAM_FIELD_SEMANTICS = (
    ("workstream_id", "scientific_workstream_identity", "governance_workstream_identity"),
    ("adapter_id", None, "execution_adapter_selection"),
    ("priority", "scientific_goal_priority", None),
    ("role", "scientific_workstream_role", None),
    ("enabled", "scientific_goal_enabled", "execution_route_enabled"),
)

_METADATA_FIELD_SEMANTICS = (
    ("production_profile", None, "production_profile_identity"),
    ("execution_adapter", None, "execution_adapter_selection"),
    (
        "initial_expected_action_class",
        "expected_scientific_action_progression",
        "execution_route_guard",
    ),
    (
        "post_acquisition_expected_action_class",
        "expected_scientific_action_progression",
        "execution_route_guard",
    ),
    (
        "post_comparability_expected_action_class",
        "expected_scientific_action_progression",
        "execution_route_guard",
    ),
    (
        "post_nist_expected_action_class",
        "expected_scientific_action_progression",
        "execution_route_guard",
    ),
    (
        "post_geometry_mapping_expected_action_class",
        "expected_scientific_action_progression",
        "execution_route_guard",
    ),
    (
        "post_bridge_expected_action_class",
        "expected_scientific_action_progression",
        "execution_route_guard",
    ),
    (
        "post_source_discovery_expected_action_class",
        "expected_scientific_action_progression",
        "execution_route_guard",
    ),
    ("evidence_source_scope", "eligible_scientific_evidence_classes", None),
    (
        "scientific_closeout_expected_in_first_profile",
        "scientific_closeout_expectation",
        None,
    ),
    (
        "post_candidate_acquisition_expected_action_class",
        "expected_scientific_action_progression",
        "execution_route_guard",
    ),
    (
        "post_reference_chain_expected_action_class",
        "expected_scientific_action_progression",
        "execution_route_guard",
    ),
)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScientificControlPlaneError(f"duplicate legacy mission JSON key: {key}")
        result[key] = value
    return result


def _authenticated_legacy_mission(mission_bytes: bytes) -> dict[str, Any]:
    if type(mission_bytes) is not bytes:
        raise ScientificControlPlaneError("legacy mission binding requires exact raw bytes")
    observed_sha = hashlib.sha256(mission_bytes).hexdigest()
    if observed_sha != _IN625_MISSION_SHA256:
        raise ScientificControlPlaneError("legacy mission bytes do not match the frozen mission SHA-256")
    try:
        value = json.loads(
            mission_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScientificControlPlaneError("legacy mission bytes must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ScientificControlPlaneError("legacy mission root must be an object")

    # Validation is deliberately performed on the complete artifact, not caller-selected fields.
    from .research_program import ResearchProgramError, validate_research_mission

    try:
        validated = validate_research_mission(value)
    except ResearchProgramError as exc:
        raise ScientificControlPlaneError("legacy mission failed current whole-mission validation") from exc
    if validated.get("mission_id") != _IN625_MISSION_ID:
        raise ScientificControlPlaneError("legacy mission identity drifted")
    return dict(validated)


def _typed_equal(observed: object, expected: object) -> bool:
    if isinstance(expected, bool):
        return type(observed) is bool and observed is expected
    if isinstance(expected, int):
        return type(observed) is int and observed == expected
    if expected is None or isinstance(expected, str):
        return type(observed) is type(expected) and observed == expected
    if isinstance(expected, list):
        return isinstance(observed, list) and len(observed) == len(expected) and all(
            _typed_equal(left, right) for left, right in zip(observed, expected, strict=True)
        )
    if isinstance(expected, Mapping):
        if not isinstance(observed, Mapping) or set(observed) != set(expected):
            return False
        return all(_typed_equal(observed[key], expected[key]) for key in expected)
    return type(observed) is type(expected) and observed == expected


def _controller_dict(record: ControllerRecord) -> dict[str, Any]:
    return {
        "surface_id": record.surface_id,
        "classification": record.classification,
        "role": record.role,
        "maximum_actions_per_call": record.maximum_actions_per_call,
        "automatic_looping": record.automatic_looping,
        "scientific_authority_applied": record.scientific_authority_applied,
    }


def _field_projection_dict() -> dict[str, dict[str, Any]]:
    return _impl._legacy_mission_field_projection_dict()


def _item_projection_list() -> list[dict[str, Any]]:
    return _impl._legacy_mission_item_projection_list()


def _structured_semantics(
    rows: tuple[tuple[str, str | None, str | None], ...],
) -> list[dict[str, str | None]]:
    return [
        {
            "source_key": key,
            "science_semantic": science,
            "governance_semantic": governance,
        }
        for key, science, governance in rows
    ]


def project_legacy_stop_status(stop_status: str) -> dict[str, Any]:
    return _impl.project_legacy_stop_status(stop_status)


def project_legacy_mission_field(*, mission_bytes: bytes) -> dict[str, Any]:
    """Project the composite legacy mission field only from the authenticated whole artifact."""
    mission = _authenticated_legacy_mission(mission_bytes)
    mission_id = mission.get("mission_id")
    mission_text = mission.get("mission")
    matches = [
        record
        for record in LEGACY_MISSION_FIELD_PROJECTIONS
        if record.mission_id == mission_id
        and record.source_field == "mission"
        and record.source_text == mission_text
    ]
    if len(matches) != 1:
        raise ScientificControlPlaneError(
            "legacy mission field has no exact deterministic Science/Governance classification"
        )
    record = matches[0]
    return {
        "mission_id": record.mission_id,
        "mission_sha256": _IN625_MISSION_SHA256,
        "source_field": record.source_field,
        "source_text": record.source_text,
        "science_projection": record.science_projection,
        "governance_projection": record.governance_projection,
        "whole_mission_validated": True,
        "historical_artifact_rewritten": False,
        "scientific_status_promoted": False,
        "execution_authority_granted": False,
    }


def project_legacy_mission_item(
    *, mission_bytes: bytes, collection: str, item_index: int
) -> dict[str, Any]:
    """Project one exact list item after authenticating and validating the whole mission."""
    if type(item_index) is not int:
        raise ScientificControlPlaneError("legacy mission item_index must be a non-boolean integer")
    mission = _authenticated_legacy_mission(mission_bytes)
    items = mission.get(collection)
    if not isinstance(items, list) or item_index < 0 or item_index >= len(items):
        raise ScientificControlPlaneError("legacy mission item is outside the authenticated collection")
    item_text = items[item_index]
    if not isinstance(item_text, str):
        raise ScientificControlPlaneError("legacy mission item must be exact text")
    matches = [
        record
        for record in LEGACY_MISSION_ITEM_PROJECTIONS
        if record.mission_id == mission["mission_id"]
        and record.collection == collection
        and record.item_index == item_index
        and record.item_text == item_text
    ]
    if len(matches) != 1:
        raise ScientificControlPlaneError(
            "legacy mission item has no exact deterministic Science/Governance classification"
        )
    record = matches[0]
    return {
        "mission_id": record.mission_id,
        "mission_sha256": _IN625_MISSION_SHA256,
        "collection": record.collection,
        "item_index": record.item_index,
        "item_text": record.item_text,
        "science_semantic": record.science_semantic,
        "governance_semantic": record.governance_semantic,
        "whole_mission_validated": True,
        "historical_artifact_rewritten": False,
        "scientific_status_promoted": False,
        "execution_authority_granted": False,
    }


def project_legacy_mission_workstream(
    *, mission_bytes: bytes, item_index: int
) -> dict[str, Any]:
    """Split one exact legacy workstream into non-authority-crossing projections."""
    if type(item_index) is not int:
        raise ScientificControlPlaneError("legacy workstream item_index must be a non-boolean integer")
    mission = _authenticated_legacy_mission(mission_bytes)
    workstreams = mission.get("workstreams")
    if not isinstance(workstreams, list) or item_index < 0 or item_index >= len(workstreams):
        raise ScientificControlPlaneError("legacy workstream is outside the authenticated mission")
    raw = workstreams[item_index]
    if not isinstance(raw, Mapping):
        raise ScientificControlPlaneError("legacy workstream must be an object")
    expected_keys = {row[0] for row in _WORKSTREAM_FIELD_SEMANTICS}
    if set(raw) != expected_keys:
        raise ScientificControlPlaneError("legacy workstream field set drifted")
    science: dict[str, Any] = {}
    governance: dict[str, Any] = {}
    for key, science_name, governance_name in _WORKSTREAM_FIELD_SEMANTICS:
        if science_name is not None:
            science[science_name] = raw[key]
        if governance_name is not None:
            governance[governance_name] = raw[key]
    return {
        "mission_id": mission["mission_id"],
        "mission_sha256": _IN625_MISSION_SHA256,
        "collection": "workstreams",
        "item_index": item_index,
        "science_projection": science,
        "governance_projection": governance,
        "whole_mission_validated": True,
        "science_projection_may_modify_execution_policy": False,
        "execution_authority_granted": False,
    }


def project_legacy_mission_metadata(*, mission_bytes: bytes, source_key: str) -> dict[str, Any]:
    """Classify one exact metadata key from the authenticated whole legacy mission."""
    mission = _authenticated_legacy_mission(mission_bytes)
    metadata = mission.get("metadata")
    if not isinstance(metadata, Mapping) or source_key not in metadata:
        raise ScientificControlPlaneError("legacy metadata key is outside the authenticated mission")
    matches = [row for row in _METADATA_FIELD_SEMANTICS if row[0] == source_key]
    if len(matches) != 1:
        raise ScientificControlPlaneError("legacy metadata key has no deterministic classification")
    _, science, governance = matches[0]
    return {
        "mission_id": mission["mission_id"],
        "mission_sha256": _IN625_MISSION_SHA256,
        "source_field": "metadata",
        "source_key": source_key,
        "source_value": metadata[source_key],
        "science_semantic": science,
        "governance_semantic": governance,
        "whole_mission_validated": True,
        "scientific_status_promoted": False,
        "execution_authority_granted": False,
    }


def build_scientific_control_plane_contract() -> dict[str, Any]:
    result = _impl.build_scientific_control_plane_contract()
    result["controller_inventory"] = [_controller_dict(item) for item in CONTROLLER_INVENTORY]
    semantics = dict(result["mission_projection_semantics"])
    semantics.update(
        {
            "authenticated_whole_mission_binding_required": True,
            "legacy_mission_raw_sha256": {_IN625_MISSION_ID: _IN625_MISSION_SHA256},
            "structured_projection_required_for": ["workstreams", "metadata"],
            "workstream_field_semantics": _structured_semantics(_WORKSTREAM_FIELD_SEMANTICS),
            "metadata_field_semantics": _structured_semantics(_METADATA_FIELD_SEMANTICS),
        }
    )
    result["mission_projection_semantics"] = semantics
    return result


def validate_scientific_control_plane_contract(value: object) -> dict[str, Any]:
    """Validate the contract with exact nested types and immutable expected semantics."""
    if not isinstance(value, Mapping):
        raise ScientificControlPlaneError("scientific control-plane contract must be an object")
    _impl._exact_keys(value, _impl._REQUIRED_CONTRACT_KEYS, field="scientific control-plane contract")
    expected = build_scientific_control_plane_contract()

    for field in (
        "schema_version",
        "policy_version",
        "canonical_research_state_entities",
        "canonical_research_stages",
        "canonical_terminal_classes",
        "governance_run_stop_reasons",
        "science_plane_responsibilities",
        "governance_plane_responsibilities",
        "provider_to_evidence_flow",
        "controller_classifications",
        "controller_inventory",
        "legacy_stop_status_compatibility",
        "mission_projection_semantics",
        "diagnostic_transition_semantics",
        "readiness_projection_semantics",
        "authority_boundary",
    ):
        if not _typed_equal(value.get(field), expected[field]):
            raise ScientificControlPlaneError(f"{field} drifted from the canonical contract")

    science = set(value["science_plane_responsibilities"])
    governance = set(value["governance_plane_responsibilities"])
    if science & governance:
        raise ScientificControlPlaneError("science and governance responsibilities must be disjoint")
    if set(value["canonical_terminal_classes"]) & set(value["governance_run_stop_reasons"]):
        raise ScientificControlPlaneError(
            "scientific terminal classes and governance stop reasons must be disjoint"
        )
    return expected


__all__ = [
    "CANONICAL_RESEARCH_STAGES",
    "CANONICAL_RESEARCH_STATE_ENTITIES",
    "CANONICAL_TERMINAL_CLASSES",
    "CONTROL_PLANE_POLICY_VERSION",
    "CONTROL_PLANE_SCHEMA_VERSION",
    "CONTROLLER_CLASSIFICATIONS",
    "CONTROLLER_INVENTORY",
    "ControllerRecord",
    "GOVERNANCE_PLANE_RESPONSIBILITIES",
    "GOVERNANCE_RUN_STOP_REASONS",
    "LEGACY_MISSION_FIELD_PROJECTIONS",
    "LEGACY_MISSION_ITEM_PROJECTIONS",
    "LEGACY_STOP_STATUS_COMPATIBILITY",
    "LegacyMissionFieldProjection",
    "LegacyMissionItemProjection",
    "LegacyStopProjection",
    "PROVIDER_TO_EVIDENCE_FLOW",
    "SCIENCE_PLANE_RESPONSIBILITIES",
    "ScientificControlPlaneError",
    "build_scientific_control_plane_contract",
    "project_legacy_mission_field",
    "project_legacy_mission_item",
    "project_legacy_mission_metadata",
    "project_legacy_mission_workstream",
    "project_legacy_stop_status",
    "validate_scientific_control_plane_contract",
]
