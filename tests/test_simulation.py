"""Tests for simulation-mode validation and scenario ranking helpers."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pandas as pd
import pytest

from config import OutputPaths
from analyzers.simulation import (
    build_feature_summary_table,
    build_sensitivity_summary,
    build_scenario_predictions,
    generate_virtual_experiment_design,
    run_simulation_analysis,
    summarize_feature_ranges,
    validate_scenario_input,
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


def test_validate_simulation_columns_target_in_features_raises_value_error() -> None:
    df = pd.DataFrame(
        {
            "yield_percent": [90.0, 95.0],
            "process_temp_c": [700.0, 750.0],
        }
    )

    with pytest.raises(ValueError):
        validate_simulation_columns(
            df=df,
            target="yield_percent",
            features=["process_temp_c", "yield_percent"],
        )


def test_validate_scenario_input_missing_feature_raises_value_error() -> None:
    scenario_df = pd.DataFrame({"process_temp_c": [700.0, 750.0]})

    with pytest.raises(ValueError):
        validate_scenario_input(
            scenario_df=scenario_df,
            feature_columns=["process_temp_c", "pressure_mpa"],
        )


def test_generate_random_virtual_experiment_design_uses_observed_ranges() -> None:
    training_df = pd.DataFrame(
        {
            "process_temp_c": [650.0, 850.0],
            "pressure_mpa": [0.8, 1.5],
        }
    )
    feature_ranges = summarize_feature_ranges(
        training_df=training_df,
        feature_columns=["process_temp_c", "pressure_mpa"],
    )

    design_df = generate_virtual_experiment_design(
        feature_ranges=feature_ranges,
        method="random",
        n_samples=10,
        random_state=42,
    )

    assert len(design_df) == 10
    assert design_df["process_temp_c"].between(650.0, 850.0).all()
    assert design_df["pressure_mpa"].between(0.8, 1.5).all()
    assert "scenario_id" in design_df.columns


def test_generate_grid_virtual_experiment_design_creates_combinations() -> None:
    feature_ranges = pd.DataFrame(
        {
            "feature": ["process_temp_c", "pressure_mpa"],
            "min": [650.0, 0.8],
            "max": [850.0, 1.5],
            "mean": [750.0, 1.15],
            "std": [100.0, 0.35],
        }
    )

    design_df = generate_virtual_experiment_design(
        feature_ranges=feature_ranges,
        method="grid",
        grid_levels=3,
    )

    assert len(design_df) == 9
    assert sorted(design_df["process_temp_c"].unique().tolist()) == [
        650.0,
        750.0,
        850.0,
    ]


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


def test_build_sensitivity_summary_has_expected_columns() -> None:
    scenario_df = pd.DataFrame(
        {
            "scenario_id": ["low", "mid", "high"],
            "process_temp_c": [700.0, 750.0, 800.0],
            "pressure_mpa": [1.0, 1.5, 2.0],
            "predicted_yield_percent": [710.0, 765.0, 820.0],
        }
    )

    summary_df = build_sensitivity_summary(
        model=DummyRegressionModel(),
        design_or_prediction_df=scenario_df,
        feature_columns=["process_temp_c", "pressure_mpa"],
        target_column="yield_percent",
    )

    assert {
        "feature",
        "correlation_with_prediction",
        "sensitivity_metric",
        "interpretation_note",
    }.issubset(summary_df.columns)
    assert len(summary_df) == 2


def test_build_feature_summary_table_for_random_forest_model() -> None:
    class ModelWithImportances:
        feature_importances_ = [0.25, 0.75]

    summary_df = build_feature_summary_table(
        model=ModelWithImportances(),
        feature_columns=["process_temp_c", "pressure_mpa"],
    )

    assert "importance" in summary_df.columns
    assert summary_df.loc[0, "feature"] == "pressure_mpa"


def test_run_simulation_analysis_without_scenario_creates_virtual_outputs() -> None:
    output_root = (
        Path(__file__).resolve().parents[1]
        / "outputs"
        / f"pytest_virtual_experiment_{uuid.uuid4().hex}"
    )
    output_paths = OutputPaths(
        root=output_root,
        processed=output_root / "processed",
        figures=output_root / "figures",
        reports=output_root / "reports",
    )
    output_paths.root.mkdir(parents=True)
    output_paths.processed.mkdir()
    output_paths.figures.mkdir()
    output_paths.reports.mkdir()
    df = pd.DataFrame(
        {
            "process_temp_c": [650, 700, 750, 800, 850, 720, 780, 830],
            "process_time_min": [30, 35, 40, 45, 50, 32, 42, 48],
            "pressure_mpa": [0.8, 1.0, 1.1, 1.3, 1.5, 0.9, 1.2, 1.4],
            "thickness_um": [1.0, 1.2, 1.4, 1.7, 2.0, 1.1, 1.5, 1.8],
            "yield_percent": [80, 88, 92, 95, 98, 84, 93, 96],
        }
    )

    try:
        result = run_simulation_analysis(
            df=df,
            input_path=Path("demo.csv"),
            target="yield_percent",
            output_paths=output_paths,
            features=[
                "process_temp_c",
                "process_time_min",
                "pressure_mpa",
                "thickness_um",
            ],
            design_method="random",
            design_samples=12,
        )

        assert result["report"].exists()
        assert (output_paths.processed / "virtual_experiment_design.csv").exists()
        assert (
            output_paths.processed / "virtual_experiment_predictions.csv"
        ).exists()
        assert (output_paths.processed / "scenario_ranking.csv").exists()
        assert (output_paths.processed / "feature_summary.csv").exists()
        assert (output_paths.processed / "sensitivity_summary.csv").exists()
    finally:
        shutil.rmtree(output_root, ignore_errors=True)
