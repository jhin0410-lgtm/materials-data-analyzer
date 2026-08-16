"""Facade for one critic-aware, self-directed research-agent planning iteration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .autonomous_inquiry import _canonical_sha256
from .critic_inquiry_adapter import adapt_scientific_critic_report
from .self_directed_research import build_self_directed_research_plan

RESEARCH_AGENT_SCHEMA_VERSION = "1.0"
RESEARCH_AGENT_POLICY_VERSION = "1.0"


def build_research_agent_iteration(
    program_state: Mapping[str, Any],
    *,
    scientific_critic_report: Mapping[str, Any] | None = None,
    validated_reasoning_proposal: Mapping[str, Any] | None = None,
    previous_plan: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    max_iterations: int = 8,
) -> dict[str, Any]:
    """Build the preferred v1 research-agent iteration from current public contracts."""
    adapted_critic = (
        adapt_scientific_critic_report(scientific_critic_report)
        if scientific_critic_report is not None
        else None
    )
    plan = build_self_directed_research_plan(
        program_state,
        critic_report=adapted_critic,
        validated_reasoning_proposal=validated_reasoning_proposal,
        previous_plan=previous_plan,
        budget_units=budget_units,
        minimum_utility=minimum_utility,
        max_iterations=max_iterations,
    )
    result = {
        **plan,
        "research_agent_schema_version": RESEARCH_AGENT_SCHEMA_VERSION,
        "research_agent_policy_version": RESEARCH_AGENT_POLICY_VERSION,
        "scientific_critic_adapter": (
            {
                "source_sha256": _canonical_sha256(scientific_critic_report),
                "adapted_sha256": adapted_critic["projection_sha256"],
                "current_public_critic_contract_consumed": True,
            }
            if scientific_critic_report is not None and adapted_critic is not None
            else None
        ),
    }
    result.pop("plan_sha256", None)
    result["plan_sha256"] = _canonical_sha256(result)
    return result


__all__ = [
    "RESEARCH_AGENT_POLICY_VERSION",
    "RESEARCH_AGENT_SCHEMA_VERSION",
    "build_research_agent_iteration",
]
