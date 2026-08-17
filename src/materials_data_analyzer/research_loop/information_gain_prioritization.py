"""Post-planner prioritization using validated expected information gain.

The base planner intentionally uses heuristic information scores.  This bridge permits an
already-generated action frontier to be re-ranked by *validated* probabilistic EIG without
changing action classes, authorization, cost, or executor semantics.  Actions without true
EIG retain their base ordering after EIG-ranked actions.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .expected_information_gain import rank_actions_by_eig
from .kernel import ResearchLoopError

INFORMATION_GAIN_PRIORITIZATION_VERSION = "1.0"


class InformationGainPrioritizationError(ResearchLoopError):
    """Raised when EIG bindings do not correspond to a planner action frontier."""


def prioritize_planner_actions(
    ranked_actions: Sequence[Mapping[str, Any]],
    eig_results: Mapping[str, Mapping[str, Any]],
    *,
    budget_units: float,
    minimum_utility: float,
) -> dict[str, Any]:
    if isinstance(budget_units, bool) or not isinstance(budget_units, (int, float)):
        raise InformationGainPrioritizationError("budget_units must be numeric")
    if budget_units < 0:
        raise InformationGainPrioritizationError("budget_units must be non-negative")
    if isinstance(minimum_utility, bool) or not isinstance(minimum_utility, (int, float)):
        raise InformationGainPrioritizationError("minimum_utility must be numeric")
    actions = [dict(action) for action in ranked_actions]
    ids: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for action in actions:
        action_id = action.get("action_id")
        if not isinstance(action_id, str) or not action_id:
            raise InformationGainPrioritizationError("all actions require action_id")
        if action_id in by_id:
            raise InformationGainPrioritizationError("action_id values must be unique")
        ids.append(action_id)
        by_id[action_id] = action
    unknown = sorted(set(eig_results) - set(ids))
    if unknown:
        raise InformationGainPrioritizationError(
            "EIG results reference unknown planner actions: " + ", ".join(unknown)
        )

    probabilistic_rank = rank_actions_by_eig(eig_results)
    eig_ids = [item["action_id"] for item in probabilistic_rank]
    ordered_ids = eig_ids + [action_id for action_id in ids if action_id not in eig_ids]
    reranked = [by_id[action_id] for action_id in ordered_ids]
    affordable = []
    for action in reranked:
        try:
            cost = float(action["cost_units"])
            utility = float(action["utility_score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InformationGainPrioritizationError(
                "planner action is missing numeric cost/utility"
            ) from exc
        if cost <= float(budget_units) and utility >= float(minimum_utility):
            affordable.append(action)
    selected = dict(affordable[0]) if affordable else None
    return {
        "policy_version": INFORMATION_GAIN_PRIORITIZATION_VERSION,
        "base_action_order": ids,
        "validated_eig_action_order": eig_ids,
        "prioritized_action_order": ordered_ids,
        "selected_next_action": selected,
        "validated_eig_overrode_base_order": bool(eig_ids and ordered_ids != ids),
        "authorization_changed": False,
        "execution_mode_changed": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "INFORMATION_GAIN_PRIORITIZATION_VERSION",
    "InformationGainPrioritizationError",
    "prioritize_planner_actions",
]
