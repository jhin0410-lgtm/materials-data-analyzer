"""Tests for simulation-mode validation and scenario ranking helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from analyzers.simulation import (
    build_scenario_predictions,
    validate_simulation_columns,
)


class DummyRegressionModel:
    """Small test model that returns deterministic predictions."""

    def predict(self, features: pd.DataFrame) -> pd.Series:
        return features["process_temp_c"] + features["pressure_mpa"] * 10


def test_validate_simulation_columns_missing_target_raises_value_error() -> None:
    df = pd.DataFrame({"feature_a": [1.0, 2.0]})

    with pytest.raises(ValueError):
        validate_simulation_columns(
            df=df,
            target="yield_percent",
            features=["feature_a"],
        )


def test_validate_simulation_columns_non_numeric_feature_raises_value_error() -> None:
    df = pd.DataFrame(
        {
            "yield_percent": [90.0, 95.0],
            "material": ["Al2O3", "TiO2"],
        }
    )

    with pytest.raises(ValueError):
        validate_simulation_columns(
            df=df,
            target="yield_percent",
            features=["material"],
        )


def test_build_scenario_predictions_creates_prediction_and_ranking() -> None:
    scenario_df = pd.DataFrame(
        {
            "scenario_id": ["low", "high"],
            "process_temp_c": [700.0, 800.0],
            "pressure_mpa": [1.0, 2.0],
        }
    )

    predictions, ranking, excluded_count = build_scenario_predictions(
        model=DummyRegressionModel(),
        scenario_df=scenario_df,
        feature_columns=["process_temp_c", "pressure_mpa"],
        target_column="yield_percent",
        goal="maximize",
    )

    assert excluded_count == 0
    assert "predicted_yield_percent" in predictions.columns
    assert ranking.loc[0, "scenario_id"] == "high"


def test_build_scenario_predictions_goal_changes_ranking_direction() -> None:
    scenario_df = pd.DataFrame(
        {
            "scenario_id": ["low", "high"],
            "process_temp_c": [700.0, 800.0],
            "pressure_mpa": [1.0, 2.0],
        }
    )

    _, maximize_ranking, _ = build_scenario_predictions(
        model=DummyRegressionModel(),
        scenario_df=scenario_df,
        feature_columns=["process_temp_c", "pressure_mpa"],
        target_column="yield_percent",
        goal="maximize",
    )
    _, minimize_ranking, _ = build_scenario_predictions(
        model=DummyRegressionModel(),
        scenario_df=scenario_df,
        feature_columns=["process_temp_c", "pressure_mpa"],
        target_column="yield_percent",
        goal="minimize",
    )

    assert maximize_ranking.loc[0, "scenario_id"] == "high"
    assert minimize_ranking.loc[0, "scenario_id"] == "low"
