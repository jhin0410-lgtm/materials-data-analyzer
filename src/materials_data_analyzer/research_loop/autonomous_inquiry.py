"""Bounded self-directed inquiry planning over verified research-program state.

This module advances the research loop from blocker-oriented planning toward a bounded
hypothesis/action inquiry cycle. It may derive methodological rival hypotheses, evidence
gaps, follow-up objectives, and ranked analysis/simulation/experiment-design proposals
from already verified program, critic, and reasoning-proposal state.

It deliberately does *not* execute an action, access a network, operate equipment,
invent empirical evidence, assign calibrated scientific probabilities, or promote a
claim. Any executable candidate must still pass the existing independent authorization
and typed-executor chain. Physical experiments remain proposals only.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .kernel import ResearchLoopError

AUTONOMOUS_INQUIRY_SCHEMA_VERSION = "1.0"
AUTONOMOUS_INQUIRY_POLICY_VERSION = "1.0"

_ACTION_CLASSES = {
    "existing_data_reanalysis",
    "external_evidence_search",
    "computational_experiment",
    "sensitivity_analysis",
    "simulation",
    "physical_experiment_design",
    "replication",
    "manual_review",
}
_ACTION_KINDS = {
    "existing_data_reanalysis": "analysis",
    "external_evidence_search": "evidence_acquisition",
    "computational_experiment": "analysis",
    "sensitivity_analysis": "analysis",
    "simulation": "simulation",
    "physical_experiment_design": "experiment_design",
    "replication": "replication",
    "manual_review": "manual_review",
}
_PRIORITY_SCORE = {"critical": 1.0, "high": 0.8, "medium": 0.55, "low": 0.3}
_DEFAULT_COST = {
    "existing_data_reanalysis": 1.0,
    "sensitivity_analysis": 1.5,
    "computational_experiment": 2.0,
    "simulation": 3.0,
    "replication": 3.0,
    "external_evidence_search": 2.5,
    "manual_review": 2.0,
    "physical_experiment_design": 4.0,
}
_DEFAULT_FEASIBILITY = {
    "existing_data_reanalysis": 0.95,
    "sensitivity_analysis": 0.9,
    "computational_experiment": 0.8,
    "simulation": 0.7,
    "replication": 0.65,
    "external_evidence_search": 0.55,
    "manual_review": 0.75,
    "physical_experiment_design": 0.45,
}


class AutonomousInquiryError(ResearchLoopError):
    """Raised when bounded autonomous inquiry cannot preserve its trust boundary."""


def _canonical_sha256(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AutonomousInquiryError("inquiry input must be canonical-JSON serializable") from exc
    return hashlib.sha256(encoded).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AutonomousInquiryError(f"{field} must be non-empty text")
    return value.strip()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AutonomousInquiryError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AutonomousInquiryError(f"{field} must be a list")
    return value


def _bounded_number(value: object, field: str, *, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AutonomousInquiryError(f"{field} must be numeric")
    numeric = float(value)
    if not low <= numeric <= high:
        raise AutonomousInquiryError(f"{field} must be between {low} and {high}")
    return numeric


def _mission_policy(program_state: Mapping[str, Any]) -> Mapping[str, Any]:
    mission = _mapping(program_state.get("mission"), "program_state.mission")
    return _mapping(mission.get("autonomy_policy"), "mission.autonomy_policy")


def _generated_goals(program_state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = _sequence(program_state.get("generated_goals"), "program_state.generated_goals")
    result = [item for item in raw if isinstance(item, Mapping)]
    if len(result) != len(raw):
        raise AutonomousInquiryError("generated_goals must contain only objects")
    return result


def _goal_objectives(program_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    objectives: list[dict[str, Any]] = []
    for goal in _generated_goals(program_state):
        goal_id = _text(goal.get("goal_id"), "goal.goal_id")
        status = _text(goal.get("status"), f"{goal_id}.status")
        requirements_raw = goal.get("evidence_requirements", [])
        requirements = [
            _text(item, f"{goal_id}.evidence_requirements")
            for item in _sequence(requirements_raw, f"{goal_id}.evidence_requirements")
        ]
        objectives.append(
            {
                "objective_id": f"inquiry:{goal_id}",
                "goal_id": goal_id,
                "workstream_id": goal.get("workstream_id"),
                "research_question": _text(
                    goal.get("research_question"), f"{goal_id}.research_question"
                ),
                "objective": _text(goal.get("goal_statement"), f"{goal_id}.goal_statement"),
                "status": status,
                "priority": goal.get("priority"),
                "evidence_requirements": requirements,
                "claim_boundary": goal.get("claim_boundary"),
                "origin": "verified_program_goal",
            }
        )
    return objectives


def _methodological_rivals(objective: Mapping[str, Any]) -> list[dict[str, Any]]:
    objective_id = _text(objective.get("objective_id"), "objective.objective_id")
    requirements = objective.get("evidence_requirements", [])
    gap_text = "; ".join(str(item) for item in requirements) or "current verified evidence gap"
    return [
        {
            "hypothesis_id": f"{objective_id}:h-evidence-sufficient-after-gap",
            "hypothesis_type": "readiness_alternative",
            "statement": (
                "Resolving the declared evidence gap is sufficient to make the target claim "
                "eligible for re-evaluation within its existing claim boundary."
            ),
            "falsification_criteria": [
                "The required evidence is acquired but the domain gate remains blocked.",
                "New verified contradictory or falsifying evidence appears.",
            ],
            "discriminating_evidence": list(requirements),
            "scientific_mechanism_claim": False,
            "status": "candidate_not_evidence_upgraded",
        },
        {
            "hypothesis_id": f"{objective_id}:h-artifact-or-bias",
            "hypothesis_type": "methodological_rival",
            "statement": (
                "The apparent finding or blocker may be materially affected by measurement, "
                "preprocessing, sampling, calibration, provenance, or analysis artifacts rather "
                "than the intended scientific effect."
            ),
            "falsification_criteria": [
                "Independent provenance-preserving replication remains consistent.",
                "Sensitivity and negative-control analyses exclude material artifact sensitivity.",
            ],
            "discriminating_evidence": [
                "Independent replication or orthogonal measurement",
                "Predeclared sensitivity/negative-control analysis",
                gap_text,
            ],
            "scientific_mechanism_claim": False,
            "status": "candidate_not_evidence_upgraded",
        },
        {
            "hypothesis_id": f"{objective_id}:h-scope-limited-null",
            "hypothesis_type": "null_or_scope_rival",
            "statement": (
                "The current evidence may not support a stable effect beyond the verified source, "
                "sample, acquisition, condition, or protocol scope."
            ),
            "falsification_criteria": [
                "A predeclared independent or scope-expanded replication supports the same result.",
            ],
            "discriminating_evidence": [
                "Independent sample/acquisition or condition coverage",
                "Predeclared replication with source identity separated from development evidence",
            ],
            "scientific_mechanism_claim": False,
            "status": "candidate_not_evidence_upgraded",
        },
    ]


def _critic_targets(critic_report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if critic_report is None:
        return []
    targets_raw = critic_report.get("targets")
    if targets_raw is None:
        targets_raw = critic_report.get("target_reviews", [])
    targets = _sequence(targets_raw, "critic_report targets")
    alternatives: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, Mapping):
            raise AutonomousInquiryError("critic targets must contain only objects")
        for raw in _sequence(target.get("alternatives", []), "critic alternatives"):
            item = _mapping(raw, "critic alternative")
            alternatives.append(dict(item))
    return alternatives


def _proposal_hypotheses(
    validated_reasoning_proposal: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if validated_reasoning_proposal is None:
        return []
    if validated_reasoning_proposal.get("proposal_status") != "validated_for_planning_only":
        raise AutonomousInquiryError(
            "reasoning proposal must already be validated_for_planning_only"
        )
    result: list[dict[str, Any]] = []
    for raw in _sequence(
        validated_reasoning_proposal.get("new_hypotheses", []),
        "validated reasoning proposal hypotheses",
    ):
        item = _mapping(raw, "reasoning proposal hypothesis")
        result.append(dict(item))
    return result


def _normalize_action(
    raw: Mapping[str, Any],
    *,
    origin: str,
    ordinal_priority: str | None = None,
) -> dict[str, Any]:
    action_id = _text(raw.get("action_id"), "action.action_id")
    action_class = _text(raw.get("action_class"), f"{action_id}.action_class")
    if action_class not in _ACTION_CLASSES:
        raise AutonomousInquiryError(f"unsupported action_class: {action_class}")
    priority = ordinal_priority or str(raw.get("information_gain_priority", "medium"))
    if priority not in _PRIORITY_SCORE:
        priority = "medium"

    expected_information = raw.get("expected_information_score")
    if expected_information is None:
        expected_information = _PRIORITY_SCORE[priority]
    information_score = _bounded_number(
        expected_information,
        f"{action_id}.expected_information_score",
        low=0.0,
        high=1.0,
    )
    discrimination = raw.get("hypothesis_discrimination_score")
    if discrimination is None:
        discrimination = information_score
    discrimination_score = _bounded_number(
        discrimination,
        f"{action_id}.hypothesis_discrimination_score",
        low=0.0,
        high=1.0,
    )
    feasibility = _bounded_number(
        raw.get("feasibility_score", _DEFAULT_FEASIBILITY[action_class]),
        f"{action_id}.feasibility_score",
        low=0.0,
        high=1.0,
    )
    cost = _bounded_number(
        raw.get("cost_units", _DEFAULT_COST[action_class]),
        f"{action_id}.cost_units",
        low=0.01,
        high=1_000_000.0,
    )
    risk_penalty = _bounded_number(
        raw.get("risk_penalty", 0.0),
        f"{action_id}.risk_penalty",
        low=0.0,
        high=1.0,
    )
    utility = information_score * discrimination_score * feasibility * (1.0 - risk_penalty) / cost

    execution_mode = str(raw.get("execution_mode", "plan_only"))
    if action_class == "physical_experiment_design":
        execution_mode = "plan_only"
    if action_class == "external_evidence_search" and execution_mode == "typed_local_action":
        execution_mode = "explicit_authorization_required"

    return {
        "action_id": action_id,
        "action_class": action_class,
        "action_kind": _ACTION_KINDS[action_class],
        "description": str(raw.get("description") or raw.get("summary") or action_id),
        "rationale": str(raw.get("rationale") or "Resolve a verified evidence gap."),
        "required_evidence": list(raw.get("required_evidence", []))
        if isinstance(raw.get("required_evidence", []), list)
        else [],
        "expected_outcome": str(
            raw.get("expected_outcome")
            or raw.get("expected_discrimination")
            or "Produce evidence that can be independently re-gated."
        ),
        "execution_mode": execution_mode,
        "origin": origin,
        "expected_information_score": information_score,
        "hypothesis_discrimination_score": discrimination_score,
        "feasibility_score": feasibility,
        "cost_units": cost,
        "risk_penalty": risk_penalty,
        "utility_score": round(utility, 12),
        "utility_is_calibrated_probability": False,
        "automatic_execution_authorized": False,
        "physical_experiment_execution_authorized": False,
    }


def _goal_frontier_actions(program_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for goal in _generated_goals(program_state):
        goal_id = _text(goal.get("goal_id"), "goal.goal_id")
        frontier = _sequence(goal.get("action_frontier", []), f"{goal_id}.action_frontier")
        for index, raw in enumerate(frontier):
            item = _mapping(raw, f"{goal_id}.action_frontier[{index}]")
            action_class = item.get("action_class") or item.get("category")
            if action_class not in _ACTION_CLASSES:
                # Existing domain frontiers can carry executor-specific categories. They remain
                # visible to the existing planner but are not reinterpreted here.
                continue
            normalized = dict(item)
            normalized.setdefault("action_id", f"{goal_id}:frontier:{index}")
            normalized["action_class"] = action_class
            result.append(_normalize_action(normalized, origin="verified_goal_frontier"))
    return result


def _critic_actions(critic_report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if critic_report is None:
        return []
    targets_raw = critic_report.get("targets")
    if targets_raw is None:
        targets_raw = critic_report.get("target_reviews", [])
    targets = _sequence(targets_raw, "critic_report targets")
    result: list[dict[str, Any]] = []
    for target in targets:
        item = _mapping(target, "critic target")
        for raw in _sequence(item.get("proposed_actions", item.get("actions", [])), "critic actions"):
            action = _mapping(raw, "critic action")
            priority = str(action.get("information_gain_priority", "medium"))
            result.append(
                _normalize_action(action, origin="scientific_critic", ordinal_priority=priority)
            )
    return result


def _proposal_actions(
    validated_reasoning_proposal: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if validated_reasoning_proposal is None:
        return []
    result: list[dict[str, Any]] = []
    for raw in _sequence(
        validated_reasoning_proposal.get("proposed_actions", []),
        "validated reasoning proposal actions",
    ):
        result.append(_normalize_action(_mapping(raw, "proposal action"), origin="reasoning_proposal"))
    return result


def _deduplicate_actions(actions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[str, dict[str, Any]] = {}
    for action in actions:
        action_id = _text(action.get("action_id"), "action.action_id")
        candidate = dict(action)
        previous = chosen.get(action_id)
        if previous is None or float(candidate["utility_score"]) > float(previous["utility_score"]):
            chosen[action_id] = candidate
    return sorted(
        chosen.values(),
        key=lambda item: (-float(item["utility_score"]), float(item["cost_units"]), str(item["action_id"])),
    )


def _evidence_gaps(objectives: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for objective in objectives:
        objective_id = _text(objective.get("objective_id"), "objective.objective_id")
        for index, requirement in enumerate(objective.get("evidence_requirements", [])):
            result.append(
                {
                    "gap_id": f"{objective_id}:gap:{index + 1}",
                    "objective_id": objective_id,
                    "requirement": str(requirement),
                    "status": "unresolved_from_verified_program_state",
                    "may_be_filled_by_synthetic_evidence": False,
                }
            )
    return result


def _stop_decision(
    *,
    objectives: Sequence[Mapping[str, Any]],
    ranked_actions: Sequence[Mapping[str, Any]],
    budget_units: float,
    minimum_utility: float,
) -> dict[str, Any]:
    active = [item for item in objectives if item.get("status") not in {"scope_exhausted"}]
    if not active:
        return {"stop": True, "reason": "mission_scope_exhausted", "next_mode": "revise_objective"}
    if budget_units <= 0:
        return {"stop": True, "reason": "budget_exhausted", "next_mode": "await_budget_or_revise_scope"}
    affordable = [
        item
        for item in ranked_actions
        if float(item["cost_units"]) <= budget_units
        and float(item["utility_score"]) >= minimum_utility
    ]
    if not affordable:
        return {
            "stop": True,
            "reason": "no_affordable_informative_action",
            "next_mode": "seek_new_evidence_path_or_revise_objective",
        }
    return {
        "stop": False,
        "reason": "informative_action_available",
        "next_mode": "request_existing_authorization_chain",
    }


def build_autonomous_inquiry_plan(
    program_state: Mapping[str, Any],
    *,
    critic_report: Mapping[str, Any] | None = None,
    validated_reasoning_proposal: Mapping[str, Any] | None = None,
    budget_units: float = 8.0,
    minimum_utility: float = 0.01,
) -> dict[str, Any]:
    """Build one bounded self-directed inquiry plan without granting execution authority.

    The score is a deterministic planning heuristic, not a posterior probability or a
    calibrated expected-information-gain estimate. Its only role is ordering already
    permitted candidate work under explicit cost/feasibility assumptions.
    """
    policy = _mission_policy(program_state)
    if policy.get("goal_generation") != "bounded_autonomous":
        raise AutonomousInquiryError("mission does not permit bounded autonomous goal generation")

    budget = _bounded_number(budget_units, "budget_units", low=0.0, high=1_000_000.0)
    threshold = _bounded_number(minimum_utility, "minimum_utility", low=0.0, high=1.0)
    objectives = _goal_objectives(program_state)
    gaps = _evidence_gaps(objectives)

    hypotheses: list[dict[str, Any]] = []
    for objective in objectives:
        hypotheses.extend(_methodological_rivals(objective))
    hypotheses.extend(_critic_targets(critic_report))
    hypotheses.extend(_proposal_hypotheses(validated_reasoning_proposal))

    actions = _goal_frontier_actions(program_state)
    actions.extend(_critic_actions(critic_report))
    actions.extend(_proposal_actions(validated_reasoning_proposal))
    ranked_actions = _deduplicate_actions(actions)

    stop = _stop_decision(
        objectives=objectives,
        ranked_actions=ranked_actions,
        budget_units=budget,
        minimum_utility=threshold,
    )
    eligible = [
        item
        for item in ranked_actions
        if float(item["cost_units"]) <= budget
        and float(item["utility_score"]) >= threshold
    ]
    selected = dict(eligible[0]) if eligible and not stop["stop"] else None

    objective_revision = None
    if stop["reason"] in {"mission_scope_exhausted", "no_affordable_informative_action"}:
        objective_revision = {
            "status": "proposal_only",
            "proposal": (
                "Reassess the mission success criteria and unresolved evidence gaps, then spawn "
                "a bounded successor objective only if it remains inside the externally supplied "
                "mission and autonomy policy."
            ),
            "mission_mutation_performed": False,
        }

    result = {
        "schema_version": AUTONOMOUS_INQUIRY_SCHEMA_VERSION,
        "policy_version": AUTONOMOUS_INQUIRY_POLICY_VERSION,
        "program_binding": {"canonical_sha256": _canonical_sha256(program_state)},
        "critic_binding": (
            {"canonical_sha256": _canonical_sha256(critic_report)}
            if critic_report is not None
            else None
        ),
        "reasoning_proposal_binding": (
            {"canonical_sha256": _canonical_sha256(validated_reasoning_proposal)}
            if validated_reasoning_proposal is not None
            else None
        ),
        "planning_budget": {
            "budget_units": budget,
            "minimum_utility": threshold,
            "score_semantics": "deterministic_nonprobabilistic_planning_heuristic",
        },
        "research_objectives": objectives,
        "evidence_gaps": gaps,
        "candidate_hypotheses": hypotheses,
        "ranked_actions": ranked_actions,
        "selected_next_action": selected,
        "stop_decision": stop,
        "objective_revision": objective_revision,
        "handoff": {
            "required_for_selected_action": selected is not None,
            "destination": "existing_independent_action_authorization_and_typed_executor_chain",
            "request_compiled": False,
            "execution_performed": False,
        },
        "autonomy_boundary": {
            "bounded_goal_derivation_performed": True,
            "methodological_rival_hypotheses_generated": bool(objectives),
            "domain_mechanism_truth_invented": False,
            "empirical_evidence_created": False,
            "calibrated_probability_claimed": False,
            "network_access_performed": False,
            "physical_experiment_execution_performed": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
            "mission_mutated": False,
        },
    }
    result["plan_sha256"] = _canonical_sha256(result)
    return result


__all__ = [
    "AUTONOMOUS_INQUIRY_POLICY_VERSION",
    "AUTONOMOUS_INQUIRY_SCHEMA_VERSION",
    "AutonomousInquiryError",
    "build_autonomous_inquiry_plan",
]
