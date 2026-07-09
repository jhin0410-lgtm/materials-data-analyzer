"""Tests for simulation-mode validation and scenario ranking helpers."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pandas as pd
import pytest

from config import OutputPaths
from analyzers.simulation import (
    add_or_clean_scenario_id,
    build_overfitting_diagnostics,
    build_feature_summary_table,
    build_sensitivity_summary,
    build_prediction_rows,
    build_scenario_predictions,
    build_train_test_metrics,
    calculate_cross_validation_metrics,
    create_surrogate_model,
    generate_virtual_experiment_design,
    run_simulation_analysis,
    split_model_validation_data,
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


def test_validate_scenario_input_non_numeric_feature_raises_value_error() -> None:
    scenario_df = pd.DataFrame(
        {
            "process_temp_c": [700.0, "not_numeric"],
            "pressure_mpa": [1.0, 1.2],
        }
    )

    with pytest.raises(ValueError, match="cannot be converted to numeric"):
        validate_scenario_input(
            scenario_df=scenario_df,
            feature_columns=["process_temp_c", "pressure_mpa"],
        )


def test_scenario_input_without_candidate_id_creates_candidate_ids() -> None:
    scenario_df = pd.DataFrame(
        {
            "process_temp_c": [700.0, 750.0],
            "pressure_mpa": [1.0, 1.2],
        }
    )

    prepared_df = add_or_clean_scenario_id(scenario_df)

    assert prepared_df["candidate_id"].tolist() == [
        "candidate_001",
        "candidate_002",
    ]
    assert prepared_df["scenario_id"].tolist() == [
        "candidate_001",
        "candidate_002",
    ]


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


def test_build_train_test_metrics_creates_train_and_test_rows() -> None:
    train_df = pd.DataFrame(
        {
            "process_temp_c": [700.0, 750.0, 800.0],
            "pressure_mpa": [1.0, 1.5, 2.0],
            "yield_percent": [710.0, 765.0, 820.0],
        }
    )
    test_df = pd.DataFrame(
        {
            "process_temp_c": [720.0, 780.0],
            "pressure_mpa": [1.2, 1.8],
            "yield_percent": [732.0, 798.0],
        }
    )

    metrics_df = build_train_test_metrics(
        model=DummyRegressionModel(),
        train_df=train_df,
        eval_df=test_df,
        feature_columns=["process_temp_c", "pressure_mpa"],
        target_column="yield_percent",
        metric_dataset="test",
        split_note="test split",
    )

    assert metrics_df["dataset"].tolist() == ["train", "test"]
    assert {"r2", "mae", "rmse"}.issubset(metrics_df.columns)


def test_overfitting_diagnostics_uses_possible_overfitting_language() -> None:
    metrics_df = pd.DataFrame(
        {
            "dataset": ["train", "test"],
            "row_count": [8, 2],
            "r2": [0.99, 0.10],
            "mae": [0.1, 3.0],
            "rmse": [0.2, 4.0],
            "note": ["split", "split"],
        }
    )

    diagnostics_df = build_overfitting_diagnostics(metrics_df)

    assert "possible overfitting signal" in " ".join(
        diagnostics_df["interpretation"].tolist()
    )


def test_cross_validation_split_count_adjusts_to_row_count() -> None:
    training_df = pd.DataFrame(
        {
            "process_temp_c": [float(650 + index * 10) for index in range(12)],
            "pressure_mpa": [0.8 + index * 0.05 for index in range(12)],
            "yield_percent": [80.0 + index for index in range(12)],
        }
    )
    model, _ = create_surrogate_model("random_forest")

    metrics_df = calculate_cross_validation_metrics(
        model=model,
        training_df=training_df,
        feature_columns=["process_temp_c", "pressure_mpa"],
        target_column="yield_percent",
    )

    assert len(metrics_df) == 5
    assert metrics_df["validation_type"].unique().tolist() == ["random_kfold"]


def test_group_split_keeps_battery_ids_out_of_both_train_and_test() -> None:
    training_df = pd.DataFrame(
        {
            "model_row_id": range(1, 13),
            "battery_id": [
                "B1",
                "B1",
                "B2",
                "B2",
                "B3",
                "B3",
                "B4",
                "B4",
                "B5",
                "B5",
                "B6",
                "B6",
            ],
            "cycle_index": list(range(1, 13)),
            "capacity_retention_percent": [
                100,
                98,
                96,
                94,
                92,
                90,
                88,
                86,
                84,
                82,
                80,
                78,
            ],
        }
    )

    train_df, test_df, _, metric_dataset, validation_type = split_model_validation_data(
        training_df=training_df,
        group_column="battery_id",
    )

    train_groups = set(train_df["battery_id"])
    test_groups = set(test_df["battery_id"])
    assert metric_dataset == "test"
    assert validation_type == "group_split_by_battery_id"
    assert train_groups.isdisjoint(test_groups)


def test_random_split_is_used_when_group_column_is_not_provided() -> None:
    training_df = pd.DataFrame(
        {
            "model_row_id": range(1, 13),
            "feature": [float(index) for index in range(12)],
            "target": [float(index * 2) for index in range(12)],
        }
    )

    _, _, split_note, metric_dataset, validation_type = split_model_validation_data(
        training_df=training_df,
        group_column=None,
    )

    assert metric_dataset == "test"
    assert validation_type == "random_split"
    assert "train/test split used" in split_note


def test_group_cross_validation_skips_when_group_count_is_too_small() -> None:
    training_df = pd.DataFrame(
        {
            "battery_id": ["B1", "B1", "B1", "B1", "B1"],
            "cycle_index": [1, 2, 3, 4, 5],
            "capacity_retention_percent": [100, 98, 96, 94, 92],
        }
    )
    model, _ = create_surrogate_model("random_forest")

    metrics_df = calculate_cross_validation_metrics(
        model=model,
        training_df=training_df,
        feature_columns=["cycle_index"],
        target_column="capacity_retention_percent",
        group_column="battery_id",
    )

    assert metrics_df.loc[0, "fold"] == "skipped"
    assert metrics_df.loc[0, "validation_type"] == "group_kfold_by_battery_id"
    assert "skipped" in metrics_df.loc[0, "note"]


def test_residuals_match_actual_minus_predicted() -> None:
    df = pd.DataFrame(
        {
            "model_row_id": [1, 2],
            "process_temp_c": [700.0, 800.0],
            "pressure_mpa": [1.0, 2.0],
            "yield_percent": [715.0, 825.0],
        }
    )

    predictions_df = build_prediction_rows(
        dataset_name="train",
        model=DummyRegressionModel(),
        dataset_df=df,
        feature_columns=["process_temp_c", "pressure_mpa"],
        target_column="yield_percent",
    )

    expected_residuals = predictions_df["actual"] - predictions_df["predicted"]
    pd.testing.assert_series_equal(
        predictions_df["residual"],
        expected_residuals,
        check_names=False,
    )


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
        assert (output_paths.processed / "train_test_metrics.csv").exists()
        assert (output_paths.processed / "overfitting_diagnostics.csv").exists()
        assert (output_paths.processed / "cross_validation_metrics.csv").exists()
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


def test_run_simulation_analysis_with_scenario_creates_candidate_predictions() -> None:
    output_root = (
        Path(__file__).resolve().parents[1]
        / "outputs"
        / f"pytest_candidate_predictions_{uuid.uuid4().hex}"
    )
    scenario_path = output_root / "candidate_conditions.csv"
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
    pd.DataFrame(
        {
            "process_temp_c": [700.0, 760.0, 820.0],
            "process_time_min": [30.0, 40.0, pd.NA],
            "pressure_mpa": [1.0, 1.2, 1.4],
            "thickness_um": [1.2, 1.5, 1.8],
            "note": ["baseline", "mid", "missing time"],
        }
    ).to_csv(scenario_path, index=False)
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
            scenario_input=str(scenario_path),
        )

        candidate_predictions_path = (
            output_paths.processed / "candidate_predictions.csv"
        )
        candidate_predictions = pd.read_csv(candidate_predictions_path)

        assert result["report"].exists()
        assert candidate_predictions_path.exists()
        assert (output_paths.processed / "scenario_predictions.csv").exists()
        assert (output_paths.processed / "scenario_ranking.csv").exists()
        assert candidate_predictions["candidate_id"].tolist() == [
            "candidate_001",
            "candidate_002",
            "candidate_003",
        ]
        assert "note" in candidate_predictions.columns
        assert {
            "candidate_id",
            "row_index",
            "predicted_target",
            "target_name",
            "model_type",
            "validation_status",
            "validation_message",
        }.issubset(candidate_predictions.columns)
        assert (
            candidate_predictions["validation_status"]
            == "excluded_missing_feature"
        ).sum() == 1
        assert "Candidate Prediction Summary" in result["report"].read_text(
            encoding="utf-8"
        )
    finally:
        shutil.rmtree(output_root, ignore_errors=True)
