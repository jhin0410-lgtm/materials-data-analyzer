"""Facade for one critic-aware, self-directed research-agent planning iteration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .autonomous_inquiry import _canonical_sha256
from .characterization_evidence_bridge import (
    apply_characterization_evidence_assessments,
    composite_assessment_binding,
)
from .critic_inquiry_adapter import adapt_scientific_critic_report
from .self_directed_research import build_self_directed_research_plan

RESEARCH_AGENT_SCHEMA_VERSION = "1.1"
RESEARCH_AGENT_POLICY_VERSION = "1.1"


def _selected_action_id(plan: Mapping[str, Any]) -> str | None:
    selected = plan.get("selected_next_action")
    if not isinstance(selected, Mapping):
        return None
    value = selected.get("action_id")
    return value if isinstance(value, str) and value else None


def build_research_agent_iteration(
    program_state: Mapping[str, Any],
    *,
    scientific_critic_report: Mapping[str, Any] | None = None,
    validated_reasoning_proposal: Mapping[str, Any] | None = None,
    characterization_evidence_assessments: Sequence[Mapping[str, Any]] | None = None,
    previous_plan: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    max_iterations: int = 8,
) -> dict[str, Any]:
    """Build one preferred critic- and evidence-aware research-agent iteration."""
    adapted_critic = (
        adapt_scientific_critic_report(scientific_critic_report)
        if scientific_critic_report is not None
        else None
    )
    assessments = list(characterization_evidence_assessments or [])
    characterization_binding = (
        composite_assessment_binding(assessments) if assessments else None
    )
    research_state_material = {
        "program_sha256": _canonical_sha256(program_state),
        "scientific_critic_sha256": (
            _canonical_sha256(scientific_critic_report)
            if scientific_critic_report is not None
            else None
        ),
        "validated_reasoning_proposal_sha256": (
            _canonical_sha256(validated_reasoning_proposal)
            if validated_reasoning_proposal is not None
            else None
        ),
        "characterization_evidence_binding_sha256": characterization_binding,
    }
    research_state_binding = _canonical_sha256(research_state_material)

    previous_state_binding = (
        previous_plan.get("research_state_binding_sha256")
        if isinstance(previous_plan, Mapping)
        else None
    )
    # New verified evidence/critic/reasoning state is a real research-state transition and
    # must not be mistaken for stagnation merely because the mission/program goal is unchanged.
    previous_for_base = (
        previous_plan
        if previous_plan is not None
        and previous_state_binding == research_state_binding
        else None
    )

    plan = build_self_directed_research_plan(
        program_state,
        critic_report=adapted_critic,
        validated_reasoning_proposal=validated_reasoning_proposal,
        previous_plan=previous_for_base,
        budget_units=budget_units,
        minimum_utility=minimum_utility,
        max_iterations=max_iterations,
    )
    if assessments:
        plan = apply_characterization_evidence_assessments(plan, assessments)

    result = {
        **plan,
        "research_agent_schema_version": RESEARCH_AGENT_SCHEMA_VERSION,
        "research_agent_policy_version": RESEARCH_AGENT_POLICY_VERSION,
        "research_state_binding_sha256": research_state_binding,
        "research_state_binding_material": research_state_material,
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

    # The lower planning layer protects against repeated program-only actions. This final
    # check extends stagnation across all verified inputs, including characterization
    # evidence, so repeated unchanged external evidence cannot manufacture progress.
    if (
        previous_plan is not None
        and previous_state_binding == research_state_binding
        and _selected_action_id(previous_plan) is not None
        and _selected_action_id(previous_plan) == _selected_action_id(result)
    ):
        result["selected_next_action"] = None
        result["stop_decision"] = {
            "stop": True,
            "reason": "stagnation_no_new_verified_research_state",
            "next_mode": "seek_new_evidence_path_or_revise_objective",
        }
        handoff = dict(result.get("handoff", {}))
        handoff["required_for_selected_action"] = False
        handoff["execution_performed"] = False
        result["handoff"] = handoff

    result.pop("plan_sha256", None)
    result["plan_sha256"] = _canonical_sha256(result)
    return result


__all__ = [
    "RESEARCH_AGENT_POLICY_VERSION",
    "RESEARCH_AGENT_SCHEMA_VERSION",
    "build_research_agent_iteration",
]
