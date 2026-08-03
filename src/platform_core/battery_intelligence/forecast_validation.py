"""Battery-disjoint validation, transparent baselines, uncertainty, and OOD checks."""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .common import BatteryIntelligenceConfig
from .forecast_baselines import build_baseline_predictions


def _metric_dict(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    absolute = np.abs(actual - predicted)
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "median_absolute_error": float(np.median(absolute)),
        "rmse": float(math.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)) if len(actual) >= 2 else math.nan,
        "p90_absolute_error": float(np.quantile(absolute, 0.90)),
        "p95_absolute_error": float(np.quantile(absolute, 0.95)),
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
        inner_train_raw = x.iloc[train_index]
        eligible = [
            column for column in x.columns if inner_train_raw[column].notna().any()
        ]
        if not eligible:
            continue
        inner_train = inner_train_raw[eligible]
        inner_test = x.iloc[test_index][eligible]
        model = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("ridge", Ridge(alpha=alpha)),
            ]
        )
        model.fit(inner_train, y[train_index])
        prediction = model.predict(inner_test)
        residuals.extend(np.abs(y[test_index] - prediction).tolist())
    return np.asarray(residuals, dtype=float)


def _finite_sample_conformal_quantile(residuals: np.ndarray, coverage: float) -> float:
    if len(residuals) == 0:
        return math.nan
    rank = math.ceil((len(residuals) + 1) * coverage) / len(residuals)
    return float(np.quantile(residuals, min(rank, 1.0), method="higher"))


def _ood_diagnostics(
    train: pd.DataFrame, test: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray]:
    train_min = train.min(axis=0).to_numpy(dtype=float)
    train_max = train.max(axis=0).to_numpy(dtype=float)
    train_iqr = (
        train.quantile(0.75, axis=0) - train.quantile(0.25, axis=0)
    ).to_numpy(dtype=float)
    train_std = train.std(axis=0, ddof=0).to_numpy(dtype=float)
    scale = np.where(train_iqr > 0, train_iqr, np.where(train_std > 0, train_std, 1.0))
    values = test.to_numpy(dtype=float)
    below = values < train_min
    above = values > train_max
    outside = below | above
    outside_count = np.sum(outside, axis=1)
    distance = np.maximum(train_min - values, values - train_max)
    distance = np.maximum(distance, 0.0) / scale
    max_distance = np.max(np.where(outside, distance, 0.0), axis=1)
    max_distance[outside_count == 0] = 0.0
    return outside_count.astype(int), max_distance.astype(float)


def _improvement_percent(reference_mae: float, candidate_mae: float) -> float:
    return float(
        100.0
        * (reference_mae - candidate_mae)
        / max(reference_mae, np.finfo(float).eps)
    )


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
    baseline_predictions, baseline_metadata = build_baseline_predictions(
        forecast_table, horizon=config.horizon, lags=config.lags
    )
    baseline_names = [
        column.removesuffix("_prediction") for column in baseline_predictions.columns
    ]

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
        train_x_raw = x.iloc[train_index]
        test_x_raw = x.iloc[test_index]
        eligible_features = [
            column for column in feature_columns if train_x_raw[column].notna().any()
        ]
        if not eligible_features:
            raise ValueError(f"fold {fold} has no train-eligible forecast features")
        train_x = train_x_raw[eligible_features]
        test_x = test_x_raw[eligible_features]
        model = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("ridge", Ridge(alpha=config.ridge_alpha)),
            ]
        )
        model.fit(train_x, y[train_index])
        ridge_prediction = model.predict(test_x)
        calibration_residuals = _group_oof_residuals(
            train_x.reset_index(drop=True),
            y[train_index],
            groups[train_index],
            alpha=config.ridge_alpha,
            max_splits=max(2, split_count - 1),
        )
        interval_half_width = _finite_sample_conformal_quantile(
            calibration_residuals, config.conformal_coverage
        )
        train_medians = train_x.median(axis=0, skipna=True)
        ood_train = train_x.fillna(train_medians)
        ood_test = test_x.fillna(train_medians)
        outside_count, max_distance = _ood_diagnostics(ood_train, ood_test)

        actual = y[test_index]
        fold_model_metrics: dict[str, dict[str, float]] = {}
        for name in baseline_names:
            values = baseline_predictions.iloc[test_index][
                f"{name}_prediction"
            ].to_numpy(dtype=float)
            fold_model_metrics[name] = _metric_dict(actual, values)
        fold_model_metrics["ridge"] = _metric_dict(actual, ridge_prediction)
        persistence_mae = fold_model_metrics["persistence"]["mae"]
        ridge_mae = fold_model_metrics["ridge"]["mae"]
        fold_rows.append(
            {
                "fold": fold,
                "train_battery_count": len(train_groups),
                "test_battery_count": len(test_groups),
                "train_test_group_overlap_count": len(overlap),
                "calibration_residual_count": int(len(calibration_residuals)),
                "conformal_half_width": interval_half_width,
                "persistence_mae": persistence_mae,
                "ridge_mae": ridge_mae,
                "ridge_improvement_percent": _improvement_percent(
                    persistence_mae, ridge_mae
                ),
                "model_metrics": fold_model_metrics,
                "eligible_feature_count": len(eligible_features),
                "eligible_feature_columns": list(eligible_features),
                "train_only_feature_eligibility": True,
            }
        )

        fold_baselines = baseline_predictions.iloc[test_index].reset_index(drop=True)
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
            row: dict[str, Any] = {
                "fold": fold,
                config.group_column: source[config.group_column],
                "origin_cycle": source["origin_cycle"],
                "target_cycle": source["target_cycle"],
                "actual": actual[local_position],
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
                "missing_origin_feature_count": int(
                    test_x_raw.iloc[local_position].isna().sum()
                ),
                "prediction_outside_plausibility_range": bool(
                    ridge_prediction[local_position] < config.plausibility_min
                    or ridge_prediction[local_position] > config.plausibility_max
                ),
            }
            for column in fold_baselines.columns:
                row[column] = float(fold_baselines.iloc[local_position][column])
            prediction_rows.append(row)

    predictions = pd.DataFrame(prediction_rows)
    fold_metrics = pd.DataFrame(fold_rows)
    actual = predictions["actual"].to_numpy(dtype=float)
    model_names = [*baseline_names, "ridge"]
    model_metrics: dict[str, dict[str, float]] = {}
    for name in model_names:
        model_metrics[name] = _metric_dict(
            actual, predictions[f"{name}_prediction"].to_numpy(dtype=float)
        )
    ranking = sorted(model_names, key=lambda name: (model_metrics[name]["mae"], name))
    best_baseline_name = min(
        baseline_names, key=lambda name: (model_metrics[name]["mae"], name)
    )

    per_group_rows: list[dict[str, Any]] = []
    for battery_id, group in predictions.groupby(config.group_column, sort=True):
        actual_group = group["actual"].to_numpy(dtype=float)
        group_metrics = {
            name: _metric_dict(
                actual_group, group[f"{name}_prediction"].to_numpy(dtype=float)
            )
            for name in model_names
        }
        group_best_baseline = min(
            baseline_names, key=lambda name: (group_metrics[name]["mae"], name)
        )
        persistence_mae = group_metrics["persistence"]["mae"]
        ridge_mae = group_metrics["ridge"]["mae"]
        row = {
            config.group_column: battery_id,
            "prediction_count": int(len(group)),
            "persistence_mae": persistence_mae,
            "ridge_mae": ridge_mae,
            "ridge_improved": bool(ridge_mae < persistence_mae),
            "ridge_improvement_percent": _improvement_percent(
                persistence_mae, ridge_mae
            ),
            "best_baseline_name": group_best_baseline,
            "best_baseline_mae": group_metrics[group_best_baseline]["mae"],
            "ridge_improved_vs_best_baseline": bool(
                ridge_mae < group_metrics[group_best_baseline]["mae"]
            ),
            "ood_prediction_fraction": float(
                np.mean(group["outside_training_range_feature_count"] > 0)
            ),
        }
        for name in model_names:
            row[f"{name}_mae"] = group_metrics[name]["mae"]
        per_group_rows.append(row)
    per_group = pd.DataFrame(per_group_rows)

    decision_metrics: dict[str, dict[str, float]] = {}
    for name in model_names:
        battery_macro_mae = float(per_group[f"{name}_mae"].mean())
        fold_balanced_mae = float(
            np.mean([row["model_metrics"][name]["mae"] for row in fold_rows])
        )
        decision_metrics[name] = {
            "battery_macro_mae": battery_macro_mae,
            "fold_balanced_mae": fold_balanced_mae,
            "pooled_row_mae": model_metrics[name]["mae"],
        }
    primary_ranking = sorted(
        model_names,
        key=lambda name: (decision_metrics[name]["battery_macro_mae"], name),
    )
    primary_best_baseline_name = min(
        baseline_names,
        key=lambda name: (decision_metrics[name]["battery_macro_mae"], name),
    )

    interval_available = predictions["interval_contains_actual"].notna()
    coverage = (
        float(
            predictions.loc[
                interval_available, "interval_contains_actual"
            ].astype(bool).mean()
        )
        if interval_available.any()
        else math.nan
    )
    improved_group_count = int(per_group["ridge_improved"].sum())
    improved_best_count = int(per_group["ridge_improved_vs_best_baseline"].sum())
    persistence_metrics = model_metrics["persistence"]
    ridge_metrics = model_metrics["ridge"]
    best_baseline_name = primary_best_baseline_name
    best_baseline_metrics = model_metrics[best_baseline_name]
    summary = {
        "split_method": "group_kfold",
        "split_count": int(split_count),
        "train_test_group_overlap_count": int(leakage_violations),
        "prediction_count": int(len(predictions)),
        "evaluated_battery_count": int(len(per_group)),
        "feature_columns": list(feature_columns),
        "baseline_metadata": baseline_metadata,
        "model_metrics": model_metrics,
        "model_ranking_by_mae": ranking,
        "model_ranking_by_battery_macro_mae": primary_ranking,
        "primary_decision_metric": "battery_macro_mae",
        "primary_decision_rule": "lowest battery-macro MAE; pooled row MAE is secondary",
        "decision_metrics": decision_metrics,
        "best_model_name": primary_ranking[0],
        "best_baseline_name": best_baseline_name,
        "best_baseline_metrics": best_baseline_metrics,
        "persistence_metrics": persistence_metrics,
        "ridge_metrics": ridge_metrics,
        "ridge_improvement_percent": _improvement_percent(
            persistence_metrics["mae"], ridge_metrics["mae"]
        ),
        "ridge_improvement_percent_vs_best_baseline": _improvement_percent(
            best_baseline_metrics["mae"], ridge_metrics["mae"]
        ),
        "ridge_battery_macro_improvement_percent_vs_best_baseline": _improvement_percent(
            decision_metrics[best_baseline_name]["battery_macro_mae"],
            decision_metrics["ridge"]["battery_macro_mae"],
        ),
        "improved_battery_count": improved_group_count,
        "not_improved_battery_count": int(len(per_group) - improved_group_count),
        "improved_vs_best_baseline_battery_count": improved_best_count,
        "not_improved_vs_best_baseline_battery_count": int(
            len(per_group) - improved_best_count
        ),
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
