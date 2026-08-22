"""Public policy boundary for discrepancy-to-planning handoff.

The structural handoff already prevents proposal injection into the current executable
frontier. This wrapper additionally requires the source discrepancy report to pass the
complete public physics/provenance hardening policy before any future-planning objective
is projected.

A diagnostic action class is not necessarily an executor/planner action category. This
policy may therefore apply a *narrow, explicit semantic translation* after source
validation. The translation preserves the original diagnostic class and the exact
scientific blocker while projecting only an execution-category-compatible planning class.
It never asserts candidate availability, selects an action, binds a registry, or grants
execution authority.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .discrepancy_planning_handoff import (
    DISCREPANCY_PLANNING_HANDOFF_POLICY_VERSION,
    DISCREPANCY_PLANNING_HANDOFF_SCHEMA_VERSION,
    DiscrepancyPlanningHandoffError,
    build_discrepancy_planning_handoff as _build_structural_handoff,
    validate_discrepancy_planning_handoff as _validate_structural_handoff,
)
from .model_evidence_discrepancy_physics_policy import (
    validate_physics_hardened_model_evidence_discrepancy_report,
)

DISCREPANCY_PLANNING_HANDOFF_HARDENING_POLICY_VERSION = "1.2"
SEMANTIC_ACTION_CLASS_TRANSLATION_SCHEMA_VERSION = "1.0"
SEMANTIC_ACTION_CLASS_TRANSLATION_POLICY_VERSION = "1.0"

# These are scientific-semantics-to-planner-category translations, not aliases. Every
# translation is guarded by the exact discrepancy diagnosis/gate that makes it meaningful.
# Adding a mapping is therefore a policy change requiring explicit tests and review.
_SEMANTIC_ACTION_CLASS_TRANSLATIONS: dict[str, dict[str, str]] = {
    "numerical_validation": {
        "planner_action_class": "simulation",
        "required_diagnosis": "numerical_invalidity",
        "required_failed_gate": "numerical_validity",
        "translation_id": "numerical-validation-via-audited-simulation-v1",
    },
}


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DiscrepancyPlanningHandoffError(
            "policy-hardened planning handoff must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DiscrepancyPlanningHandoffError(f"{field} must be an object")
    return value


def _text_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise DiscrepancyPlanningHandoffError(f"{field} must be a list of non-empty text")
    return list(value)


def _apply_semantic_action_class_translations(
    structural_handoff: Mapping[str, Any],
) -> dict[str, Any]:
    """Translate only explicitly allowlisted diagnostic classes into planner categories."""
    value = copy.deepcopy(dict(structural_handoff))
    diagnosis = _mapping(value.get("diagnosis_context"), "planning_handoff.diagnosis_context")
    diagnosis_types = set(
        _text_list(diagnosis.get("diagnosis_types"), "diagnosis_context.diagnosis_types")
    )
    failed_gates = set(
        _text_list(diagnosis.get("failed_gates"), "diagnosis_context.failed_gates")
    )
    objectives = value.get("research_objectives")
    if not isinstance(objectives, list):
        raise DiscrepancyPlanningHandoffError(
            "planning_handoff.research_objectives must be a list"
        )

    translated_objective_ids: list[str] = []
    for index, raw in enumerate(objectives):
        objective = _mapping(raw, f"planning_handoff.research_objectives[{index}]")
        source_class = objective.get("research_action_class")
        if not isinstance(source_class, str) or not source_class:
            raise DiscrepancyPlanningHandoffError(
                f"research_objectives[{index}].research_action_class must be non-empty text"
            )
        translation = _SEMANTIC_ACTION_CLASS_TRANSLATIONS.get(source_class)
        if translation is None:
            continue
        required_diagnosis = translation["required_diagnosis"]
        required_failed_gate = translation["required_failed_gate"]
        if required_diagnosis not in diagnosis_types:
            raise DiscrepancyPlanningHandoffError(
                "semantic action-class translation lacks its required discrepancy diagnosis"
            )
        if required_failed_gate not in failed_gates:
            raise DiscrepancyPlanningHandoffError(
                "semantic action-class translation lacks its required failed discrepancy gate"
            )
        objective_id = objective.get("objective_id")
        if not isinstance(objective_id, str) or not objective_id:
            raise DiscrepancyPlanningHandoffError(
                f"research_objectives[{index}].objective_id must be non-empty text"
            )
        planner_class = translation["planner_action_class"]
        objective["source_research_action_class"] = source_class
        objective["research_action_class"] = planner_class
        objective["semantic_action_class_translation"] = {
            "schema_version": SEMANTIC_ACTION_CLASS_TRANSLATION_SCHEMA_VERSION,
            "policy_version": SEMANTIC_ACTION_CLASS_TRANSLATION_POLICY_VERSION,
            "translation_id": translation["translation_id"],
            "source_diagnostic_action_class": source_class,
            "planner_action_class": planner_class,
            "required_diagnosis": required_diagnosis,
            "required_failed_gate": required_failed_gate,
            "diagnostic_semantics_preserved": True,
            "candidate_availability_asserted": False,
            "registry_binding_created": False,
            "action_authorization_granted": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
        }
        translated_objective_ids.append(objective_id)

    if translated_objective_ids:
        value["planner_semantic_bridge"] = {
            "schema_version": SEMANTIC_ACTION_CLASS_TRANSLATION_SCHEMA_VERSION,
            "policy_version": SEMANTIC_ACTION_CLASS_TRANSLATION_POLICY_VERSION,
            "translated_objective_ids": translated_objective_ids,
            "translation_count": len(translated_objective_ids),
            "candidate_availability_asserted": False,
            "registry_binding_created": False,
            "action_authorization_granted": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
        }

    value.pop("handoff_sha256", None)
    value["handoff_sha256"] = _canonical_sha256(value)
    return value


def _verify_policy_handoff_integrity(handoff: Mapping[str, Any]) -> str:
    value = dict(_mapping(handoff, "planning_handoff"))
    embedded = value.pop("handoff_sha256", None)
    if (
        not isinstance(embedded, str)
        or len(embedded) != 64
        or embedded != embedded.lower()
        or any(char not in "0123456789abcdef" for char in embedded)
    ):
        raise DiscrepancyPlanningHandoffError(
            "planning_handoff.handoff_sha256 must be lowercase SHA-256"
        )
    if _canonical_sha256(value) != embedded:
        raise DiscrepancyPlanningHandoffError(
            "policy-hardened planning handoff canonical SHA-256 does not match its content"
        )
    return embedded


def build_policy_hardened_discrepancy_planning_handoff(
    discrepancy_report: Mapping[str, Any],
    *,
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build future-planning context only after full discrepancy validation."""
    validate_physics_hardened_model_evidence_discrepancy_report(
        discrepancy_report,
        evaluated_graph=evaluated_graph,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_report=previous_discrepancy_report,
    )
    structural = _build_structural_handoff(
        discrepancy_report,
        evaluated_graph=evaluated_graph,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    return _apply_semantic_action_class_translations(structural)


def validate_policy_hardened_discrepancy_planning_handoff(
    handoff: Mapping[str, Any],
    *,
    discrepancy_report: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Revalidate source provenance/physics, structural handoff, and semantic projection."""
    discrepancy = validate_physics_hardened_model_evidence_discrepancy_report(
        discrepancy_report,
        evaluated_graph=evaluated_graph,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_report=previous_discrepancy_report,
    )
    structural = _build_structural_handoff(
        discrepancy_report,
        evaluated_graph=evaluated_graph,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    structural_result = _validate_structural_handoff(
        structural,
        discrepancy_report=discrepancy_report,
        evaluated_graph=evaluated_graph,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    rebuilt = _apply_semantic_action_class_translations(structural)
    embedded = _verify_policy_handoff_integrity(handoff)
    if dict(handoff) != rebuilt:
        raise DiscrepancyPlanningHandoffError(
            "policy-hardened planning handoff differs from validated semantic projection"
        )
    bridge = rebuilt.get("planner_semantic_bridge")
    translation_count = 0
    if bridge is not None:
        bridge_map = _mapping(bridge, "planning_handoff.planner_semantic_bridge")
        count = bridge_map.get("translation_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise DiscrepancyPlanningHandoffError(
                "planner_semantic_bridge.translation_count must be an integer >= 1"
            )
        translation_count = count
    return {
        **structural_result,
        "handoff_sha256": embedded,
        "source_discrepancy_hardening_verified": True,
        "source_discrepancy_physics_hardening_verified": True,
        "source_discrepancy_report_sha256": discrepancy["report_sha256"],
        "semantic_action_class_translation_policy_version": (
            SEMANTIC_ACTION_CLASS_TRANSLATION_POLICY_VERSION
        ),
        "semantic_action_class_translation_count": translation_count,
        "semantic_translation_created_execution_authority": False,
    }


build_discrepancy_planning_handoff = build_policy_hardened_discrepancy_planning_handoff
validate_discrepancy_planning_handoff = (
    validate_policy_hardened_discrepancy_planning_handoff
)


__all__ = [
    "DISCREPANCY_PLANNING_HANDOFF_HARDENING_POLICY_VERSION",
    "DISCREPANCY_PLANNING_HANDOFF_POLICY_VERSION",
    "DISCREPANCY_PLANNING_HANDOFF_SCHEMA_VERSION",
    "SEMANTIC_ACTION_CLASS_TRANSLATION_POLICY_VERSION",
    "SEMANTIC_ACTION_CLASS_TRANSLATION_SCHEMA_VERSION",
    "DiscrepancyPlanningHandoffError",
    "build_discrepancy_planning_handoff",
    "build_policy_hardened_discrepancy_planning_handoff",
    "validate_discrepancy_planning_handoff",
    "validate_policy_hardened_discrepancy_planning_handoff",
]
