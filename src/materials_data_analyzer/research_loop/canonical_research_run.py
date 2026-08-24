"""Canonical persistent ResearchRun architecture contract.

A product-level research run keeps scientific meaning, governance authority, operational
lifecycle, and scientific stopping disposition orthogonal. Historical ledger artifacts are not
rewritten; compatibility projections may reconstruct the canonical view without changing bytes.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

from .scientific_control_plane import (
    CANONICAL_RESEARCH_STATE_ENTITIES,
    CANONICAL_TERMINAL_CLASSES,
    GOVERNANCE_RUN_STOP_REASONS,
)

RESEARCH_RUN_SCHEMA_VERSION = "1.2"
RESEARCH_RUN_POLICY_VERSION = "1.2"

RESEARCH_RUN_SECTIONS = (
    "identity",
    "scientific_state",
    "governance_state",
    "run_lifecycle",
    "scientific_stop_disposition",
    "derived_projections",
)

SCIENTIFIC_STATE_COLLECTIONS = tuple(CANONICAL_RESEARCH_STATE_ENTITIES)

GOVERNANCE_STATE_COLLECTIONS = (
    "provenance_bindings",
    "mission_governance_policy",
    "source_access_policies",
    "authorization_records",
    "execution_records",
    "resource_budget_state",
    "transaction_integrity_state",
    "recovery_and_audit_records",
    "lifecycle_event_records",
)

RUN_LIFECYCLE_STATES = (
    "active",
    "blocked",
    "concluded",
    "stopped",
    "interrupted",
    "execution_failed",
)

SCIENTIFIC_STOP_DISPOSITIONS = (
    "continue",
    "undetermined",
    *CANONICAL_TERMINAL_CLASSES,
)

DERIVED_PROJECTIONS = (
    "provider_readiness",
    "characterization_l0_l8",
    "planner_view",
    "release_readiness",
)


class ScientificEntityAuthoritySource(NamedTuple):
    entity: str
    authority_source: str


# Immutable source representation. A builder may project this tuple into a dictionary, but
# importers cannot mutate the source of truth and make validation accept authority drift.
SCIENTIFIC_ENTITY_AUTHORITY_SOURCES = (
    ScientificEntityAuthoritySource(
        "research_question",
        "science_plane_authored_initialization_or_classified_legacy_projection",
    ),
    ScientificEntityAuthoritySource(
        "scientific_mission",
        "science_plane_authored_scientific_projection_or_classified_legacy_projection",
    ),
    ScientificEntityAuthoritySource(
        "hypothesis",
        "science_plane_authored_hypothesis_or_authority_bearing_epistemic_update",
    ),
    ScientificEntityAuthoritySource("observation", "validated_evidence_packet"),
    ScientificEntityAuthoritySource(
        "derived_result",
        "validated_evidence_packet_with_authenticated_derivation_lineage",
    ),
    ScientificEntityAuthoritySource("evidence", "validated_evidence_packet"),
    ScientificEntityAuthoritySource(
        "claim",
        "authority_bearing_epistemic_update_over_validated_evidence_packets",
    ),
    ScientificEntityAuthoritySource(
        "inference",
        "authority_bearing_epistemic_update_over_validated_evidence_packets",
    ),
    ScientificEntityAuthoritySource(
        "contradiction",
        "science_plane_assessment_over_authoritative_scientific_state",
    ),
    ScientificEntityAuthoritySource(
        "comparability_assessment",
        "science_plane_comparability_assessment_over_validated_evidence_packets",
    ),
    ScientificEntityAuthoritySource(
        "uncertainty_state",
        "science_plane_uncertainty_assessment_or_explicit_unknown_over_authoritative_state",
    ),
    ScientificEntityAuthoritySource(
        "evidence_gap",
        "science_plane_diagnosis_over_current_authoritative_scientific_state",
    ),
    ScientificEntityAuthoritySource(
        "candidate_action",
        "science_plane_planner_generation_from_current_authoritative_state",
    ),
    ScientificEntityAuthoritySource(
        "decision",
        "science_plane_decision_record_from_current_authoritative_state",
    ),
)

_REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "policy_version",
        "sections",
        "scientific_state_collections",
        "scientific_entity_authority_sources",
        "governance_state_collections",
        "governance_run_stop_reasons",
        "run_lifecycle_states",
        "scientific_stop_dispositions",
        "derived_projections",
        "section_authority_sources",
        "authority_invariants",
        "compatibility_invariants",
    }
)


class CanonicalResearchRunError(ValueError):
    """Raised when the canonical ResearchRun architecture contract drifts."""


def _scientific_entity_authority_dict() -> dict[str, str]:
    return {record.entity: record.authority_source for record in SCIENTIFIC_ENTITY_AUTHORITY_SOURCES}


def build_canonical_research_run_contract() -> dict[str, Any]:
    """Return the immutable semantic contract for product-level ResearchRun state."""

    return {
        "schema_version": RESEARCH_RUN_SCHEMA_VERSION,
        "policy_version": RESEARCH_RUN_POLICY_VERSION,
        "sections": list(RESEARCH_RUN_SECTIONS),
        "scientific_state_collections": list(SCIENTIFIC_STATE_COLLECTIONS),
        "scientific_entity_authority_sources": _scientific_entity_authority_dict(),
        "governance_state_collections": list(GOVERNANCE_STATE_COLLECTIONS),
        "governance_run_stop_reasons": list(GOVERNANCE_RUN_STOP_REASONS),
        "run_lifecycle_states": list(RUN_LIFECYCLE_STATES),
        "scientific_stop_dispositions": list(SCIENTIFIC_STOP_DISPOSITIONS),
        "derived_projections": list(DERIVED_PROJECTIONS),
        "section_authority_sources": {
            "identity": "authenticated_run_identity_and_ancestry",
            "scientific_state": "entity_specific_science_plane_initialization_classified_legacy_projection_and_validated_evidence_epistemic_update_rules",
            "governance_state": "authenticated_policy_authorization_execution_and_audit_records",
            "run_lifecycle": "authenticated_operational_lifecycle_events",
            "scientific_stop_disposition": "science_plane_assessment_over_authoritative_scientific_state",
            "derived_projections": "non_authoritative_projection_of_canonical_state",
        },
        "authority_invariants": {
            "science_plane_may_initialize_non_empirical_scientific_scaffolding": True,
            "legacy_composite_mission_authentication_alone_enters_scientific_state": False,
            "legacy_mission_scientific_projection_requires_deterministic_classification": True,
            "empirical_observation_enters_without_validated_evidence_packet": False,
            "derived_result_enters_without_validated_evidence_packet": False,
            "claim_or_inference_promoted_without_authority_bearing_update": False,
            "authenticated_artifact_alone_enters_authoritative_scientific_state": False,
            "diagnostic_transition_alone_enters_authoritative_scientific_state": False,
            "governance_state_reconstructed_from_authenticated_policy_authorization_and_execution_records": True,
            "run_lifecycle_reconstructed_from_authenticated_operational_events": True,
            "run_lifecycle_implies_scientific_stop_disposition": False,
            "governance_stop_reason_implies_scientific_stop_disposition": False,
            "scientific_stop_disposition_is_operational_lifecycle_state": False,
            "derived_projection_is_authoritative_scientific_truth": False,
            "derived_projection_grants_execution_authority": False,
            "governance_success_promotes_scientific_status": False,
            "science_selection_grants_execution_authority": False,
        },
        "compatibility_invariants": {
            "historical_artifacts_rewritten": False,
            "historical_hashes_recomputed": False,
            "legacy_state_remains_replayable": True,
            "legacy_operational_stop_is_not_assumed_scientific_stop": True,
            "migration_requires_explicit_compatibility_projection": True,
        },
    }


def validate_canonical_research_run_contract(value: object) -> dict[str, Any]:
    """Validate the exact canonical ResearchRun architecture contract fail-closed."""

    if not isinstance(value, Mapping):
        raise CanonicalResearchRunError("canonical ResearchRun contract must be an object")
    missing = sorted(_REQUIRED_KEYS - set(value))
    unknown = sorted(set(value) - _REQUIRED_KEYS)
    if missing or unknown:
        raise CanonicalResearchRunError(
            f"canonical ResearchRun contract must use exact keys; unknown={unknown}, missing={missing}"
        )

    expected = build_canonical_research_run_contract()
    if dict(value) != expected:
        raise CanonicalResearchRunError("canonical ResearchRun contract drifted")
    return expected


__all__ = [
    "CanonicalResearchRunError",
    "DERIVED_PROJECTIONS",
    "GOVERNANCE_STATE_COLLECTIONS",
    "RESEARCH_RUN_POLICY_VERSION",
    "RESEARCH_RUN_SCHEMA_VERSION",
    "RESEARCH_RUN_SECTIONS",
    "RUN_LIFECYCLE_STATES",
    "SCIENTIFIC_ENTITY_AUTHORITY_SOURCES",
    "SCIENTIFIC_STATE_COLLECTIONS",
    "SCIENTIFIC_STOP_DISPOSITIONS",
    "ScientificEntityAuthoritySource",
    "build_canonical_research_run_contract",
    "validate_canonical_research_run_contract",
]
