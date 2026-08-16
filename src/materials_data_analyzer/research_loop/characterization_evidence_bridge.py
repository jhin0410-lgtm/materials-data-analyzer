"""Independently verify characterization evidence-ladder assessments for research planning.

This consumer intentionally re-validates the producer contract rather than importing the
characterization package or trusting producer readiness flags. It converts only the first
verified blocking level into a planning evidence gap/action; it never authorizes use,
upgrades scientific status, or treats lower-level method evidence as stronger material or
independence evidence.
"""

from __future__ import annotations

import hashlib
import json
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
_EXPECTED_READINESS = {
    "raw_representation_ready": 1,
    "acquisition_provenance_ready": 2,
    "instrument_calibration_ready": 3,
    "method_validation_ready": 4,
    "material_domain_validation_ready": 5,
    "independent_external_validation_ready": 6,
    "replicated_multisource_support_ready": 7,
    "engineering_decision_ready": 8,
}

_BLOCKER_ACTION = {
    "L0_software_integration": (
        "existing_data_reanalysis",
        "Establish the intended characterization software integration path before stronger claims.",
    ),
    "L1_raw_representation_identity": (
        "external_evidence_search",
        "Acquire and byte-bind raw or demonstrably lossless source representation and version identity.",
    ),
    "L2_acquisition_provenance_integrity": (
        "external_evidence_search",
        "Acquire authoritative sample/acquisition identity and processing-lineage evidence without filename or row-order inference.",
    ),
    "L3_instrument_calibration_validity": (
        "external_evidence_search",
        "Acquire traceable instrument, detector, acquisition-setting, and calibration evidence required by the claim.",
    ),
    "L4_method_algorithm_validation": (
        "sensitivity_analysis",
        "Design a predeclared method/reference/sensitivity validation using only verified lower-level evidence.",
    ),
    "L5_material_domain_validation": (
        "external_evidence_search",
        "Acquire exact or explicitly bounded target-material evidence; do not promote a cross-material method benchmark.",
    ),
    "L6_independent_external_validation": (
        "external_evidence_search",
        "Acquire a development- and provenance-disjoint external validation cohort under an explicit independence contract.",
    ),
    "L7_replicated_multisource_support": (
        "replication",
        "Design or acquire provenance-disjoint multi-source/sample/acquisition/facility replication evidence.",
    ),
    "L8_engineering_decision_readiness": (
        "physical_experiment_design",
        "Design operational validation under explicit facility, threshold, failure-mode, and engineering-use constraints.",
    ),
}


class CharacterizationEvidenceBridgeError(AutonomousInquiryError):
    """Raised when producer evidence cannot be independently verified."""


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise CharacterizationEvidenceBridgeError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CharacterizationEvidenceBridgeError(f"{field} must be non-empty text")
    return value.strip()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CharacterizationEvidenceBridgeError(f"{field} must be an object")
    return value


def _list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise CharacterizationEvidenceBridgeError(f"{field} must be a list")
    return value


def _verify_declaration(declaration: Mapping[str, Any]) -> tuple[int, str | None]:
    if declaration.get("schema_version") != PRODUCER_SCHEMA_VERSION:
        raise CharacterizationEvidenceBridgeError("unsupported producer declaration schema_version")
    _text(declaration.get("declaration_id"), "declaration.declaration_id")
    subject = _mapping(declaration.get("subject"), "declaration.subject")
    for field in ("modality", "source_material_domain", "target_material_domain", "claim_scope"):
        _text(subject.get(field), f"declaration.subject.{field}")

    roles: set[str] = set()
    bindings = _list(declaration.get("source_bindings"), "declaration.source_bindings")
    if not bindings:
        raise CharacterizationEvidenceBridgeError("declaration.source_bindings must not be empty")
    for index, raw in enumerate(bindings):
        item = _mapping(raw, f"declaration.source_bindings[{index}]")
        role = _text(item.get("role"), f"declaration.source_bindings[{index}].role")
        if role in roles:
            raise CharacterizationEvidenceBridgeError(f"duplicate source binding role: {role}")
        roles.add(role)
        _sha256(item.get("sha256"), f"declaration.source_bindings[{index}].sha256")

    levels = _mapping(declaration.get("levels"), "declaration.levels")
    if set(levels) != set(LEVELS):
        missing = sorted(set(LEVELS) - set(levels))
        unknown = sorted(set(levels) - set(LEVELS))
        detail = f"missing={missing[0]}" if missing else f"unknown={unknown[0]}"
        raise CharacterizationEvidenceBridgeError(f"declaration.levels contract mismatch: {detail}")

    highest = -1
    encountered_blocker = False
    first_blocker: str | None = None
    for index, level in enumerate(LEVELS):
        record = _mapping(levels[level], f"declaration.levels.{level}")
        assessment = _text(record.get("assessment"), f"declaration.levels.{level}.assessment")
        if assessment not in ASSESSMENTS:
            raise CharacterizationEvidenceBridgeError(f"unsupported level assessment: {assessment}")
        evidence = _list(record.get("evidence"), f"declaration.levels.{level}.evidence")
        limitations = _list(record.get("limitations"), f"declaration.levels.{level}.limitations")
        if any(not isinstance(item, str) or not item.strip() for item in evidence + limitations):
            raise CharacterizationEvidenceBridgeError("level evidence/limitations must contain non-empty text")
        if assessment == "Supported":
            if encountered_blocker:
                raise CharacterizationEvidenceBridgeError(
                    f"{level} cannot be Supported after a lower non-Supported level"
                )
            if not evidence:
                raise CharacterizationEvidenceBridgeError(f"{level} Supported requires explicit evidence")
            highest = index
        else:
            encountered_blocker = True
            if first_blocker is None:
                first_blocker = level
    return highest, first_blocker


def verify_characterization_evidence_assessment(value: Mapping[str, Any]) -> dict[str, Any]:
    """Independently verify producer hashes, monotonicity, readiness, and handoff boundaries."""
    if value.get("schema_version") != PRODUCER_SCHEMA_VERSION:
        raise CharacterizationEvidenceBridgeError("unsupported evidence assessment schema_version")
    if value.get("policy_version") != "1.0":
        raise CharacterizationEvidenceBridgeError("unsupported evidence assessment policy_version")

    claimed_assessment_sha = _sha256(value.get("assessment_sha256"), "assessment_sha256")
    without_assessment_sha = dict(value)
    without_assessment_sha.pop("assessment_sha256", None)
    if _canonical_sha256(without_assessment_sha) != claimed_assessment_sha:
        raise CharacterizationEvidenceBridgeError("assessment_sha256 does not bind exact assessment content")

    declaration = _mapping(value.get("declaration"), "declaration")
    claimed_declaration_sha = _sha256(value.get("declaration_sha256"), "declaration_sha256")
    if _canonical_sha256(declaration) != claimed_declaration_sha:
        raise CharacterizationEvidenceBridgeError("declaration_sha256 mismatch")

    highest_index, first_blocker = _verify_declaration(declaration)
    claimed_index = value.get("highest_contiguous_supported_index")
    if isinstance(claimed_index, bool) or not isinstance(claimed_index, int) or claimed_index != highest_index:
        raise CharacterizationEvidenceBridgeError("highest_contiguous_supported_index mismatch")
    expected_highest = LEVELS[highest_index] if highest_index >= 0 else None
    if value.get("highest_contiguous_supported_level") != expected_highest:
        raise CharacterizationEvidenceBridgeError("highest_contiguous_supported_level mismatch")
    if value.get("first_blocking_level") != first_blocker:
        raise CharacterizationEvidenceBridgeError("first_blocking_level mismatch")

    readiness = _mapping(value.get("readiness"), "readiness")
    if set(readiness) != set(_EXPECTED_READINESS):
        raise CharacterizationEvidenceBridgeError("readiness fields do not match producer contract")
    for field, required_index in _EXPECTED_READINESS.items():
        claimed = readiness[field]
        if not isinstance(claimed, bool) or claimed != (highest_index >= required_index):
            raise CharacterizationEvidenceBridgeError(f"readiness mismatch: {field}")

    handoff = _mapping(value.get("handoff"), "handoff")
    if handoff.get("contract") != PRODUCER_CONTRACT:
        raise CharacterizationEvidenceBridgeError("unexpected characterization handoff contract")
    if handoff.get("schema_version") != PRODUCER_SCHEMA_VERSION:
        raise CharacterizationEvidenceBridgeError("unexpected characterization handoff schema_version")
    if handoff.get("scientific_status_promoted") is not False:
        raise CharacterizationEvidenceBridgeError("producer handoff must not promote scientific status")
    if handoff.get("downstream_use_authorized") is not False:
        raise CharacterizationEvidenceBridgeError("evidence ladder must not authorize downstream use")
    if handoff.get("lower_level_evidence_preserved") is not True:
        raise CharacterizationEvidenceBridgeError("producer must preserve lower-level evidence")
    if handoff.get("highest_supported_level") != expected_highest or handoff.get("first_blocking_level") != first_blocker:
        raise CharacterizationEvidenceBridgeError("handoff level summary mismatch")
    if handoff.get("subject") != declaration.get("subject") or handoff.get("source_bindings") != declaration.get("source_bindings"):
        raise CharacterizationEvidenceBridgeError("handoff subject/source bindings drift from declaration")

    return {
        "assessment_sha256": claimed_assessment_sha,
        "declaration_sha256": claimed_declaration_sha,
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
    blocker = verified.get("first_blocking_level")
    if blocker is None:
        return None
    if blocker not in _BLOCKER_ACTION:
        raise CharacterizationEvidenceBridgeError(f"unsupported blocking level: {blocker}")
    action_class, requirement = _BLOCKER_ACTION[blocker]
    declaration_id = _text(verified.get("declaration_id"), "verified.declaration_id")
    subject = _mapping(verified.get("subject"), "verified.subject")
    gap_id = f"characterization:{declaration_id}:{blocker}"
    gap = {
        "gap_id": gap_id,
        "origin": "independently_verified_characterization_evidence_ladder",
        "requirement": requirement,
        "blocking_level": blocker,
        "modality": subject.get("modality"),
        "source_material_domain": subject.get("source_material_domain"),
        "target_material_domain": subject.get("target_material_domain"),
        "claim_scope": subject.get("claim_scope"),
        "assessment_sha256": verified.get("assessment_sha256"),
        "may_be_filled_by_synthetic_evidence": False,
    }
    raw_action = {
        "action_id": f"{gap_id}:next-action",
        "action_class": action_class,
        "description": requirement,
        "rationale": f"Resolve the first independently verified characterization evidence blocker: {blocker}.",
        "required_evidence": [requirement],
        "expected_outcome": "New evidence that can be re-evaluated through the producer and independent consumer contracts.",
        "execution_mode": "plan_only" if action_class in {"physical_experiment_design", "replication", "sensitivity_analysis"} else "explicit_authorization_required",
        "expected_information_score": 0.85,
        "hypothesis_discrimination_score": 0.8,
        "feasibility_score": 0.55 if action_class == "external_evidence_search" else 0.65,
        "cost_units": 2.5 if action_class == "external_evidence_search" else 3.0,
        "risk_penalty": 0.05,
    }
    return {"gap": gap, "action": _normalize_action(raw_action, origin="characterization_evidence_ladder")}


def apply_characterization_evidence_assessments(
    plan: Mapping[str, Any],
    assessments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Append verified characterization gaps/actions and rerank without granting execution."""
    verified_items = [verify_characterization_evidence_assessment(item) for item in assessments]
    additions = [_gap_from_verified(item) for item in verified_items]
    additions = [item for item in additions if item is not None]

    result = dict(plan)
    gaps = list(result.get("evidence_gaps", []))
    gaps.extend(item["gap"] for item in additions)
    actions = [item for item in result.get("ranked_actions", []) if isinstance(item, Mapping)]
    actions.extend(item["action"] for item in additions)
    ranked = _deduplicate_actions(actions)

    budget = float(_mapping(result.get("planning_budget"), "planning_budget")["budget_units"])
    threshold = float(result["planning_budget"]["minimum_utility"])
    stop = _stop_decision(
        objectives=result.get("research_objectives", []),
        ranked_actions=ranked,
        budget_units=budget,
        minimum_utility=threshold,
    )
    affordable = [
        item for item in ranked
        if float(item["cost_units"]) <= budget and float(item["utility_score"]) >= threshold
    ]
    selected = dict(affordable[0]) if affordable and not stop["stop"] else None

    binding_material = [item["assessment_sha256"] for item in verified_items]
    result.update(
        {
            "evidence_gaps": gaps,
            "ranked_actions": ranked,
            "selected_next_action": selected,
            "stop_decision": stop,
            "characterization_evidence": {
                "schema_version": CHARACTERIZATION_EVIDENCE_BRIDGE_SCHEMA_VERSION,
                "policy_version": CHARACTERIZATION_EVIDENCE_BRIDGE_POLICY_VERSION,
                "assessment_count": len(verified_items),
                "assessment_sha256s": binding_material,
                "composite_binding_sha256": _canonical_sha256(binding_material),
                "verified_assessments": verified_items,
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
        }
    )
    boundary = dict(result.get("autonomy_boundary", {}))
    boundary.update(
        {
            "characterization_evidence_independently_reverified": bool(verified_items),
            "characterization_lower_level_evidence_promoted": False,
            "characterization_downstream_use_inferred": False,
        }
    )
    result["autonomy_boundary"] = boundary
    result.pop("plan_sha256", None)
    result["plan_sha256"] = _canonical_sha256(result)
    return result


def composite_assessment_binding(assessments: Sequence[Mapping[str, Any]]) -> str:
    """Return a deterministic independently verified binding for stagnation control."""
    verified = [verify_characterization_evidence_assessment(item) for item in assessments]
    return _canonical_sha256([item["assessment_sha256"] for item in verified])


__all__ = [
    "CHARACTERIZATION_EVIDENCE_BRIDGE_POLICY_VERSION",
    "CHARACTERIZATION_EVIDENCE_BRIDGE_SCHEMA_VERSION",
    "CharacterizationEvidenceBridgeError",
    "apply_characterization_evidence_assessments",
    "composite_assessment_binding",
    "verify_characterization_evidence_assessment",
]
