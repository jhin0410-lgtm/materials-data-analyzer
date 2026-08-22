"""Supported planning-context wrapper with predecessor-limit inheritance.

The underlying checkpoint builder already inherits recursive limits from a predecessor when
the caller omits them.  This public wrapper preserves that same contract when the validated
checkpoint is packaged into the persistent planning context.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .public_recursive_planning import (
    build_public_recursive_planning_context as _build_context,
    validate_public_recursive_planning_context,
)


def build_public_recursive_planning_context(
    *,
    validated_planning_artifact: Mapping[str, Any],
    planning_handoff: Mapping[str, Any],
    source_discrepancy_report: Mapping[str, Any],
    source_evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    planner_program_state: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any] | None = None,
    candidate_match: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    previous_validated_planning_context: Mapping[str, Any] | None = None,
    recursive_limits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    effective_limits = recursive_limits
    if effective_limits is None and previous_validated_planning_context is not None:
        previous = validate_public_recursive_planning_context(
            previous_validated_planning_context
        )
        effective_limits = previous["recursive_limits"]
    return _build_context(
        validated_planning_artifact=validated_planning_artifact,
        planning_handoff=planning_handoff,
        source_discrepancy_report=source_discrepancy_report,
        source_evaluated_graph=source_evaluated_graph,
        fresh_plan=fresh_plan,
        planner_program_state=planner_program_state,
        previous_discrepancy_report=previous_discrepancy_report,
        candidate_match=candidate_match,
        budget_units=budget_units,
        minimum_utility=minimum_utility,
        previous_validated_planning_context=previous_validated_planning_context,
        recursive_limits=effective_limits,
    )


__all__ = ["build_public_recursive_planning_context"]
