"""Tests for generic time-aware classification validation utilities."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analyzers.temporal_classification_validation import (
    ClassificationModelConfig,
    ClassificationValidationConfig,
    compute_classification_metrics,
    default_classification_model_configs,
    evaluate_temporal_classification,
    fit_train_only_preprocessor,
    generate_validation_splits,
    transform_with_preprocessor,
    validate_binary_target,
    write_classification_outputs,
)


def _df(rows: int = 30) -> pd.DataFrame:
    target = [0] * rows
    for index in [5, 11, 17, 23, 29]:
        if index < rows:
            target[index] = 1
    return pd.DataFrame(
        {
            "sample_index": list(range(rows)),
            "observation_timestamp": pd.date_range("2020-01-01", periods=rows, freq="h"),
            "source_order_index": list(range(rows)),
            "chronological_rank": list(range(rows)),
            "target_failure": target,
            "process_feature_000": np.linspace(0, 1, rows),
            "process_feature_001": [1.0] * rows,
            "process_feature_002": [np.nan] * rows,
            "process_feature_003": [np.nan if i < 19 else float(i) for i in range(rows)],
            "process_feature_004": [float(i % 3) for i in range(rows)],
        }
    )


def _split_plan() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "split_name": "future_holdout",
                "split_type": "expanding_train_future_test",
                "train_rows": 20,
                "test_rows": 10,
                "train_failures": 3,
                "test_failures": 2,
                "feasibility_status": "feasible",
                "leakage_status": "no_future_to_past",
            }
        ]
    )


def _config() -> ClassificationValidationConfig:
    return ClassificationValidationConfig(
        case_study_version="test",
        source_artifact="synthetic.csv",
        source_sha256="abc123",
        identifier_column="sample_index",
        target_column="target_failure",
        timestamp_column="observation_timestamp",
        feature_columns=[
            "process_feature_000",
            "process_feature_001",
            "process_feature_002",
            "process_feature_003",
            "process_feature_004",
        ],
        model_configs=[
            ClassificationModelConfig("dummy_prior", "dummy_prior", 7),
            ClassificationModelConfig(
                "logistic_regression_balanced",
                "logistic_regression",
                7,
            ),
            ClassificationModelConfig("random_forest_balanced", "random_forest", 7),
        ],
        random_state=7,
    )


def test_chronological_split_ordering_and_no_sample_overlap() -> None:
    df = _df()
    splits = generate_validation_splits(df, _split_plan(), _config())
    temporal = [split for split in splits if split["validation_type"] == "primary_temporal"][0]

    assert max(temporal["train_index"]) < min(temporal["test_index"])
    assert set(temporal["train_index"]).isdisjoint(set(temporal["test_index"]))


def test_random_reference_is_labeled_not_primary() -> None:
    splits = generate_validation_splits(_df(), _split_plan(), _config())
    random_split = [split for split in splits if split["validation_type"] == "random_reference"][0]

    assert random_split["split_type"] == "stratified_random_reference"
    assert random_split["leakage_status"] == "optimistic_reference_not_primary"


def test_train_only_preprocessing_removes_columns_using_train_only_state() -> None:
    train = _df().iloc[:20]
    preprocessor = fit_train_only_preprocessor(
        train[_config().feature_columns],
        missing_rate_threshold=0.95,
        near_constant_top_value_rate=0.99,
    )

    assert "process_feature_001" in preprocessor.removed_features["constant"]
    assert "process_feature_002" in preprocessor.removed_features["all_missing"]
    assert "process_feature_003" in preprocessor.removed_features["high_missing"]
    assert "process_feature_004" in preprocessor.retained_features


def test_median_imputer_and_scaler_are_train_only() -> None:
    train = pd.DataFrame({"x": [1.0, 2.0, 100.0], "y": [0.0, 1.0, 2.0]})
    test = pd.DataFrame({"x": [np.nan], "y": [3.0]})
    preprocessor = fit_train_only_preprocessor(
        train,
        missing_rate_threshold=0.95,
        near_constant_top_value_rate=0.99,
    )

    transformed = transform_with_preprocessor(test, preprocessor, scale=False)
    scaled = transform_with_preprocessor(test, preprocessor, scale=True)

    assert transformed[0, preprocessor.retained_features.index("x")] == 2.0
    assert np.isfinite(scaled).all()


def test_invalid_binary_target_is_rejected() -> None:
    df = _df()
    df.loc[0, "target_failure"] = 2

    try:
        validate_binary_target(df, "target_failure")
    except ValueError as exc:
        assert "Target values" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("invalid target should be rejected")


def test_evaluator_runs_dummy_logistic_tree_and_is_deterministic() -> None:
    df = _df()
    config = _config()

    first = evaluate_temporal_classification(df, _split_plan(), config)
    second = evaluate_temporal_classification(df, _split_plan(), config)

    assert set(first["metrics"]["model_name"]) == {
        "dummy_prior",
        "logistic_regression_balanced",
        "random_forest_balanced",
    }
    assert first["metrics"]["average_precision"].fillna(-1).tolist() == second[
        "metrics"
    ]["average_precision"].fillna(-1).tolist()


def test_threshold_policy_and_prediction_schema() -> None:
    outputs = evaluate_temporal_classification(_df(), _split_plan(), _config())

    assert outputs["threshold_summary"]["threshold"].eq(0.5).all()
    assert not outputs["threshold_summary"]["threshold_selected_using_test_labels"].any()
    assert {
        "split_id",
        "validation_type",
        "model_name",
        "sample_index",
        "predicted_score",
        "is_false_negative",
        "row_missing_rate",
    }.issubset(outputs["predictions"].columns)


def test_one_class_metric_handling_records_unavailable_status() -> None:
    metrics = compute_classification_metrics(
        np.array([0, 0, 0]),
        np.array([0.1, 0.2, 0.3]),
        np.array([0, 0, 0]),
    )

    assert metrics["average_precision_status"] == "unavailable_one_class"
    assert metrics["roc_auc_status"] == "unavailable_one_class"


def test_default_models_are_fixed_classical_baselines() -> None:
    names = [config.name for config in default_classification_model_configs()]

    assert names == [
        "dummy_prior",
        "logistic_regression_balanced",
        "random_forest_balanced",
        "hist_gradient_boosting_balanced",
    ]


def test_write_outputs_creates_compact_and_prediction_csvs(tmp_path: Path) -> None:
    outputs = evaluate_temporal_classification(_df(), _split_plan(), _config())
    paths = {
        "predictions_path": tmp_path / "predictions.csv",
        "metrics_path": tmp_path / "metrics.csv",
        "split_diagnostics_path": tmp_path / "split.csv",
        "model_summary_path": tmp_path / "models.csv",
        "random_temporal_gap_path": tmp_path / "gap.csv",
        "threshold_summary_path": tmp_path / "threshold.csv",
        "error_structure_path": tmp_path / "errors.csv",
        "conclusion_path": tmp_path / "conclusion.csv",
    }

    write_classification_outputs(outputs, **paths)

    for path in paths.values():
        assert path.exists()
        assert not pd.read_csv(path).empty
