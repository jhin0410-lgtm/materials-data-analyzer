"""Independently verify characterization evidence-ladder assessments for research planning.

The consumer revalidates producer bytes and semantics instead of importing producer code or
trusting producer readiness flags. Only the first verified blocking level can influence
planning. This module never authorizes downstream use or upgrades scientific status.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .autonomous_inquiry import (
    AutonomousInquiryError,
    _canonical_sha256,
    _deduplicate_actions,
    _normalize_action,
    _stop_decision,
)

CHARACTERIZATION_EVIDENCE_BRIDGE_SCHEMA_VERSION = "1.0"
CHARACTERIZATION_EVIDENCE_BRIDGE_POLICY_VERSION = "1.0"
PRODUCER_CONTRACT = "materials-characterization-scientific-evidence-ladder"
PRODUCER_SCHEMA_VERSION = "1.0"
PRODUCER_POLICY_VERSION = "1.0"
LEVELS = (
    "L0_software_integration",
    "L1_raw_representation_identity",
    "L2_acquisition_provenance_integrity",
    "L3_instrument_calibration_validity",
    "L4_method_algorithm_validation",
    "L5_material_domain_validation",
    "L6_independent_external_validation",
    "L7_replicated_multisource_support",
    "L8_engineering_decision_readiness",
)
ASSESSMENTS = {"Supported", "Diagnostic", "Inconclusive", "Unsupported"}
_ROOT_FIELDS = {
    "schema_version", "policy_version", "declaration", "declaration_sha256",
    "highest_contiguous_supported_level", "highest_contiguous_supported_index",
    "first_blocking_level", "non_supported_levels", "readiness", "handoff",
    "policy_boundary", "assessment_sha256",
}
_DECLARATION_FIELDS = {"schema_version", "declaration_id", "subject", "source_bindings", "levels", "limitations"}
_SUBJECT_FIELDS = {"modality", "source_material_domain", "target_material_domain", "claim_scope"}
_BINDING_FIELDS = {"role", "sha256"}
_LEVEL_FIELDS = {"assessment", "evidence", "limitations", "description"}
_NON_SUPPORTED_FIELDS = {"level", "assessment", "limitations"}
_READINESS_INDEX = {
    "raw_representation_ready": 1,
    "acquisition_provenance_ready": 2,
    "instrument_calibration_ready": 3,
    "method_validation_ready": 4,
    "material_domain_validation_ready": 5,
    "independent_external_validation_ready": 6,
    "replicated_multisource_support_ready": 7,
    "engineering_decision_ready": 8,
}
_POLICY_BOUNDARY_FIELDS = {
    "cross_material_proxy_promoted_to_target_material_validation",
    "software_validation_promoted_to_measurement_truth",
    "simulation_promoted_to_empirical_truth",
    "independence_inferred_from_file_count",
    "engineering_readiness_inferred",
}
_BLOCKER_ACTION = {
    "L0_software_integration": ("existing_data_reanalysis", "Establish the intended characterization software integration path before stronger claims."),
    "L1_raw_representation_identity": ("external_evidence_search", "Acquire and byte-bind raw or demonstrably lossless source representation and version identity."),
    "L2_acquisition_provenance_integrity": ("external_evidence_search", "Acquire authoritative sample/acquisition identity and processing-lineage evidence without filename or row-order inference."),
    "L3_instrument_calibration_validity": ("external_evidence_search", "Acquire traceable instrument, detector, acquisition-setting, and calibration evidence required by the claim."),
    "L4_method_algorithm_validation": ("sensitivity_analysis", "Design a predeclared method/reference/sensitivity validation using only verified lower-level evidence."),
    "L5_material_domain_validation": ("external_evidence_search", "Acquire exact or explicitly bounded target-material evidence; do not promote a cross-material method benchmark."),
    "L6_independent_external_validation": ("external_evidence_search", "Acquire a development- and provenance-disjoint external validation cohort under an explicit independence contract."),
    "L7_replicated_multisource_support": ("replication", "Design or acquire provenance-disjoint multi-source/sample/acquisition/facility replication evidence."),
    "L8_engineering_decision_readiness": ("physical_experiment_design", "Design operational validation under explicit facility, threshold, failure-mode, and engineering-use constraints."),
}


class CharacterizationEvidenceBridgeError(AutonomousInquiryError):
    """Raised when characterization evidence cannot be independently verified."""


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CharacterizationEvidenceBridgeError(f"{field} must be an object")
    return value


def _exact(value: object, expected: set[str], field: str) -> Mapping[str, Any]:
    item = _mapping(value, field)
    missing = sorted(expected - set(item))
    unknown = sorted(set(item) - expected)
    if missing:
        raise CharacterizationEvidenceBridgeError(f"{field} missing field: {missing[0]}")
    if unknown:
        raise CharacterizationEvidenceBridgeError(f"{field} unknown field: {unknown[0]}")
    return item


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CharacterizationEvidenceBridgeError(f"{field} must be non-empty text")
    return value.strip()


def _text_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise CharacterizationEvidenceBridgeError(f"{field} must be a list")
    result: list[str] = []
    for index, raw in enumerate(value):
        text = _text(raw, f"{field}[{index}]")
        if text in result:
            raise CharacterizationEvidenceBridgeError(f"{field} contains duplicate text")
        result.append(text)
    return result


def _sha256(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise CharacterizationEvidenceBridgeError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _verify_declaration(value: object) -> tuple[dict[str, Any], int, str | None]:
    declaration = _exact(value, _DECLARATION_FIELDS, "declaration")
    if declaration["schema_version"] != PRODUCER_SCHEMA_VERSION:
        raise CharacterizationEvidenceBridgeError("unsupported producer declaration schema_version")
    _text(declaration["declaration_id"], "declaration.declaration_id")
    subject = _exact(declaration["subject"], _SUBJECT_FIELDS, "declaration.subject")
    for field in sorted(_SUBJECT_FIELDS):
        _text(subject[field], f"declaration.subject.{field}")
    bindings = declaration["source_bindings"]
    if not isinstance(bindings, list) or not bindings:
        raise CharacterizationEvidenceBridgeError("declaration.source_bindings must be a non-empty list")
    roles: set[str] = set()
    for index, raw in enumerate(bindings):
        binding = _exact(raw, _BINDING_FIELDS, f"declaration.source_bindings[{index}]")
        role = _text(binding["role"], f"declaration.source_bindings[{index}].role")
        if role in roles:
            raise CharacterizationEvidenceBridgeError(f"duplicate source binding role: {role}")
        roles.add(role)
        _sha256(binding["sha256"], f"declaration.source_bindings[{index}].sha256")
    _text_list(declaration["limitations"], "declaration.limitations")

    levels = _mapping(declaration["levels"], "declaration.levels")
    if set(levels) != set(LEVELS):
        raise CharacterizationEvidenceBridgeError("declaration.levels must contain exactly L0-L8")
    highest = -1
    first_blocker: str | None = None
    blocked = False
    for index, level in enumerate(LEVELS):
        record = _exact(levels[level], _LEVEL_FIELDS, f"declaration.levels.{level}")
        assessment = _text(record["assessment"], f"declaration.levels.{level}.assessment")
        if assessment not in ASSESSMENTS:
            raise CharacterizationEvidenceBridgeError(f"unsupported level assessment: {assessment}")
        evidence = _text_list(record["evidence"], f"declaration.levels.{level}.evidence")
        _text_list(record["limitations"], f"declaration.levels.{level}.limitations")
        _text(record["description"], f"declaration.levels.{level}.description")
        if assessment == "Supported":
            if blocked:
                raise CharacterizationEvidenceBridgeError(f"{level} cannot be Supported after a lower non-Supported level")
            if not evidence:
                raise CharacterizationEvidenceBridgeError(f"{level} Supported requires explicit evidence")
            highest = index
        else:
            blocked = True
            if first_blocker is None:
                first_blocker = level
    return dict(declaration), highest, first_blocker


def verify_characterization_evidence_assessment(value: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute producer hashes, summaries, monotonicity, readiness and policy boundaries."""
    root = _exact(value, _ROOT_FIELDS, "assessment")
    if root["schema_version"] != PRODUCER_SCHEMA_VERSION or root["policy_version"] != PRODUCER_POLICY_VERSION:
        raise CharacterizationEvidenceBridgeError("unsupported evidence assessment version")
    claimed_assessment = _sha256(root["assessment_sha256"], "assessment_sha256")
    assessment_without_hash = dict(root)
    assessment_without_hash.pop("assessment_sha256")
    if _canonical_sha256(assessment_without_hash) != claimed_assessment:
        raise CharacterizationEvidenceBridgeError("assessment_sha256 does not bind exact assessment content")

    declaration, highest_index, first_blocker = _verify_declaration(root["declaration"])
    claimed_declaration = _sha256(root["declaration_sha256"], "declaration_sha256")
    if _canonical_sha256(declaration) != claimed_declaration:
        raise CharacterizationEvidenceBridgeError("declaration_sha256 mismatch")
    expected_highest = LEVELS[highest_index] if highest_index >= 0 else None
    if root["highest_contiguous_supported_index"] != highest_index:
        raise CharacterizationEvidenceBridgeError("highest_contiguous_supported_index mismatch")
    if root["highest_contiguous_supported_level"] != expected_highest:
        raise CharacterizationEvidenceBridgeError("highest_contiguous_supported_level mismatch")
    if root["first_blocking_level"] != first_blocker:
        raise CharacterizationEvidenceBridgeError("first_blocking_level mismatch")

    expected_non_supported = [
        {
            "level": level,
            "assessment": declaration["levels"][level]["assessment"],
            "limitations": declaration["levels"][level]["limitations"],
        }
        for level in LEVELS
        if declaration["levels"][level]["assessment"] != "Supported"
    ]
    raw_non_supported = root["non_supported_levels"]
    if not isinstance(raw_non_supported, list):
        raise CharacterizationEvidenceBridgeError("non_supported_levels must be a list")
    for index, raw in enumerate(raw_non_supported):
        _exact(raw, _NON_SUPPORTED_FIELDS, f"non_supported_levels[{index}]")
    if raw_non_supported != expected_non_supported:
        raise CharacterizationEvidenceBridgeError("non_supported_levels summary mismatch")

    readiness = _exact(root["readiness"], set(_READINESS_INDEX), "readiness")
    for field, threshold in _READINESS_INDEX.items():
        if not isinstance(readiness[field], bool) or readiness[field] != (highest_index >= threshold):
            raise CharacterizationEvidenceBridgeError(f"readiness mismatch: {field}")

    handoff = _mapping(root["handoff"], "handoff")
    expected_handoff_fields = {
        "contract", "schema_version", "subject", "source_bindings", "highest_supported_level",
        "first_blocking_level", "scientific_status_promoted", "downstream_use_authorized",
        "lower_level_evidence_preserved",
    }
    _exact(handoff, expected_handoff_fields, "handoff")
    if handoff["contract"] != PRODUCER_CONTRACT or handoff["schema_version"] != PRODUCER_SCHEMA_VERSION:
        raise CharacterizationEvidenceBridgeError("unexpected characterization handoff contract")
    if handoff["scientific_status_promoted"] is not False:
        raise CharacterizationEvidenceBridgeError("producer handoff must not promote scientific status")
    if handoff["downstream_use_authorized"] is not False:
        raise CharacterizationEvidenceBridgeError("evidence ladder must not authorize downstream use")
    if handoff["lower_level_evidence_preserved"] is not True:
        raise CharacterizationEvidenceBridgeError("producer must preserve lower-level evidence")
    if handoff["highest_supported_level"] != expected_highest or handoff["first_blocking_level"] != first_blocker:
        raise CharacterizationEvidenceBridgeError("handoff level summary mismatch")
    if handoff["subject"] != declaration["subject"] or handoff["source_bindings"] != declaration["source_bindings"]:
        raise CharacterizationEvidenceBridgeError("handoff subject/source bindings drift from declaration")

    boundary = _exact(root["policy_boundary"], _POLICY_BOUNDARY_FIELDS, "policy_boundary")
    for field in sorted(_POLICY_BOUNDARY_FIELDS):
        if boundary[field] is not False:
            raise CharacterizationEvidenceBridgeError(f"producer policy boundary violated: {field}")

    return {
        "assessment_sha256": claimed_assessment,
        "declaration_sha256": claimed_declaration,
        "declaration_id": declaration["declaration_id"],
        "subject": dict(declaration["subject"]),
        "source_bindings": [dict(item) for item in declaration["source_bindings"]],
        "highest_supported_level": expected_highest,
        "highest_supported_index": highest_index,
        "first_blocking_level": first_blocker,
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
    }


def _gap_from_verified(verified: Mapping[str, Any]) -> dict[str, Any] | None:
    blocker = verified["first_blocking_level"]
    if blocker is None:
        return None
    action_class, requirement = _BLOCKER_ACTION[blocker]
    declaration_id = _text(verified["declaration_id"], "verified.declaration_id")
    subject = _mapping(verified["subject"], "verified.subject")
    gap_id = f"characterization:{declaration_id}:{blocker}"
    gap = {
        "gap_id": gap_id,
        "origin": "independently_verified_characterization_evidence_ladder",
        "requirement": requirement,
        "blocking_level": blocker,
        "modality": subject["modality"],
        "source_material_domain": subject["source_material_domain"],
        "target_material_domain": subject["target_material_domain"],
        "claim_scope": subject["claim_scope"],
        "assessment_sha256": verified["assessment_sha256"],
        "may_be_filled_by_synthetic_evidence": False,
    }
    execution_mode = (
        "plan_only"
        if action_class in {"physical_experiment_design", "replication", "sensitivity_analysis", "existing_data_reanalysis"}
        else "explicit_authorization_required"
    )
    action = _normalize_action(
        {
            "action_id": f"{gap_id}:next-action",
            "action_class": action_class,
            "description": requirement,
            "rationale": f"Resolve the first independently verified characterization evidence blocker: {blocker}.",
            "required_evidence": [requirement],
            "expected_outcome": "New evidence that can be re-evaluated through producer and independent consumer contracts.",
            "execution_mode": execution_mode,
            "expected_information_score": 0.85,
            "hypothesis_discrimination_score": 0.8,
            "feasibility_score": 0.55 if action_class == "external_evidence_search" else 0.65,
            "cost_units": 2.5 if action_class == "external_evidence_search" else 3.0,
            "risk_penalty": 0.05,
        },
        origin="characterization_evidence_ladder",
    )
    return {"gap": gap, "action": action}


def apply_characterization_evidence_assessments(
    plan: Mapping[str, Any], assessments: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Append independently verified blocker gaps/actions and rerank without execution authority."""
    verified = [verify_characterization_evidence_assessment(item) for item in assessments]
    additions = [item for item in (_gap_from_verified(item) for item in verified) if item]
    result = dict(plan)
    result["evidence_gaps"] = list(result.get("evidence_gaps", [])) + [item["gap"] for item in additions]
    ranked = _deduplicate_actions(
        [item for item in result.get("ranked_actions", []) if isinstance(item, Mapping)]
        + [item["action"] for item in additions]
    )
    budget_record = _mapping(result["planning_budget"], "planning_budget")
    budget = float(budget_record["budget_units"])
    threshold = float(budget_record["minimum_utility"])
    stop = _stop_decision(
        objectives=result.get("research_objectives", []), ranked_actions=ranked,
        budget_units=budget, minimum_utility=threshold,
    )
    affordable = [
        item for item in ranked
        if float(item["cost_units"]) <= budget and float(item["utility_score"]) >= threshold
    ]
    selected = dict(affordable[0]) if affordable and not stop["stop"] else None
    hashes = [item["assessment_sha256"] for item in verified]
    result.update({
        "ranked_actions": ranked,
        "selected_next_action": selected,
        "stop_decision": stop,
        "characterization_evidence": {
            "schema_version": CHARACTERIZATION_EVIDENCE_BRIDGE_SCHEMA_VERSION,
            "policy_version": CHARACTERIZATION_EVIDENCE_BRIDGE_POLICY_VERSION,
            "assessment_count": len(verified),
            "assessment_sha256s": hashes,
            "composite_binding_sha256": _canonical_sha256(hashes),
            "verified_assessments": verified,
            "first_blocker_gaps_added": len(additions),
            "producer_scientific_status_promoted": False,
            "downstream_use_authorized": False,
        },
        "handoff": {
            "required_for_selected_action": selected is not None,
            "destination": "existing_independent_action_authorization_and_typed_executor_chain",
            "request_compiled": False,
            "execution_performed": False,
        },
    })
    boundary = dict(result.get("autonomy_boundary", {}))
    boundary.update({
        "characterization_evidence_independently_reverified": bool(verified),
        "characterization_lower_level_evidence_promoted": False,
        "characterization_downstream_use_inferred": False,
    })
    result["autonomy_boundary"] = boundary
    result.pop("plan_sha256", None)
    result["plan_sha256"] = _canonical_sha256(result)
    return result


def composite_assessment_binding(assessments: Sequence[Mapping[str, Any]]) -> str:
    """Return a deterministic binding over independently verified assessment identities."""
    verified = [verify_characterization_evidence_assessment(item) for item in assessments]
    return _canonical_sha256([item["assessment_sha256"] for item in verified])


__all__ = [
    "CHARACTERIZATION_EVIDENCE_BRIDGE_POLICY_VERSION",
    "CHARACTERIZATION_EVIDENCE_BRIDGE_SCHEMA_VERSION",
    "CharacterizationEvidenceBridgeError",
    "LEVELS",
    "apply_characterization_evidence_assessments",
    "composite_assessment_binding",
    "verify_characterization_evidence_assessment",
]
