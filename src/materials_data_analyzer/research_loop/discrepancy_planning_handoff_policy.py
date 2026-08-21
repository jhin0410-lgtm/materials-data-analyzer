"""Public policy boundary for discrepancy-to-planning handoff.

The structural handoff already prevents proposal injection into the current executable
frontier. This wrapper additionally requires the source discrepancy report to pass the
complete public physics/provenance hardening policy before any future-planning objective
is projected.
"""
from __future__ import annotations

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

DISCREPANCY_PLANNING_HANDOFF_HARDENING_POLICY_VERSION = "1.1"


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
    return _build_structural_handoff(
        discrepancy_report,
        evaluated_graph=evaluated_graph,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_discrepancy_report=previous_discrepancy_report,
    )


def validate_policy_hardened_discrepancy_planning_handoff(
    handoff: Mapping[str, Any],
    *,
    discrepancy_report: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Revalidate full source provenance/physics and the structural handoff itself."""
    discrepancy = validate_physics_hardened_model_evidence_discrepancy_report(
        discrepancy_report,
        evaluated_graph=evaluated_graph,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_report=previous_discrepancy_report,
    )
    result = _validate_structural_handoff(
        handoff,
        discrepancy_report=discrepancy_report,
        evaluated_graph=evaluated_graph,
        hypothesis_portfolio=hypothesis_portfolio,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    return {
        **result,
        "source_discrepancy_hardening_verified": True,
        "source_discrepancy_physics_hardening_verified": True,
        "source_discrepancy_report_sha256": discrepancy["report_sha256"],
    }


build_discrepancy_planning_handoff = build_policy_hardened_discrepancy_planning_handoff
validate_discrepancy_planning_handoff = (
    validate_policy_hardened_discrepancy_planning_handoff
)


__all__ = [
    "DISCREPANCY_PLANNING_HANDOFF_HARDENING_POLICY_VERSION",
    "DISCREPANCY_PLANNING_HANDOFF_POLICY_VERSION",
    "DISCREPANCY_PLANNING_HANDOFF_SCHEMA_VERSION",
    "DiscrepancyPlanningHandoffError",
    "build_discrepancy_planning_handoff",
    "build_policy_hardened_discrepancy_planning_handoff",
    "validate_discrepancy_planning_handoff",
    "validate_policy_hardened_discrepancy_planning_handoff",
]
