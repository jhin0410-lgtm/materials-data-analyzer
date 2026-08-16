"""Higher-order self-directed research planning over the bounded inquiry contract.

The lower-level :mod:`autonomous_inquiry` module derives verified objectives, generic
rival hypotheses, evidence gaps, and ranks supplied candidate actions. This module adds
a conservative action-synthesis layer for evidence gaps and finite-iteration/stagnation
control. It is intentionally a *planner*, never a second executor.

Generated work is restricted to proposal-only analysis/evidence/simulation/experiment
design unless an already validated reasoning proposal supplies a typed local action.
Even then, execution authority remains with the existing independent authorization and
typed-executor chain.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .autonomous_inquiry import (
    AUTONOMOUS_INQUIRY_POLICY_VERSION,
    AUTONOMOUS_INQUIRY_SCHEMA_VERSION,
    AutonomousInquiryError,
    _canonical_sha256,
    _deduplicate_actions,
    _normalize_action,
    _stop_decision,
    build_autonomous_inquiry_plan,
)

SELF_DIRECTED_RESEARCH_SCHEMA_VERSION = "1.0"
SELF_DIRECTED_RESEARCH_POLICY_VERSION = "1.0"

_SOURCE_TERMS = {
    "source",
    "dataset",
    "archive",
    "raw",
    "lossless",
    "independent",
    "provenance",
    "checksum",
    "reuse",
    "external",
}
_EXPERIMENT_TERMS = {
    "sample",
    "acquisition",
    "trace",
    "measurement",
    "condition",
    "calibration",
    "detector",
    "replication",
    "specimen",
    "instrument",
}
_SIMULATION_TERMS = {
    "simulation",
    "thermodynamic",
    "kinetic",
    "diffusion",
    "phase-field",
    "finite element",
    "fem",
    "dft",
    "molecular dynamics",
}
_ANALYSIS_TERMS = {
    "sensitivity",
    "residual",
    "uncertainty",
    "baseline",
    "overlap",
    "duplicate",
    "stratification",
    "robustness",
}


def _contains_any(text: str, terms: set[str]) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in terms)


def _gap_action_specs(gap: Mapping[str, Any]) -> list[dict[str, Any]]:
    gap_id = str(gap.get("gap_id", "gap"))
    requirement = str(gap.get("requirement", "unresolved evidence requirement"))
    actions: list[dict[str, Any]] = []

    # Search is the least-assumptive way to resolve a missing empirical/source record.
    if _contains_any(requirement, _SOURCE_TERMS | _EXPERIMENT_TERMS):
        actions.append(
            {
                "action_id": f"{gap_id}:search-evidence",
                "action_class": "external_evidence_search",
                "description": f"Search for authoritative evidence satisfying: {requirement}",
                "rationale": (
                    "Resolve the declared evidence gap before generating or executing new work. "
                    "Any network acquisition requires the existing explicit authorization path."
                ),
                "required_evidence": [requirement],
                "expected_outcome": "A source candidate or a documented exhausted search space.",
                "execution_mode": "explicit_authorization_required",
                "expected_information_score": 0.8,
                "hypothesis_discrimination_score": 0.7,
                "feasibility_score": 0.6,
                "cost_units": 2.0,
                "risk_penalty": 0.05,
            }
        )

    if _contains_any(requirement, _ANALYSIS_TERMS):
        actions.append(
            {
                "action_id": f"{gap_id}:analysis-design",
                "action_class": "sensitivity_analysis",
                "description": f"Design a bounded reanalysis for: {requirement}",
                "rationale": "Test whether existing evidence can discriminate the gap without inventing data.",
                "required_evidence": [requirement],
                "expected_outcome": "A predeclared analysis contract or an explicit data insufficiency finding.",
                "execution_mode": "plan_only",
                "expected_information_score": 0.65,
                "hypothesis_discrimination_score": 0.7,
                "feasibility_score": 0.85,
                "cost_units": 1.25,
            }
        )

    if _contains_any(requirement, _SIMULATION_TERMS):
        actions.append(
            {
                "action_id": f"{gap_id}:simulation-design",
                "action_class": "simulation",
                "description": f"Design a solver-bounded simulation addressing: {requirement}",
                "rationale": (
                    "Use simulation only as separately labeled computational evidence and only "
                    "after solver/input/output provenance contracts are frozen."
                ),
                "required_evidence": [requirement],
                "expected_outcome": "A solver/input/output contract suitable for later authorized execution.",
                "execution_mode": "plan_only",
                "expected_information_score": 0.7,
                "hypothesis_discrimination_score": 0.75,
                "feasibility_score": 0.55,
                "cost_units": 2.5,
                "risk_penalty": 0.1,
            }
        )

    # A physical experiment is never executed here. It is proposed only when the gap
    # clearly asks for new samples, acquisitions, traces, measurements, calibration, or
    # independent replication that existing-data work cannot manufacture.
    if _contains_any(requirement, _EXPERIMENT_TERMS):
        actions.append(
            {
                "action_id": f"{gap_id}:experiment-design",
                "action_class": "physical_experiment_design",
                "description": f"Design an independent experiment to satisfy: {requirement}",
                "rationale": (
                    "The requirement appears empirical and cannot be satisfied by synthetic or "
                    "interpolated evidence. Facility safety and operator authorization remain external."
                ),
                "required_evidence": [requirement],
                "expected_outcome": (
                    "A predeclared acquisition design including identifiers, calibration, provenance, "
                    "replication, exclusions, and acceptance criteria."
                ),
                "execution_mode": "plan_only",
                "expected_information_score": 0.9,
                "hypothesis_discrimination_score": 0.9,
                "feasibility_score": 0.4,
                "cost_units": 4.0,
                "risk_penalty": 0.15,
            }
        )

    if not actions:
        actions.append(
            {
                "action_id": f"{gap_id}:manual-discrimination-design",
                "action_class": "manual_review",
                "description": f"Define a discriminating evidence path for: {requirement}",
                "rationale": (
                    "No safe deterministic action class can be inferred from the requirement text; "
                    "do not fabricate a domain-specific experiment or solver."
                ),
                "required_evidence": [requirement],
                "expected_outcome": "A bounded evidence or action specification for subsequent validation.",
                "execution_mode": "plan_only",
                "expected_information_score": 0.45,
                "hypothesis_discrimination_score": 0.55,
                "feasibility_score": 0.8,
                "cost_units": 1.5,
            }
        )
    return actions


def _synthesized_gap_actions(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    gaps = plan.get("evidence_gaps", [])
    if isinstance(gaps, (str, bytes)) or not isinstance(gaps, Sequence):
        raise AutonomousInquiryError("inquiry evidence_gaps must be a list")
    actions: list[dict[str, Any]] = []
    for gap in gaps:
        if not isinstance(gap, Mapping):
            raise AutonomousInquiryError("inquiry evidence_gaps must contain objects")
        for raw in _gap_action_specs(gap):
            actions.append(_normalize_action(raw, origin="self_generated_from_evidence_gap"))
    return actions


def _previous_iteration(previous_plan: Mapping[str, Any] | None) -> int:
    if previous_plan is None:
        return 0
    value = previous_plan.get("iteration_index")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AutonomousInquiryError("previous_plan.iteration_index must be a positive integer")
    return value


def _stagnated(
    previous_plan: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> bool:
    if previous_plan is None:
        return False
    previous_binding = previous_plan.get("program_binding")
    current_binding = current.get("program_binding")
    previous_action = previous_plan.get("selected_next_action")
    current_action = current.get("selected_next_action")
    if not isinstance(previous_binding, Mapping) or not isinstance(current_binding, Mapping):
        return False
    if previous_binding.get("canonical_sha256") != current_binding.get("canonical_sha256"):
        return False
    previous_id = previous_action.get("action_id") if isinstance(previous_action, Mapping) else None
    current_id = current_action.get("action_id") if isinstance(current_action, Mapping) else None
    return previous_id is not None and previous_id == current_id


def build_self_directed_research_plan(
    program_state: Mapping[str, Any],
    *,
    critic_report: Mapping[str, Any] | None = None,
    validated_reasoning_proposal: Mapping[str, Any] | None = None,
    previous_plan: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
    max_iterations: int = 8,
) -> dict[str, Any]:
    """Build one finite self-directed research iteration.

    Reinvoke only after the verified program/critic/reasoning state changes. Repeating the
    same selected action against an identical program binding is treated as stagnation,
    not as permission to loop forever.
    """
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise AutonomousInquiryError("max_iterations must be a positive integer")
    prior_iteration = _previous_iteration(previous_plan)
    iteration = prior_iteration + 1

    base = build_autonomous_inquiry_plan(
        program_state,
        critic_report=critic_report,
        validated_reasoning_proposal=validated_reasoning_proposal,
        budget_units=budget_units,
        minimum_utility=minimum_utility,
    )
    generated = _synthesized_gap_actions(base)
    existing = base.get("ranked_actions", [])
    if isinstance(existing, (str, bytes)) or not isinstance(existing, Sequence):
        raise AutonomousInquiryError("ranked_actions must be a list")
    ranked = _deduplicate_actions(
        [item for item in existing if isinstance(item, Mapping)] + generated
    )
    budget = float(base["planning_budget"]["budget_units"])
    threshold = float(base["planning_budget"]["minimum_utility"])
    stop = _stop_decision(
        objectives=base["research_objectives"],
        ranked_actions=ranked,
        budget_units=budget,
        minimum_utility=threshold,
    )
    affordable = [
        item
        for item in ranked
        if float(item["cost_units"]) <= budget
        and float(item["utility_score"]) >= threshold
    ]
    selected = dict(affordable[0]) if affordable and not stop["stop"] else None

    plan: dict[str, Any] = {
        **base,
        "schema_version": SELF_DIRECTED_RESEARCH_SCHEMA_VERSION,
        "policy_version": SELF_DIRECTED_RESEARCH_POLICY_VERSION,
        "parent_inquiry_contract": {
            "schema_version": AUTONOMOUS_INQUIRY_SCHEMA_VERSION,
            "policy_version": AUTONOMOUS_INQUIRY_POLICY_VERSION,
        },
        "iteration_index": iteration,
        "max_iterations": max_iterations,
        "self_generated_gap_actions": generated,
        "ranked_actions": ranked,
        "selected_next_action": selected,
        "stop_decision": stop,
        "objective_revision": base.get("objective_revision"),
        "handoff": {
            "required_for_selected_action": selected is not None,
            "destination": "existing_independent_action_authorization_and_typed_executor_chain",
            "request_compiled": False,
            "execution_performed": False,
        },
    }

    if iteration > max_iterations:
        plan["selected_next_action"] = None
        plan["stop_decision"] = {
            "stop": True,
            "reason": "maximum_iteration_guard_reached",
            "next_mode": "manual_or_mission_level_review",
        }
        plan["handoff"]["required_for_selected_action"] = False
    elif _stagnated(previous_plan, plan):
        plan["selected_next_action"] = None
        plan["stop_decision"] = {
            "stop": True,
            "reason": "stagnation_no_new_verified_evidence",
            "next_mode": "seek_new_evidence_path_or_revise_objective",
        }
        plan["handoff"]["required_for_selected_action"] = False

    if plan["stop_decision"]["reason"] in {
        "mission_scope_exhausted",
        "no_affordable_informative_action",
        "stagnation_no_new_verified_evidence",
        "maximum_iteration_guard_reached",
    }:
        plan["objective_revision"] = {
            "status": "proposal_only",
            "proposal": (
                "Re-evaluate unresolved evidence, competing hypotheses, information value, and "
                "mission success criteria. Spawn a successor objective only inside the externally "
                "supplied mission; otherwise terminate the current research scope."
            ),
            "mission_mutation_performed": False,
        }

    plan["autonomy_boundary"] = {
        **dict(base["autonomy_boundary"]),
        "evidence_gap_action_synthesis_performed": bool(generated),
        "iterative_stagnation_guard_active": True,
        "unregistered_solver_executed": False,
        "physical_facility_control_available": False,
        "second_executor_introduced": False,
    }
    plan.pop("plan_sha256", None)
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


__all__ = [
    "SELF_DIRECTED_RESEARCH_POLICY_VERSION",
    "SELF_DIRECTED_RESEARCH_SCHEMA_VERSION",
    "build_self_directed_research_plan",
]
