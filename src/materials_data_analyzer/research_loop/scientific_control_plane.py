"""Canonical architecture contract for the Autonomous Research Scientist control plane.

This module is additive and preserves historical replay. It freezes the target semantic
boundaries without pretending that every existing controller already implements the target.

Two authority planes are orthogonal:

* Science decides what research action should be attempted and what scientific meaning may be
  assigned to independently validated evidence.
* Governance decides whether the already-selected action may execute under authenticated policy,
  provenance, resource, and safety constraints.

Authentication, transport success, provider output, readiness projections, and diagnostic
transition bundles never become scientific truth by themselves.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

CONTROL_PLANE_SCHEMA_VERSION = "1.1"
CONTROL_PLANE_POLICY_VERSION = "1.1"

CANONICAL_RESEARCH_STATE_ENTITIES = (
    "research_question",
    "scientific_mission",
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
)

CANONICAL_RESEARCH_STAGES = (
    "define_or_load_scientific_mission",
    "form_or_load_hypotheses",
    "map_verified_evidence_and_gaps",
    "generate_action_frontier",
    "select_scientific_action",
    "authorize_selected_action",
    "execute_authorized_action",
    "independently_verify_result",
    "ingest_validated_evidence_packet",
    "apply_authority_bearing_epistemic_update",
    "critique_and_falsify",
    "replan",
    "classify_scientific_stop_or_continue",
)

# These are scientific stopping dispositions. They are deliberately not run lifecycle states.
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
    "research_questions",
    "scientific_mission_objective_scope_and_success_criteria",
    "hypotheses",
    "observations_derived_results_evidence_and_claims",
    "inference_formation_and_assessment",
    "contradictions_and_alternative_hypotheses",
    "comparability",
    "uncertainty",
    "evidence_gap_diagnosis",
    "scientific_action_value",
    "scientific_stopping_semantics",
)

GOVERNANCE_PLANE_RESPONSIBILITIES = (
    "provenance_authentication",
    "autonomy_access_and_delegation_policy",
    "source_and_access_policy",
    "execution_authorization",
    "execution_limits",
    "resource_budgets",
    "filesystem_and_transaction_integrity",
    "operational_recovery_and_audit",
    "run_lifecycle_recording",
)

PROVIDER_TO_EVIDENCE_FLOW = (
    "provider_or_executor",
    "raw_artifact_bundle",
    "independent_domain_validator",
    "validated_evidence_packet",
    "authority_bearing_epistemic_update",
    "epistemic_kernel",
)

CONTROLLER_CLASSIFICATIONS = (
    "canonical_primitive",
    "compatibility_facade",
    "domain_implementation",
    "deprecated_or_internal_migration_target",
)


class ControllerRecord(NamedTuple):
    surface_id: str
    classification: str
    role: str
    maximum_actions_per_call: int | None
    automatic_looping: bool
    scientific_authority_applied: bool | None


# NamedTuple entries make the frozen inventory immutable in place. Builders do not derive their
# expected value from mutable dictionaries that an importer can silently alter.
CONTROLLER_INVENTORY = (
    ControllerRecord(
        "immutable_research_loop_kernel",
        "canonical_primitive",
        "append_only_authenticated_research_state_and_ledger",
        0,
        False,
        None,
    ),
    ControllerRecord(
        "mission_level_research_program",
        "compatibility_facade",
        "legacy_composite_scientific_mission_and_governance_policy_contract",
        0,
        False,
        None,
    ),
    ControllerRecord(
        "research_cycle",
        "canonical_primitive",
        "safe_single_authorized_action_step_then_one_replan",
        1,
        False,
        None,
    ),
    ControllerRecord(
        "bounded_multicycle_controller",
        "compatibility_facade",
        "installed_finite_predeclared_request_controller_over_research_cycle",
        32,
        True,
        None,
    ),
    ControllerRecord(
        "epistemically_bounded_multicycle_controller",
        "compatibility_facade",
        "installed_epistemic_graph_gated_finite_controller_over_research_cycle",
        32,
        True,
        None,
    ),
    ControllerRecord(
        "mission_authorized_evidence_loop",
        "domain_implementation",
        "installed_mission_policy_bounded_external_evidence_loop",
        None,
        True,
        None,
    ),
    ControllerRecord(
        "persistent_research_episode",
        "canonical_primitive",
        "persistent_operational_episode_and_iteration_checkpointing",
        0,
        False,
        None,
    ),
    ControllerRecord(
        "policy_authorized_closed_loop",
        "compatibility_facade",
        "bounded_controller_over_historical_planning_and_authorization_contracts",
        None,
        True,
        None,
    ),
    ControllerRecord(
        "autonomous_production_extensions",
        "domain_implementation",
        "mission_pinned_real_evidence_production_extensions",
        None,
        True,
        None,
    ),
    ControllerRecord(
        "planning_adapter_facade",
        "compatibility_facade",
        "historical_and_typed_domain_planning_projection",
        0,
        False,
        None,
    ),
    ControllerRecord(
        "authenticated_epistemic_transition",
        "canonical_primitive",
        "authenticated_diagnostic_transition_bundle_producer_only",
        0,
        False,
        False,
    ),
)


class LegacyStopProjection(NamedTuple):
    automatic_progress_stopped: bool
    canonical_terminal_class: str | None
    semantic_refinement_required: bool


LEGACY_STOP_STATUS_COMPATIBILITY = (
    ("continue", LegacyStopProjection(False, None, False)),
    ("manual_review_gate", LegacyStopProjection(True, "review_required", False)),
    ("operationally_blocked", LegacyStopProjection(True, None, True)),
    ("terminal_for_current_scope", LegacyStopProjection(True, None, True)),
)

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
        "mission_projection_semantics",
        "diagnostic_transition_semantics",
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


def _controller_dict(record: ControllerRecord) -> dict[str, Any]:
    return {
        "surface_id": record.surface_id,
        "classification": record.classification,
        "role": record.role,
        "maximum_actions_per_call": record.maximum_actions_per_call,
        "automatic_looping": record.automatic_looping,
        "scientific_authority_applied": record.scientific_authority_applied,
    }


def _legacy_stop_dict() -> dict[str, dict[str, Any]]:
    return {
        status: {
            "automatic_progress_stopped": projection.automatic_progress_stopped,
            "canonical_terminal_class": projection.canonical_terminal_class,
            "semantic_refinement_required": projection.semantic_refinement_required,
        }
        for status, projection in LEGACY_STOP_STATUS_COMPATIBILITY
    }


def project_legacy_stop_status(stop_status: str) -> dict[str, Any]:
    """Project one historical planning stop status without inventing scientific convergence."""

    if not isinstance(stop_status, str) or not stop_status.strip() or stop_status != stop_status.strip():
        raise ScientificControlPlaneError("legacy stop status must be exact non-empty text")
    compatibility = _legacy_stop_dict()
    if stop_status not in compatibility:
        raise ScientificControlPlaneError(f"unsupported legacy stop status: {stop_status!r}")
    return {
        "legacy_stop_status": stop_status,
        **compatibility[stop_status],
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
        "controller_inventory": [_controller_dict(item) for item in CONTROLLER_INVENTORY],
        "legacy_stop_status_compatibility": _legacy_stop_dict(),
        "mission_projection_semantics": {
            "legacy_bounded_mission_is_composite": True,
            "science_projection_contains_objective_scope_and_success_criteria": True,
            "governance_projection_contains_autonomy_access_and_delegation_policy": True,
            "science_projection_may_modify_execution_policy": False,
        },
        "diagnostic_transition_semantics": {
            "authenticated_epistemic_transition_is_diagnostic": True,
            "authenticated_epistemic_transition_applies_scientific_authority": False,
            "reauthentication_grants_scientific_authority": False,
            "future_authority_bearing_update_requires_validated_evidence_packet": True,
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
            "authenticated_artifact_is_validated_scientific_evidence": False,
            "science_plane_grants_execution_authority": False,
            "governance_plane_grants_scientific_authority": False,
            "provider_self_validates_scientific_truth": False,
            "successful_transport_establishes_scientific_validity": False,
            "diagnostic_transition_creates_authoritative_epistemic_update": False,
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
        "mission_projection_semantics",
        "diagnostic_transition_semantics",
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
    "ControllerRecord",
    "GOVERNANCE_PLANE_RESPONSIBILITIES",
    "LEGACY_STOP_STATUS_COMPATIBILITY",
    "LegacyStopProjection",
    "PROVIDER_TO_EVIDENCE_FLOW",
    "SCIENCE_PLANE_RESPONSIBILITIES",
    "ScientificControlPlaneError",
    "build_scientific_control_plane_contract",
    "project_legacy_stop_status",
    "validate_scientific_control_plane_contract",
]
