from __future__ import annotations

import hashlib

from materials_data_analyzer.research_loop.expected_information_gain import (
    expected_information_gain,
)
from materials_data_analyzer.research_loop.information_gain_prioritization import (
    prioritize_planner_actions,
)


def _action(action_id: str, utility: float = 0.2) -> dict[str, object]:
    return {
        "action_id": action_id,
        "action_class": "sensitivity_analysis",
        "execution_mode": "plan_only",
        "cost_units": 1.0,
        "utility_score": utility,
    }


def _eig(cost: float) -> dict[str, object]:
    return expected_information_gain(
        prior_hypothesis_probabilities=[0.5, 0.5],
        outcome_probabilities=[0.5, 0.5],
        posterior_probabilities_by_outcome=[[0.9, 0.1], [0.1, 0.9]],
        probabilistic_model_validated=True,
        model_artifact_sha256=hashlib.sha256(b"model").hexdigest(),
        action_cost_units=cost,
    )


def test_validated_eig_can_rerank_but_cannot_change_authority() -> None:
    result = prioritize_planner_actions(
        [_action("base-first"), _action("better-eig")],
        {"base-first": _eig(2.0), "better-eig": _eig(1.0)},
        budget_units=2.0,
        minimum_utility=0.01,
    )
    assert result["base_action_order"] == ["base-first", "better-eig"]
    assert result["prioritized_action_order"] == ["better-eig", "base-first"]
    assert result["selected_next_action"]["action_id"] == "better-eig"
    assert result["authorization_changed"] is False
    assert result["execution_mode_changed"] is False


def test_structural_proxy_does_not_outrank_base_planner() -> None:
    proxy = expected_information_gain(
        prior_hypothesis_probabilities=[0.5, 0.5],
        outcome_probabilities=[0.5, 0.5],
        posterior_probabilities_by_outcome=[[0.9, 0.1], [0.1, 0.9]],
        probabilistic_model_validated=False,
        model_artifact_sha256=None,
    )
    result = prioritize_planner_actions(
        [_action("first"), _action("second")],
        {"second": proxy},
        budget_units=2.0,
        minimum_utility=0.01,
    )
    assert result["prioritized_action_order"] == ["first", "second"]
    assert result["validated_eig_overrode_base_order"] is False
