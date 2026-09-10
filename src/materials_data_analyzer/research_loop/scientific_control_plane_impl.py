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

CONTROL_PLANE_SCHEMA_VERSION = "1.2"
CONTROL_PLANE_POLICY_VERSION = "1.2"

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
    "map_validated_evidence_packets_and_gaps",
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

# These are scientific stopping dispositions. Governance-only inability to execute is kept out
# of this vocabulary so a budget or authorization event cannot masquerade as scientific meaning.
CANONICAL_TERMINAL_CLASSES = (
    "converged",
    "decision_threshold_reached",
    "irreducible_uncertainty",
    "contradictory_evidence",
    "blocked_external_evidence",
    "review_required",
    "marginal_information_value_too_low",
)

GOVERNANCE_RUN_STOP_REASONS = (
    "resource_budget_exhausted",
    "authorization_or_safety_blocked",
    "execution_failed",
    "interrupted",
    "operator_stop",
)

SCIENCE_PLANE_RESPONSIBILITIES = (
    "research_questions",
    "scientific_mission_objective_scope_and_scientific_criteria",
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
        "persistent_research_episode_checkpoint",
        "canonical_primitive",
        "persistent_operational_episode_checkpoint_open_resume_and_single_step_commit",
        0,
        False,
        None,
    ),
    ControllerRecord(
        "persistent_research_episode",
        "compatibility_facade",
        "caller_budget_bounded_automatic_step_handler_loop_with_checkpointing",
        None,
        True,
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
        "public_recursive_api",
        "compatibility_facade",
        (
            "supported_public_recursive_composition_facade_exposing_single_action_execution_"
            "and_single_cycle_progression_plus_nonexecuting_bounded_replay_builders"
        ),
        1,
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
    # Historical manual_review_gate is not semantically uniform: it can be emitted after failed
    # audit/execution recovery as well as human-review needs. Do not infer scientific review.
    ("manual_review_gate", LegacyStopProjection(True, None, True)),
    ("operationally_blocked", LegacyStopProjection(True, None, True)),
    ("terminal_for_current_scope", LegacyStopProjection(True, None, True)),
)


class LegacyMissionFieldProjection(NamedTuple):
    mission_id: str
    source_field: str
    source_text: str
    science_projection: str
    governance_projection: str


class LegacyMissionItemProjection(NamedTuple):
    mission_id: str
    collection: str
    item_index: int
    item_text: str
    science_semantic: str | None
    governance_semantic: str | None


_IN625_MISSION_ID = "autonomous-in625-production-v1"

# The real legacy `mission` field is composite. Authentication proves its bytes, but only this
# deterministic compatibility projection assigns the scientific and governance meanings.
LEGACY_MISSION_FIELD_PROJECTIONS = (
    LegacyMissionFieldProjection(
        _IN625_MISSION_ID,
        "mission",
        (
            "Autonomously advance the verified IN625 external empirical evidence state by "
            "selecting only mission-pinned source acquisition and typed research capabilities, "
            "preserving exact provenance and observed source quality, and iterating until the "
            "next scientific action is either executed under an audited capability or boundedly "
            "unavailable."
        ),
        (
            "Advance the verified IN625 external empirical evidence state, preserve observed "
            "source quality, generate the next scientific action from authoritative state, and "
            "continue until a scientifically meaningful next step or bounded evidence gap is "
            "identified."
        ),
        (
            "Execution may use only mission-pinned source acquisition and audited typed "
            "capabilities, with exact provenance and explicit bounded operational stopping."
        ),
    ),
)

# Exact item-level compatibility classifications for the currently installed IN625 production
# mission. A mixed item carries both projections; neither projection receives the other's
# authority. Unknown text/index combinations fail closed rather than being heuristically tagged.
LEGACY_MISSION_ITEM_PROJECTIONS = (
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "success_criteria",
        0,
        (
            "The program starts from verified evidence state and does not require a caller-authored "
            "execution request queue."
        ),
        "start_from_current_authoritative_evidence_state",
        "caller_authored_execution_request_queue_not_required",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "success_criteria",
        1,
        (
            "The exact Zenodo 20503603 source is acquired only under the mission-pinned standing "
            "network policy and independently checksum verified."
        ),
        None,
        "mission_pinned_source_authorization_and_checksum_integrity",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "success_criteria",
        2,
        (
            "The typed IN625 registration request is machine-authored only under the mission-pinned "
            "request-delegation policy."
        ),
        None,
        "machine_authored_request_requires_pinned_delegation_policy",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "success_criteria",
        3,
        (
            "Real row-level tensile evidence and observed source missingness are preserved without "
            "imputation, inverse reconstruction, coercion, or silent row exclusion."
        ),
        "preserve_observed_empirical_rows_and_missingness_without_scientific_fabrication",
        None,
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "success_criteria",
        4,
        (
            "The exact NIST mds2-2923 geometry source is acquired only after the comparability gate "
            "generates that action and only under its separately mission-pinned standing network "
            "policy."
        ),
        "comparability_gate_may_select_the_nist_geometry_evidence_action",
        "selected_nist_action_requires_separate_mission_pinned_network_authority",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "success_criteria",
        5,
        (
            "The reviewed geometry-condition mapping acquires only mission-pinned official/paper "
            "sources, binds exact source bytes at execution, preserves claim/version conflicts, and "
            "never promotes literature claims to row-level measurement authority."
        ),
        "preserve_literature_claim_scope_version_conflicts_and_non_row_authority",
        "source_acquisition_requires_mission_pins_and_exact_byte_binding",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "success_criteria",
        6,
        (
            "Unavailable full text remains explicitly metadata/abstract evidence and is never "
            "represented as acquired full-text evidence."
        ),
        "preserve_literature_evidence_scope_when_full_text_is_unavailable",
        None,
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "success_criteria",
        7,
        (
            "After re-diagnosis, the program generates the next scientific action from the new "
            "evidence state and stops only for an explicit bounded reason when that action is not "
            "registered."
        ),
        "rediagnose_authoritative_state_and_generate_next_scientific_action",
        "unregistered_action_causes_only_explicit_bounded_operational_stop",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "success_criteria",
        8,
        (
            "When a valid next action lacks an executor, the program emits a provenance-bound "
            "capability gap/specification, promotes only independently verified bounded capabilities, "
            "resumes the blocked action, and may use only separately mission-pinned discovery indices "
            "for source discovery."
        ),
        "valid_scientific_action_may_expose_a_capability_gap_without_changing_evidence",
        "capability_expansion_and_source_discovery_require_verified_bounded_authority",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "success_criteria",
        9,
        (
            "A source candidate discovered by a verified index capability may be acquired only "
            "through a separately mission-pinned derived-authority policy that binds the exact "
            "discovery report, predecessor manifest, candidate identity/rank, candidate page bytes, "
            "and any page-derived full-text link before scientific assessment."
        ),
        "scientific_assessment_occurs_only_after_source_identity_is_bound",
        "candidate_acquisition_requires_separate_derived_authority_and_exact_ancestry",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "success_criteria",
        10,
        (
            "Experiment-identity assessment must construct a typed provenance graph from exact "
            "dataset metadata and exact primary-paper references, forbid transitive identity/power "
            "promotion, and emit a narrower derived-acquisition frontier when required full text is "
            "missing."
        ),
        "experiment_identity_requires_typed_direct_evidence_and_forbids_transitive_promotion",
        "missing_primary_evidence_may_generate_only_a_narrower_derived_acquisition_frontier",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "constraints",
        0,
        (
            "Never fabricate or infer missing measurements, sample identity, replicate independence, "
            "calibration, or condition equivalence."
        ),
        "forbid_scientific_fabrication_and_unproven_identity_independence_calibration_equivalence",
        None,
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "constraints",
        1,
        (
            "Never treat network, checksum, parser, or workflow success as empirical model validation "
            "or hypothesis truth."
        ),
        "governance_or_software_success_never_establishes_model_validation_or_hypothesis_truth",
        "transport_integrity_and_workflow_success_remain_non_scientific_governance_facts",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "constraints",
        2,
        (
            "Never execute arbitrary Python, shell, provider, URL, or action outside exact "
            "mission-pinned policies and audited capability code."
        ),
        None,
        "forbid_execution_outside_exact_policies_and_audited_capabilities",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "constraints",
        3,
        "Network failures are operational evidence only and are never negative scientific evidence.",
        "network_failure_cannot_be_interpreted_as_negative_scientific_evidence",
        "network_failure_is_operational_state_only",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "constraints",
        4,
        (
            "Authoritative datasets, papers and supplementary materials, official technical reports "
            "and documentation, characterization evidence, and other provenance-verifiable real "
            "physical evidence remain eligible evidence classes under source-specific trust and "
            "scientific-intake boundaries."
        ),
        "real_evidence_classes_remain_scientifically_eligible_under_domain_intake_boundaries",
        "each_evidence_class_requires_source_specific_trust_boundary",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "constraints",
        5,
        (
            "Physical experiment execution remains external until a separately authorized laboratory "
            "interface exists."
        ),
        None,
        "physical_experiment_execution_requires_separate_laboratory_authority",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "constraints",
        6,
        (
            "Capability expansion may compose verified primitives or declarative adapters, but it may "
            "not synthesize unrestricted network authority, caller-authored URLs, arbitrary executable "
            "code, or scientific truth."
        ),
        "capability_expansion_never_creates_scientific_truth",
        "capability_expansion_cannot_widen_network_url_or_execution_authority",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "constraints",
        7,
        (
            "Discovery output is not acquisition authority; follow-up candidate acquisition must derive "
            "authority from authenticated predecessor artifacts and must not accept caller-authored "
            "candidate URLs."
        ),
        None,
        "discovery_output_does_not_grant_acquisition_authority",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "constraints",
        8,
        (
            "Dataset-publication association, condition-signature match, same-platform citation, or "
            "protocol citation alone must never be promoted to exact row identity, experiment identity, "
            "power conversion, protocol equivalence, or uncertainty transfer."
        ),
        "forbid_transitive_scientific_identity_calibration_protocol_and_uncertainty_promotion",
        None,
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "stop_rules",
        0,
        (
            "When the current verified next-action class has no audited executor, attempt bounded "
            "capability expansion; stop only if no independently verifiable candidate is available "
            "under exact mission authority."
        ),
        "lack_of_executor_does_not_change_scientific_truth_or_next_action_value",
        "bounded_capability_expansion_then_operational_stop_if_no_authorized_candidate_exists",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "stop_rules",
        1,
        "Stop on mission, policy, registry, source, request, ledger, checksum, or verifier binding mismatch.",
        None,
        "stop_on_authenticated_contract_or_integrity_binding_mismatch",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "stop_rules",
        2,
        (
            "Stop when cycle or cost budget is exhausted or when a cycle produces no new verified "
            "information."
        ),
        "no_new_validated_scientific_information_may_support_separate_scientific_reassessment",
        "cycle_or_cost_budget_exhaustion_is_governance_run_stop",
    ),
    LegacyMissionItemProjection(
        _IN625_MISSION_ID,
        "stop_rules",
        3,
        (
            "Do not claim global evidence unavailability when only the current registered capability "
            "set is exhausted."
        ),
        "capability_exhaustion_does_not_establish_global_evidence_unavailability",
        "registered_capability_exhaustion_is_bounded_operational_state",
    ),
)

_REQUIRED_CONTRACT_KEYS = frozenset(
    {
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


def _legacy_mission_field_projection_dict() -> dict[str, dict[str, Any]]:
    return {
        record.mission_id: {
            "source_field": record.source_field,
            "source_text": record.source_text,
            "science_projection": record.science_projection,
            "governance_projection": record.governance_projection,
            "authentication_alone_grants_scientific_authority": False,
        }
        for record in LEGACY_MISSION_FIELD_PROJECTIONS
    }


def _legacy_mission_item_projection_list() -> list[dict[str, Any]]:
    return [
        {
            "mission_id": record.mission_id,
            "collection": record.collection,
            "item_index": record.item_index,
            "item_text": record.item_text,
            "science_semantic": record.science_semantic,
            "governance_semantic": record.governance_semantic,
        }
        for record in LEGACY_MISSION_ITEM_PROJECTIONS
    ]


def project_legacy_stop_status(stop_status: str) -> dict[str, Any]:
    """Project one historical planning stop status without inventing scientific convergence."""

    if (
        not isinstance(stop_status, str)
        or not stop_status.strip()
        or stop_status != stop_status.strip()
    ):
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


def project_legacy_mission_field(
    *, mission_id: str, mission_text: str
) -> dict[str, Any]:
    """Project the exact installed composite mission field without trusting authentication alone."""

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
        "source_field": record.source_field,
        "source_text": record.source_text,
        "science_projection": record.science_projection,
        "governance_projection": record.governance_projection,
        "historical_artifact_rewritten": False,
        "scientific_status_promoted": False,
        "execution_authority_granted": False,
    }


def project_legacy_mission_item(
    *, mission_id: str, collection: str, item_index: int, item_text: str
) -> dict[str, Any]:
    """Return one exact item-level projection; unknown items receive no inferred authority."""

    matches = [
        record
        for record in LEGACY_MISSION_ITEM_PROJECTIONS
        if record.mission_id == mission_id
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
        "collection": record.collection,
        "item_index": record.item_index,
        "item_text": record.item_text,
        "science_semantic": record.science_semantic,
        "governance_semantic": record.governance_semantic,
        "historical_artifact_rewritten": False,
        "scientific_status_promoted": False,
        "execution_authority_granted": False,
    }


def build_scientific_control_plane_contract() -> dict[str, Any]:
    """Return the deterministic architecture contract consumed by docs/tests/tooling."""

    return {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "policy_version": CONTROL_PLANE_POLICY_VERSION,
        "canonical_research_state_entities": list(CANONICAL_RESEARCH_STATE_ENTITIES),
        "canonical_research_stages": list(CANONICAL_RESEARCH_STAGES),
        "canonical_terminal_classes": list(CANONICAL_TERMINAL_CLASSES),
        "governance_run_stop_reasons": list(GOVERNANCE_RUN_STOP_REASONS),
        "science_plane_responsibilities": list(SCIENCE_PLANE_RESPONSIBILITIES),
        "governance_plane_responsibilities": list(GOVERNANCE_PLANE_RESPONSIBILITIES),
        "provider_to_evidence_flow": list(PROVIDER_TO_EVIDENCE_FLOW),
        "controller_classifications": list(CONTROLLER_CLASSIFICATIONS),
        "controller_inventory": [_controller_dict(item) for item in CONTROLLER_INVENTORY],
        "legacy_stop_status_compatibility": _legacy_stop_dict(),
        "mission_projection_semantics": {
            "legacy_bounded_mission_is_composite": True,
            "real_legacy_mission_field_requires_classified_projection": True,
            "legacy_mission_field_projections": _legacy_mission_field_projection_dict(),
            "field_level_governance_projection": [
                "autonomy_policy",
                "source_trust_policy_pins",
                "request_delegation_policy_pins",
            ],
            "item_level_projection_required_for": [
                "success_criteria",
                "constraints",
                "stop_rules",
            ],
            "legacy_mission_item_projections": _legacy_mission_item_projection_list(),
            "unknown_mission_field_or_item_projection": "unresolved_no_authority",
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
            "governance_stop_reason_is_scientific_terminal_disposition": False,
            "unknown_legacy_mission_content_grants_authority": False,
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
        "governance_run_stop_reasons",
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
        raise ScientificControlPlaneError(
            "science and governance responsibilities must be disjoint"
        )

    if set(value["canonical_terminal_classes"]) & set(value["governance_run_stop_reasons"]):
        raise ScientificControlPlaneError(
            "scientific terminal classes and governance stop reasons must be disjoint"
        )

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
    "project_legacy_stop_status",
    "validate_scientific_control_plane_contract",
]
