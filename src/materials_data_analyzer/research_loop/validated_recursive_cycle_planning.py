"""Validated public planning entry for one recursive research cycle.

This facade closes the self-recertified-plan gap: it first reconstructs the autonomous
inquiry plan from the exact planner inputs, then delegates only that verified plan to the
planning-only recursive checkpoint controller.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .autonomous_inquiry_plan_verifier import validate_autonomous_inquiry_plan
from .discrepancy_planning_handoff_policy import (
    validate_policy_hardened_discrepancy_planning_handoff,
)
from .kernel import ResearchLoopError
from .recursive_research_cycle_controller import (
    build_recursive_research_cycle_checkpoint,
)

VALIDATED_RECURSIVE_PLANNING_SCHEMA_VERSION = "1.0"
VALIDATED_RECURSIVE_PLANNING_POLICY_VERSION = "1.0"


class ValidatedRecursivePlanningError(ResearchLoopError):
    """Raised when verified planner identity drifts before checkpoint publication."""


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def build_validated_recursive_planning_checkpoint(
    *,
    planning_handoff: Mapping[str, Any],
    source_discrepancy_report: Mapping[str, Any],
    source_evaluated_graph: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    planner_program_state: Mapping[str, Any],
    source_hypothesis_portfolio: Mapping[str, Any] | None = None,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
    candidate_match: Mapping[str, Any] | None = None,
    planner_critic_report: Mapping[str, Any] | None = None,
    planner_reasoning_proposal: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    previous_checkpoint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify hardened discrepancy provenance and planner identity before publication."""
    try:
        handoff_verification = validate_policy_hardened_discrepancy_planning_handoff(
            planning_handoff,
            discrepancy_report=source_discrepancy_report,
            evaluated_graph=source_evaluated_graph,
            hypothesis_portfolio=source_hypothesis_portfolio,
            previous_discrepancy_report=previous_discrepancy_report,
        )
    except ResearchLoopError as exc:
        raise ValidatedRecursivePlanningError(
            "planning handoff failed hardened discrepancy-source reconstruction"
        ) from exc

    verification = validate_autonomous_inquiry_plan(
        fresh_plan,
        program_state=planner_program_state,
        critic_report=planner_critic_report,
        validated_reasoning_proposal=planner_reasoning_proposal,
        budget_units=budget_units,
        minimum_utility=minimum_utility,
    )
    checkpoint = build_recursive_research_cycle_checkpoint(
        planning_handoff=planning_handoff,
        fresh_plan=fresh_plan,
        candidate_match=candidate_match,
        previous_checkpoint=previous_checkpoint,
    )
    if verification["plan_sha256"] != checkpoint["ancestry"]["fresh_plan_sha256"]:
        raise ValidatedRecursivePlanningError(
            "verified planner SHA diverged before recursive checkpoint publication"
        )
    if (
        handoff_verification["handoff_sha256"]
        != checkpoint["ancestry"]["planning_handoff_sha256"]
    ):
        raise ValidatedRecursivePlanningError(
            "verified discrepancy handoff SHA diverged before recursive checkpoint publication"
        )
    result: dict[str, Any] = {
        "schema_version": VALIDATED_RECURSIVE_PLANNING_SCHEMA_VERSION,
        "policy_version": VALIDATED_RECURSIVE_PLANNING_POLICY_VERSION,
        "handoff_verification": handoff_verification,
        "planner_verification": verification,
        "recursive_checkpoint": checkpoint,
        "autonomy_boundary": {
            "source_discrepancy_hardening_verified": True,
            "planner_reconstruction_verified": True,
            "critic_proposal_executed_directly": False,
            "planner_candidate_injected": False,
            "authorization_granted": False,
            "request_compiled": False,
            "execution_performed": False,
            "scientific_status_changed": False,
        },
    }
    result["validated_checkpoint_sha256"] = _canonical_sha256(result)
    return result


__all__ = [
    "VALIDATED_RECURSIVE_PLANNING_POLICY_VERSION",
    "VALIDATED_RECURSIVE_PLANNING_SCHEMA_VERSION",
    "ValidatedRecursivePlanningError",
    "build_validated_recursive_planning_checkpoint",
]
