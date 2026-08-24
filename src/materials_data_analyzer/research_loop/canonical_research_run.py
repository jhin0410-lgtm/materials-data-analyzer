"""Canonical persistent ResearchRun architecture contract.

The contract describes how a product-level research run is partitioned without migrating or
rewriting historical ledger artifacts. Scientific state and governance state have different
authority sources; derived projections are never authoritative truth sources.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .scientific_control_plane import CANONICAL_RESEARCH_STATE_ENTITIES

RESEARCH_RUN_SCHEMA_VERSION = "1.0"
RESEARCH_RUN_POLICY_VERSION = "1.0"

RESEARCH_RUN_SECTIONS = (
    "identity",
    "scientific_state",
    "governance_state",
    "derived_projections",
    "terminal_state",
)

SCIENTIFIC_STATE_COLLECTIONS = tuple(CANONICAL_RESEARCH_STATE_ENTITIES)

GOVERNANCE_STATE_COLLECTIONS = (
    "provenance_bindings",
    "source_access_policies",
    "authorization_records",
    "execution_records",
    "resource_budget_state",
    "transaction_integrity_state",
    "recovery_and_audit_records",
)

DERIVED_PROJECTIONS = (
    "provider_readiness",
    "characterization_l0_l8",
    "planner_view",
    "release_readiness",
)

_REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "policy_version",
        "sections",
        "scientific_state_collections",
        "governance_state_collections",
        "derived_projections",
        "authority_invariants",
        "compatibility_invariants",
    }
)


class CanonicalResearchRunError(ValueError):
    """Raised when the canonical ResearchRun architecture contract drifts."""


def build_canonical_research_run_contract() -> dict[str, Any]:
    """Return the immutable semantic contract for product-level ResearchRun state."""

    return {
        "schema_version": RESEARCH_RUN_SCHEMA_VERSION,
        "policy_version": RESEARCH_RUN_POLICY_VERSION,
        "sections": list(RESEARCH_RUN_SECTIONS),
        "scientific_state_collections": list(SCIENTIFIC_STATE_COLLECTIONS),
        "governance_state_collections": list(GOVERNANCE_STATE_COLLECTIONS),
        "derived_projections": list(DERIVED_PROJECTIONS),
        "authority_invariants": {
            "scientific_state_reconstructed_from_authenticated_evidence_and_epistemic_events": True,
            "governance_state_reconstructed_from_authenticated_policy_authorization_and_execution_records": True,
            "derived_projection_is_authoritative_scientific_truth": False,
            "derived_projection_grants_execution_authority": False,
            "governance_success_promotes_scientific_status": False,
            "science_selection_grants_execution_authority": False,
        },
        "compatibility_invariants": {
            "historical_artifacts_rewritten": False,
            "historical_hashes_recomputed": False,
            "legacy_state_remains_replayable": True,
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
    "SCIENTIFIC_STATE_COLLECTIONS",
    "build_canonical_research_run_contract",
    "validate_canonical_research_run_contract",
]
