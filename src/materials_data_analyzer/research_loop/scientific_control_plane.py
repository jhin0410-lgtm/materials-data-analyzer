"""Canonical architecture contract for the Autonomous Research Scientist control plane.

This module is intentionally additive. It does not replace historical research-loop,
planning-transition, or autonomous-production artifacts. Instead it fixes the architecture
vocabulary those implementations project into while preserving their exact historical replay
semantics.

The central boundary is deliberately asymmetric:

* the science plane decides what research action *should* be attempted;
* the governance plane decides whether that already-selected action *may* execute.

Neither plane may grant the other's authority. Provider execution, architecture metadata,
readiness projections, and successful transport are therefore never sufficient to promote a
scientific claim.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CONTROL_PLANE_SCHEMA_VERSION = "1.0"
CONTROL_PLANE_POLICY_VERSION = "1.0"

CANONICAL_RESEARCH_STATE_ENTITIES = (
    "research_question",
    "bounded_mission",
    "hypothesis",
    "observation",
    "derived_result",
    "evidence",
    "claim",
    "inference",
    "contradiction",
    "comparability_assessment",
    "uncertainty_state",
    "evidence_gap",
    "candidate_action",
    "decision",
    "stop_state",
)

CANONICAL_RESEARCH_STAGES = (
    "define_or_load_mission",
    "form_or_load_hypotheses",
    "map_verified_evidence_and_gaps",
    "generate_action_frontier",
    "select_scientific_action",
    "authorize_selected_action",
    "execute_authorized_action",
    "independently_verify_result",
    "ingest_verified_evidence",
    "apply_epistemic_update",
    "critique_and_falsify",
    "replan",
    "classify_stop_or_continue",
)

CANONICAL_TERMINAL_CLASSES = (
    "converged",
    "decision_threshold_reached",
    "irreducible_uncertainty",
    "contradictory_evidence",
    "blocked_external_evidence",
    "review_required",
    "resource_budget_exhausted",
    "marginal_information_value_too_low",
    "authorization_or_safety_blocked",
)

SCIENCE_PLANE_RESPONSIBILITIES = (
    "research_questions_and_hypotheses",
    "observations_derived_results_evidence_and_claims",
    "contradictions_and_alternative_hypotheses",
    "comparability",
    "uncertainty",
    "evidence_gap_diagnosis",
    "scientific_action_value",
    "scientific_stopping_semantics",
)

GOVERNANCE_PLANE_RESPONSIBILITIES = (
    "provenance_authentication",
    "source_and_access_policy",
    "execution_authorization",
    "execution_limits",
    "resource_budgets",
    "filesystem_and_transaction_integrity",
    "operational_recovery_and_audit",
)

PROVIDER_TO_EVIDENCE_FLOW = (
    "provider_or_executor",
    "raw_artifact_bundle",
    "independent_domain_validator",
    "validated_evidence_packet",
    "epistemic_kernel",
)

CONTROLLER_CLASSIFICATIONS = (
    "canonical_primitive",
    "compatibility_facade",
    "domain_implementation",
    "deprecated_or_internal_migration_target",
)

CONTROLLER_INVENTORY = (
    {
        "surface_id": "immutable_research_loop_kernel",
        "classification": "canonical_primitive",
        "role": "append_only_authenticated_research_state_and_ledger",
        "maximum_actions_per_call": 0,
        "automatic_looping": False,
    },
    {
        "surface_id": "mission_level_research_program",
        "classification": "canonical_primitive",
        "role": "mission_state_and_reasoning_proposal_contract",
        "maximum_actions_per_call": 0,
        "automatic_looping": False,
    },
    {
        "surface_id": "research_cycle",
        "classification": "canonical_primitive",
        "role": "safe_single_authorized_action_step_then_one_replan",
        "maximum_actions_per_call": 1,
        "automatic_looping": False,
    },
    {
        "surface_id": "policy_authorized_closed_loop",
        "classification": "compatibility_facade",
        "role": "bounded_controller_over_historical_planning_and_authorization_contracts",
        "maximum_actions_per_call": None,
        "automatic_looping": True,
    },
    {
        "surface_id": "autonomous_production_extensions",
        "classification": "domain_implementation",
        "role": "mission_pinned_real_evidence_production_extensions",
        "maximum_actions_per_call": None,
        "automatic_looping": True,
    },
    {
        "surface_id": "planning_adapter_facade",
        "classification": "compatibility_facade",
        "role": "historical_and_typed_domain_planning_projection",
        "maximum_actions_per_call": 0,
        "automatic_looping": False,
    },
    {
        "surface_id": "authenticated_epistemic_transition",
        "classification": "canonical_primitive",
        "role": "authenticated_verified_evidence_to_epistemic_state_transition",
        "maximum_actions_per_call": 0,
        "automatic_looping": False,
    },
)

# Historical planning stop values are deliberately not rewritten. Some old values map
# unambiguously to the canonical vocabulary; others require semantic evidence from the
# historical reason/blocker before a stronger terminal class may be asserted.
LEGACY_STOP_STATUS_COMPATIBILITY: dict[str, dict[str, Any]] = {
    "continue": {
        "automatic_progress_stopped": False,
        "canonical_terminal_class": None,
        "semantic_refinement_required": False,
    },
    "manual_review_gate": {
        "automatic_progress_stopped": True,
        "canonical_terminal_class": "review_required",
        "semantic_refinement_required": False,
    },
    "operationally_blocked": {
        "automatic_progress_stopped": True,
        "canonical_terminal_class": None,
        "semantic_refinement_required": True,
    },
    "terminal_for_current_scope": {
        "automatic_progress_stopped": True,
        "canonical_terminal_class": None,
        "semantic_refinement_required": True,
    },
}

_REQUIRED_CONTRACT_KEYS = frozenset(
    {
        "schema_version",
        "policy_version",
        "canonical_research_state_entities",
        "canonical_research_stages",
        "canonical_terminal_classes",
        "science_plane_responsibilities",
        "governance_plane_responsibilities",
        "provider_to_evidence_flow",
        "controller_classifications",
        "controller_inventory",
        "legacy_stop_status_compatibility",
        "readiness_projection_semantics",
        "authority_boundary",
    }
)


class ScientificControlPlaneError(ValueError):
    """Raised when the canonical control-plane architecture contract is malformed."""


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], *, field: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        raise ScientificControlPlaneError(
            f"{field} must use the exact key set; unknown={unknown}, missing={missing}"
        )


def _unique_text_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ScientificControlPlaneError(f"{field} must be a non-empty list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            raise ScientificControlPlaneError(f"{field}[{index}] must be exact non-empty text")
        if item in result:
            raise ScientificControlPlaneError(f"{field} must not contain duplicates")
        result.append(item)
    return result


def project_legacy_stop_status(stop_status: str) -> dict[str, Any]:
    """Project one historical planning stop status without inventing stronger semantics."""

    if not isinstance(stop_status, str) or not stop_status.strip() or stop_status != stop_status.strip():
        raise ScientificControlPlaneError("legacy stop status must be exact non-empty text")
    if stop_status not in LEGACY_STOP_STATUS_COMPATIBILITY:
        raise ScientificControlPlaneError(f"unsupported legacy stop status: {stop_status!r}")
    return {
        "legacy_stop_status": stop_status,
        **LEGACY_STOP_STATUS_COMPATIBILITY[stop_status],
        "historical_artifact_rewritten": False,
        "scientific_status_promoted": False,
    }


def build_scientific_control_plane_contract() -> dict[str, Any]:
    """Return the deterministic architecture contract consumed by docs/tests/tooling."""

    return {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "policy_version": CONTROL_PLANE_POLICY_VERSION,
        "canonical_research_state_entities": list(CANONICAL_RESEARCH_STATE_ENTITIES),
        "canonical_research_stages": list(CANONICAL_RESEARCH_STAGES),
        "canonical_terminal_classes": list(CANONICAL_TERMINAL_CLASSES),
        "science_plane_responsibilities": list(SCIENCE_PLANE_RESPONSIBILITIES),
        "governance_plane_responsibilities": list(GOVERNANCE_PLANE_RESPONSIBILITIES),
        "provider_to_evidence_flow": list(PROVIDER_TO_EVIDENCE_FLOW),
        "controller_classifications": list(CONTROLLER_CLASSIFICATIONS),
        "controller_inventory": [dict(item) for item in CONTROLLER_INVENTORY],
        "legacy_stop_status_compatibility": {
            key: dict(value) for key, value in LEGACY_STOP_STATUS_COMPATIBILITY.items()
        },
        "readiness_projection_semantics": {
            "readiness_projection_is_canonical_research_state": False,
            "characterization_l0_l8_is_readiness_projection": True,
            "readiness_projection_may_authorize_downstream_use": False,
            "readiness_projection_may_promote_scientific_status": False,
        },
        "authority_boundary": {
            "architecture_metadata_creates_empirical_evidence": False,
            "architecture_metadata_promotes_scientific_status": False,
            "architecture_metadata_authorizes_execution": False,
            "science_plane_grants_execution_authority": False,
            "governance_plane_grants_scientific_authority": False,
            "provider_self_validates_scientific_truth": False,
            "successful_transport_establishes_scientific_validity": False,
        },
    }


def validate_scientific_control_plane_contract(value: object) -> dict[str, Any]:
    """Fail closed if an architecture contract widens or conflates scientific authority."""

    if not isinstance(value, Mapping):
        raise ScientificControlPlaneError("scientific control-plane contract must be an object")
    _exact_keys(value, _REQUIRED_CONTRACT_KEYS, field="scientific control-plane contract")
    expected = build_scientific_control_plane_contract()

    if value.get("schema_version") != CONTROL_PLANE_SCHEMA_VERSION:
        raise ScientificControlPlaneError("unsupported scientific control-plane schema_version")
    if value.get("policy_version") != CONTROL_PLANE_POLICY_VERSION:
        raise ScientificControlPlaneError("unsupported scientific control-plane policy_version")

    list_fields = (
        "canonical_research_state_entities",
        "canonical_research_stages",
        "canonical_terminal_classes",
        "science_plane_responsibilities",
        "governance_plane_responsibilities",
        "provider_to_evidence_flow",
        "controller_classifications",
    )
    for field in list_fields:
        observed = _unique_text_list(value.get(field), field=field)
        if observed != expected[field]:
            raise ScientificControlPlaneError(f"{field} drifted from the canonical contract")

    science = set(value["science_plane_responsibilities"])
    governance = set(value["governance_plane_responsibilities"])
    if science & governance:
        raise ScientificControlPlaneError("science and governance responsibilities must be disjoint")

    for field in (
        "controller_inventory",
        "legacy_stop_status_compatibility",
        "readiness_projection_semantics",
        "authority_boundary",
    ):
        if value.get(field) != expected[field]:
            raise ScientificControlPlaneError(f"{field} drifted from the canonical contract")

    return expected


__all__ = [
    "CANONICAL_RESEARCH_STAGES",
    "CANONICAL_RESEARCH_STATE_ENTITIES",
    "CANONICAL_TERMINAL_CLASSES",
    "CONTROL_PLANE_POLICY_VERSION",
    "CONTROL_PLANE_SCHEMA_VERSION",
    "CONTROLLER_CLASSIFICATIONS",
    "CONTROLLER_INVENTORY",
    "GOVERNANCE_PLANE_RESPONSIBILITIES",
    "LEGACY_STOP_STATUS_COMPATIBILITY",
    "PROVIDER_TO_EVIDENCE_FLOW",
    "SCIENCE_PLANE_RESPONSIBILITIES",
    "ScientificControlPlaneError",
    "build_scientific_control_plane_contract",
    "project_legacy_stop_status",
    "validate_scientific_control_plane_contract",
]
