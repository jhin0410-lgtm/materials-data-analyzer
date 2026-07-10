"""Tests for generic grouped regression validation utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analyzers.grouped_regression_validation import (
    ModelConfig,
    SplitConfig,
    ValidationConfig,
    compute_metric_bundle,
    compute_screening_metrics,
    default_model_configs,
    evaluate_validation,
    generate_splits,
    validate_feature_columns,
)


def _df() -> pd.DataFrame:
    rows = []
    for i in range(40):
        group = f"formula_{i // 4}"
        chemsys = f"system_{i // 10}"
        rows.append(
            {
                "material_id": f"mp-{i:03d}",
                "x1": float(i % 7),
                "x2": float((i // 3) % 5),
                "target": float((i % 7) * 0.1 + (i // 10) * 0.05),
                "reduced_formula_group": group,
                "chemical_system_group": chemsys,
                "theoretical": bool(i % 2),
                "ambiguity_group_status": "ambiguous_formula_group"
                if i % 5 == 0
                else "singleton_formula_group",
            }
        )
    return pd.DataFrame(rows)


def _config(n_splits: int = 3) -> ValidationConfig:
    return ValidationConfig(
        identifier_column="material_id",
        target_column="target",
        feature_columns=["x1", "x2"],
        split_configs=[
            SplitConfig("random", "shuffle", n_splits=n_splits, test_size=0.25, random_state=42),
            SplitConfig(
                "reduced_formula_group",
                "group_shuffle",
                "reduced_formula_group",
                n_splits=n_splits,
                test_size=0.25,
                random_state=42,
            ),
        ],
        model_configs=[
            ModelConfig("dummy_median", "dummy_median", "raw"),
            ModelConfig("ridge_log1p", "ridge", "log1p", alpha=1.0),
        ],
        theoretical_column="theoretical",
        formula_group_column="reduced_formula_group",
        chemical_system_group_column="chemical_system_group",
        ambiguity_group_column="ambiguity_group_status",
    )


def test_random_split_is_deterministic() -> None:
    df = _df()
    config = SplitConfig("random", "shuffle", n_splits=3, test_size=0.25, random_state=42)

    first = generate_splits(df, config)
    second = generate_splits(df, config)

    assert [split["test_index"].tolist() for split in first] == [
        split["test_index"].tolist() for split in second
    ]
    assert len(first) == 3


def test_group_split_has_zero_group_overlap() -> None:
    df = _df()
    config = SplitConfig(
        "reduced_formula_group",
        "group_shuffle",
        "reduced_formula_group",
        n_splits=3,
        test_size=0.25,
        random_state=42,
    )

    splits = generate_splits(df, config)

    assert len(splits) == 3
    for split in splits:
        train_groups = set(df.iloc[split["train_index"]]["reduced_formula_group"])
        test_groups = set(df.iloc[split["test_index"]]["reduced_formula_group"])
        assert train_groups.isdisjoint(test_groups)
        assert split["status"] == "valid"


def test_invalid_group_split_is_recorded_not_replaced() -> None:
    df = _df()
    df["one_group"] = "same"
    config = SplitConfig(
        "one_group",
        "group_shuffle",
        "one_group",
        n_splits=3,
        test_size=0.25,
        random_state=42,
    )

    splits = generate_splits(df, config)

    assert len(splits) == 3
    assert {split["status"] for split in splits} == {"invalid"}
    assert {split["invalid_reason"] for split in splits} == {"too few groups"}


def test_forbidden_feature_rejection_includes_target() -> None:
    df = _df()

    with pytest.raises(ValueError, match="Forbidden"):
        validate_feature_columns(df, ["x1", "target"], ["material_id"], "target")


def test_evaluator_runs_fixed_models_and_preserves_negative_r2() -> None:
    df = _df()
    outputs = evaluate_validation(df, _config(n_splits=2), forbidden_features=["material_id"])
    metrics = outputs["metrics"]

    assert set(metrics["model_variant"]) == {"dummy_median", "ridge_log1p"}
    assert len(metrics) == 8
    assert "r2" in metrics.columns
    assert metrics["r2"].notna().any()
    assert metrics["status"].eq("valid").all()


def test_log1p_inverse_and_negative_prediction_clipping_metrics() -> None:
    y_true = np.array([0.0, 1.0, 2.0])
    raw_prediction = np.array([-0.5, 0.5, 4.0])
    constrained = np.maximum(raw_prediction, 0)
    negative = raw_prediction < 0
    prediction_df = pd.DataFrame(
        {
            "material_id": ["a", "b", "c"],
            "actual_target": y_true,
            "constrained_prediction": constrained,
            "absolute_error": np.abs(y_true - constrained),
            "descriptor_seen_in_train": [True, False, False],
            "formula_seen_in_train": [True, True, False],
            "chemical_system_seen_in_train": [True, True, True],
        }
    )

    metrics = compute_metric_bundle(
        y_true=y_true,
        raw_prediction=raw_prediction,
        constrained_prediction=constrained,
        negative_prediction=negative,
        prediction_df=prediction_df,
    )

    assert metrics["negative_prediction_count"] == 1
    assert metrics["negative_prediction_rate"] == pytest.approx(1 / 3)
    assert metrics["raw_prediction_mae"] >= 0
    assert metrics["r2"] < 0


def test_screening_metrics_are_deterministic() -> None:
    prediction_df = pd.DataFrame(
        {
            "material_id": ["b", "a", "c", "d", "e"],
            "actual_target": [0.0, 0.0, 0.5, 1.0, 2.0],
            "constrained_prediction": [0.2, 0.1, 0.4, 1.0, 1.5],
        }
    )

    metrics = compute_screening_metrics(prediction_df)

    assert metrics["precision_at_20pct"] == 1.0
    assert metrics["recall_at_20pct"] == 1.0
    assert metrics["exact_zero_target_recall_at_20pct"] == 0.5


def test_default_model_configs_are_fixed_baselines() -> None:
    names = [config.name for config in default_model_configs()]

    assert names == [
        "dummy_median",
        "ridge_raw",
        "ridge_log1p",
        "histogram_gradient_boosting_raw",
        "histogram_gradient_boosting_log1p",
    ]
