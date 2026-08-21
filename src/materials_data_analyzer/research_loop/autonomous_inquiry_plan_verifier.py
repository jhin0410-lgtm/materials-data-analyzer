"""Independent deterministic verification for autonomous inquiry plan bytes/state.

A canonical plan SHA proves integrity only after a plan exists; it does not prove that the
plan came from the repository planner.  This verifier rebuilds the plan from its declared
planner inputs and requires exact structural equality.  It grants no execution authority.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .autonomous_inquiry import build_autonomous_inquiry_plan
from .kernel import ResearchLoopError

AUTONOMOUS_INQUIRY_PLAN_VERIFIER_SCHEMA_VERSION = "1.0"
AUTONOMOUS_INQUIRY_PLAN_VERIFIER_POLICY_VERSION = "1.0"


class AutonomousInquiryPlanVerifierError(ResearchLoopError):
    """Raised when a purported planner result cannot be deterministically reproduced."""


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
        raise AutonomousInquiryPlanVerifierError(
            "autonomous inquiry verification state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AutonomousInquiryPlanVerifierError(f"{field} must be an object")
    return value


def validate_autonomous_inquiry_plan(
    plan: Mapping[str, Any],
    *,
    program_state: Mapping[str, Any],
    critic_report: Mapping[str, Any] | None = None,
    validated_reasoning_proposal: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
) -> dict[str, Any]:
    """Rebuild one inquiry plan from source inputs and require exact equality."""
    current = dict(_mapping(plan, "plan"))
    rebuilt = build_autonomous_inquiry_plan(
        _mapping(program_state, "program_state"),
        critic_report=critic_report,
        validated_reasoning_proposal=validated_reasoning_proposal,
        budget_units=budget_units,
        minimum_utility=minimum_utility,
    )
    if current != rebuilt:
        raise AutonomousInquiryPlanVerifierError(
            "autonomous inquiry plan differs from deterministic planner reconstruction"
        )
    plan_sha = current.get("plan_sha256")
    if not isinstance(plan_sha, str) or plan_sha != _canonical_sha256(
        {key: value for key, value in current.items() if key != "plan_sha256"}
    ):
        raise AutonomousInquiryPlanVerifierError(
            "autonomous inquiry plan SHA does not match deterministic content"
        )
    selected = current.get("selected_next_action")
    selected_id = selected.get("action_id") if isinstance(selected, Mapping) else None
    result: dict[str, Any] = {
        "schema_version": AUTONOMOUS_INQUIRY_PLAN_VERIFIER_SCHEMA_VERSION,
        "policy_version": AUTONOMOUS_INQUIRY_PLAN_VERIFIER_POLICY_VERSION,
        "plan_sha256": plan_sha,
        "program_state_canonical_sha256": _canonical_sha256(program_state),
        "critic_report_canonical_sha256": (
            _canonical_sha256(critic_report) if critic_report is not None else None
        ),
        "reasoning_proposal_canonical_sha256": (
            _canonical_sha256(validated_reasoning_proposal)
            if validated_reasoning_proposal is not None
            else None
        ),
        "planning_budget": {
            "budget_units": budget_units,
            "minimum_utility": minimum_utility,
        },
        "selected_candidate_id": selected_id,
        "verification_status": "deterministically_rebuilt_from_planner_inputs",
        "planner_candidate_injected": False,
        "authorization_granted": False,
        "execution_performed": False,
        "scientific_status_changed": False,
    }
    result["verification_sha256"] = _canonical_sha256(result)
    return result


__all__ = [
    "AUTONOMOUS_INQUIRY_PLAN_VERIFIER_POLICY_VERSION",
    "AUTONOMOUS_INQUIRY_PLAN_VERIFIER_SCHEMA_VERSION",
    "AutonomousInquiryPlanVerifierError",
    "validate_autonomous_inquiry_plan",
]
