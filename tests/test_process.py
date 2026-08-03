"""Tests for process-mode scoring helpers."""

from __future__ import annotations

import pandas as pd

from analyzers.process import calculate_target_score, build_multi_objective_scores


def test_calculate_target_score_maximize() -> None:
    scores = calculate_target_score(pd.Series([10, 20, 30]), goal="maximize")

    assert scores.tolist() == [0.0, 0.5, 1.0]


def test_calculate_target_score_minimize() -> None:
    scores = calculate_target_score(pd.Series([10, 20, 30]), goal="minimize")

    assert scores.tolist() == [1.0, 0.5, 0.0]


def test_build_multi_objective_scores_adds_score_columns_and_composite() -> None:
    df = pd.DataFrame(
        {
            "yield_percent": [80, 90, 100],
            "resistivity_ohm_cm": [5.0, 3.0, 1.0],
        }
    )

    result, score_columns = build_multi_objective_scores(
        df,
        target_columns=["yield_percent", "resistivity_ohm_cm"],
        goals=["maximize", "minimize"],
    )

    assert score_columns == ["score_yield_percent", "score_resistivity_ohm_cm"]
    assert "composite_score" in result.columns
    assert result["composite_score"].tolist() == [0.0, 0.5, 1.0]


def test_minimize_target_lower_value_gets_higher_score() -> None:
    df = pd.DataFrame({"resistivity_ohm_cm": [10.0, 5.0, 1.0]})

    result, _ = build_multi_objective_scores(
        df,
        target_columns=["resistivity_ohm_cm"],
        goals=["minimize"],
    )

    assert result.loc[2, "score_resistivity_ohm_cm"] > result.loc[0, "score_resistivity_ohm_cm"]


def test_multi_objective_incomplete_rows_are_not_ranked() -> None:
    df = pd.DataFrame(
        {
            "yield_percent": [80.0, 95.0],
            "resistivity_ohm_cm": [1.0, None],
        }
    )

    result, _ = build_multi_objective_scores(
        df,
        target_columns=["yield_percent", "resistivity_ohm_cm"],
        goals=["maximize", "minimize"],
    )

    assert bool(result.loc[0, "ranking_eligible"]) is True
    assert bool(result.loc[1, "ranking_eligible"]) is False
    assert pd.isna(result.loc[1, "composite_score"])
    assert result.loc[1, "ranking_exclusion_reason"] == "incomplete_multi_objective_targets"


def test_multi_objective_explicit_weights_are_normalized() -> None:
    df = pd.DataFrame(
        {
            "yield_percent": [80.0, 100.0],
            "resistivity_ohm_cm": [1.0, 5.0],
        }
    )

    result, _ = build_multi_objective_scores(
        df,
        target_columns=["yield_percent", "resistivity_ohm_cm"],
        goals=["maximize", "minimize"],
        weights=[3.0, 1.0],
    )

    assert result.loc[0, "composite_score"] == 0.25
    assert result.loc[1, "composite_score"] == 0.75
