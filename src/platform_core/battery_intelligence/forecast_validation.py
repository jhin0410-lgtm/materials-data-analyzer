"""Battery-disjoint validation, conformal uncertainty, and OOD checks."""
from __future__ import annotations
import math
from typing import Any, Sequence
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from .common import BatteryIntelligenceConfig


def _metric_dict(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(math.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)) if len(actual) >= 2 else math.nan,
    }


def _group_oof_residuals(
    x: pd.DataFrame,
    y: np.ndarray,
    groups: np.ndarray,
    *,
    alpha: float,
    max_splits: int,
) -> np.ndarray:
    unique_groups = np.unique(groups)
    if len(unique_groups) < 3:
        return np.array([], dtype=float)
    splitter = GroupKFold(n_splits=min(max_splits, len(unique_groups)))
    residuals: list[float] = []
    for train_index, test_index in splitter.split(x, y, groups):
        model = Pipeline(
            [
                ("scale", StandardScaler()),
                ("ridge", Ridge(alpha=alpha)),
            ]
        )
        model.fit(x.iloc[train_index], y[train_index])
        prediction = model.predict(x.iloc[test_index])
        residuals.extend(np.abs(y[test_index] - prediction).tolist())
    return np.asarray(residuals, dtype=float)


def _finite_sample_conformal_quantile(
    residuals: np.ndarray,
    coverage: float,
) -> float:
    if len(residuals) == 0:
        return math.nan
    rank = math.ceil((len(residuals) + 1) * coverage) / len(residuals)
    rank = min(rank, 1.0)
    return float(np.quantile(residuals, rank, method="higher"))


def _ood_diagnostics(
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    train_min = train.min(axis=0).to_numpy(dtype=float)
    train_max = train.max(axis=0).to_numpy(dtype=float)
    train_iqr = (
        train.quantile(0.75, axis=0) - train.quantile(0.25, axis=0)
    ).to_numpy(dtype=float)
    train_std = train.std(axis=0, ddof=0).to_numpy(dtype=float)
    scale = np.where(
        train_iqr > 0,
        train_iqr,
        np.where(train_std > 0, train_std, 1.0),
    )
    values = test.to_numpy(dtype=float)
    below = values < train_min
    above = values > train_max
    outside_count = np.sum(below | above, axis=1)
    distance = np.maximum(train_min - values, values - train_max)
    distance = np.maximum(distance, 0.0) / scale
    max_distance = np.max(np.where(below | above, distance, 0.0), axis=1)
    max_distance = np.maximum(max_distance, 0.0)
    max_distance[outside_count == 0] = 0.0
    return outside_count.astype(int), max_distance.astype(float)


def evaluate_grouped_forecast(
    forecast_table: pd.DataFrame,
    feature_columns: Sequence[str],
    config: BatteryIntelligenceConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    groups = forecast_table[config.group_column].astype(str).to_numpy()
    unique_groups = np.unique(groups)
    if len(unique_groups) < 2:
        raise ValueError("at least two batteries are required for grouped validation")
    split_count = min(config.n_splits, len(unique_groups))
    splitter = GroupKFold(n_splits=split_count)
    x = forecast_table[list(feature_columns)].astype(float)
    y = forecast_table["future_target"].to_numpy(dtype=float)
    persistence = forecast_table["current_target"].to_numpy(dtype=float)

    prediction_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    leakage_violations = 0
    for fold, (train_index, test_index) in enumerate(
        splitter.split(x, y, groups), start=1
    ):
        train_groups = set(groups[train_index])
        test_groups = set(groups[test_index])
        overlap = sorted(train_groups & test_groups)
        if overlap:
            leakage_violations += 1
        model = Pipeline(
            [
                ("scale", StandardScaler()),
                ("ridge", Ridge(alpha=config.ridge_alpha)),
            ]
        )
        model.fit(x.iloc[train_index], y[train_index])
        ridge_prediction = model.predict(x.iloc[test_index])
        calibration_residuals = _group_oof_residuals(
            x.iloc[train_index].reset_index(drop=True),
            y[train_index],
            groups[train_index],
            alpha=config.ridge_alpha,
            max_splits=max(2, split_count - 1),
        )
        interval_half_width = _finite_sample_conformal_quantile(
            calibration_residuals,
            config.conformal_coverage,
        )
        outside_count, max_distance = _ood_diagnostics(
            x.iloc[train_index], x.iloc[test_index]
        )

        actual = y[test_index]
        baseline_prediction = persistence[test_index]
        ridge_metrics = _metric_dict(actual, ridge_prediction)
        baseline_metrics = _metric_dict(actual, baseline_prediction)
        fold_rows.append(
            {
                "fold": fold,
                "train_battery_count": len(train_groups),
                "test_battery_count": len(test_groups),
                "train_test_group_overlap_count": len(overlap),
                "calibration_residual_count": int(len(calibration_residuals)),
                "conformal_half_width": interval_half_width,
                "persistence_mae": baseline_metrics["mae"],
                "ridge_mae": ridge_metrics["mae"],
                "ridge_improvement_percent": float(
                    100.0
                    * (baseline_metrics["mae"] - ridge_metrics["mae"])
                    / max(baseline_metrics["mae"], np.finfo(float).eps)
                ),
            }
        )

        for local_position, row_index in enumerate(test_index):
            source = forecast_table.iloc[row_index]
            lower = (
                ridge_prediction[local_position] - interval_half_width
                if math.isfinite(interval_half_width)
                else math.nan
            )
            upper = (
                ridge_prediction[local_position] + interval_half_width
                if math.isfinite(interval_half_width)
                else math.nan
            )
            prediction_rows.append(
                {
                    "fold": fold,
                    config.group_column: source[config.group_column],
                    "origin_cycle": source["origin_cycle"],
                    "target_cycle": source["target_cycle"],
                    "actual": actual[local_position],
                    "persistence_prediction": baseline_prediction[local_position],
                    "ridge_prediction": ridge_prediction[local_position],
                    "prediction_interval_low": lower,
                    "prediction_interval_high": upper,
                    "interval_contains_actual": (
                        bool(lower <= actual[local_position] <= upper)
                        if math.isfinite(lower) and math.isfinite(upper)
                        else None
                    ),
                    "outside_training_range_feature_count": int(
                        outside_count[local_position]
                    ),
                    "maximum_normalized_extrapolation_distance": float(
                        max_distance[local_position]
                    ),
                    "prediction_outside_plausibility_range": bool(
                        ridge_prediction[local_position] < config.plausibility_min
                        or ridge_prediction[local_position] > config.plausibility_max
                    ),
                }
            )

    predictions = pd.DataFrame(prediction_rows)
    fold_metrics = pd.DataFrame(fold_rows)
    actual = predictions["actual"].to_numpy(dtype=float)
    baseline_prediction = predictions["persistence_prediction"].to_numpy(dtype=float)
    ridge_prediction = predictions["ridge_prediction"].to_numpy(dtype=float)
    baseline_metrics = _metric_dict(actual, baseline_prediction)
    ridge_metrics = _metric_dict(actual, ridge_prediction)

    per_group_rows: list[dict[str, Any]] = []
    for battery_id, group in predictions.groupby(config.group_column, sort=True):
        actual_group = group["actual"].to_numpy(dtype=float)
        baseline_group = group["persistence_prediction"].to_numpy(dtype=float)
        ridge_group = group["ridge_prediction"].to_numpy(dtype=float)
        baseline_mae = float(mean_absolute_error(actual_group, baseline_group))
        ridge_mae = float(mean_absolute_error(actual_group, ridge_group))
        per_group_rows.append(
            {
                config.group_column: battery_id,
                "prediction_count": int(len(group)),
                "persistence_mae": baseline_mae,
                "ridge_mae": ridge_mae,
                "ridge_improved": bool(ridge_mae < baseline_mae),
                "ridge_improvement_percent": float(
                    100.0
                    * (baseline_mae - ridge_mae)
                    / max(baseline_mae, np.finfo(float).eps)
                ),
                "ood_prediction_fraction": float(
                    np.mean(group["outside_training_range_feature_count"] > 0)
                ),
            }
        )
    per_group = pd.DataFrame(per_group_rows)

    interval_available = predictions["interval_contains_actual"].notna()
    coverage = (
        float(
            predictions.loc[
                interval_available, "interval_contains_actual"
            ].mean()
        )
        if interval_available.any()
        else math.nan
    )
    improved_group_count = int(per_group["ridge_improved"].sum())
    summary = {
        "split_method": "group_kfold",
        "split_count": int(split_count),
        "train_test_group_overlap_count": int(leakage_violations),
        "prediction_count": int(len(predictions)),
        "evaluated_battery_count": int(len(per_group)),
        "feature_columns": list(feature_columns),
        "persistence_metrics": baseline_metrics,
        "ridge_metrics": ridge_metrics,
        "ridge_improvement_percent": float(
            100.0
            * (baseline_metrics["mae"] - ridge_metrics["mae"])
            / max(baseline_metrics["mae"], np.finfo(float).eps)
        ),
        "improved_battery_count": improved_group_count,
        "not_improved_battery_count": int(len(per_group) - improved_group_count),
        "conformal_target_coverage": config.conformal_coverage,
        "conformal_observed_coverage": coverage,
        "interval_prediction_count": int(interval_available.sum()),
        "ood_prediction_fraction": float(
            np.mean(predictions["outside_training_range_feature_count"] > 0)
        ),
        "implausible_prediction_count": int(
            predictions["prediction_outside_plausibility_range"].sum()
        ),
    }
    return predictions, per_group, {
        "summary": summary,
        "folds": fold_metrics.to_dict(orient="records"),
    }
