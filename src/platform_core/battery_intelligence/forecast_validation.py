"""Group-disjoint validation, baselines, uncertainty, and OOD checks."""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut

from .common import BatteryIntelligenceConfig
from .forecast_baselines import build_baseline_predictions
from .forecast_validation_reporting import finalize_grouped_validation
from .forecast_validation_support import (
    finite_sample_conformal_quantile,
    group_oof_residuals,
    improvement_percent,
    make_model,
    metric_dict,
    ood_diagnostics,
    pipeline_metadata,
    select_fold_features,
)


def evaluate_grouped_forecast(
    forecast_table: pd.DataFrame,
    feature_columns: Sequence[str],
    config: BatteryIntelligenceConfig,
    *,
    split_group_column: str | None = None,
    leave_one_group_out: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Evaluate with battery-disjoint or leave-one-source-cohort-out splits."""
    split_column = split_group_column or config.group_column
    if split_column not in forecast_table.columns:
        raise ValueError(f"split group column not found: {split_column}")
    if forecast_table[split_column].isna().any():
        raise ValueError(f"split group column contains missing values: {split_column}")

    split_groups = forecast_table[split_column].astype(str).to_numpy()
    battery_groups = forecast_table[config.group_column].astype(str).to_numpy()
    unique_groups = np.unique(split_groups)
    if len(unique_groups) < 2:
        raise ValueError("at least two split groups are required for grouped validation")
    if leave_one_group_out:
        splitter: Any = LeaveOneGroupOut()
        split_count = len(unique_groups)
        split_method = "leave_one_group_out"
    else:
        split_count = min(config.n_splits, len(unique_groups))
        splitter = GroupKFold(n_splits=split_count)
        split_method = "group_kfold"

    feature_list = list(feature_columns)
    x = forecast_table[feature_list].astype(float)
    y = forecast_table["future_target"].to_numpy(dtype=float)
    baselines, baseline_metadata = build_baseline_predictions(
        forecast_table, horizon=config.horizon, lags=config.lags
    )
    baseline_names = [
        column.removesuffix("_prediction") for column in baselines.columns
    ]
    prediction_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    leakage_violations = 0

    for fold, (train_index, test_index) in enumerate(
        splitter.split(x, y, split_groups), start=1
    ):
        train_groups = set(split_groups[train_index])
        test_groups = set(split_groups[test_index])
        overlap = sorted(train_groups & test_groups)
        leakage_violations += int(bool(overlap))
        train_raw = x.iloc[train_index]
        test_raw = x.iloc[test_index]
        eligible, dropped = select_fold_features(train_raw, feature_list)
        if not eligible:
            raise ValueError(f"fold {fold} has no train-eligible forecast features")
        train_x = train_raw[eligible]
        test_x = test_raw[eligible]
        model = make_model(config.ridge_alpha)
        model.fit(train_x, y[train_index])
        ridge_prediction = model.predict(test_x)
        calibration = group_oof_residuals(
            train_x.reset_index(drop=True),
            y[train_index],
            battery_groups[train_index],
            alpha=config.ridge_alpha,
            max_splits=max(
                2,
                min(
                    config.n_splits,
                    len(np.unique(battery_groups[train_index])),
                ),
            ),
        )
        half_width = finite_sample_conformal_quantile(
            calibration, config.conformal_coverage
        )
        medians = train_x.median(axis=0, skipna=True)
        outside_count, max_distance = ood_diagnostics(
            train_x.fillna(medians), test_x.fillna(medians)
        )
        actual = y[test_index]
        fold_metrics = {
            name: metric_dict(
                actual,
                baselines.iloc[test_index][f"{name}_prediction"].to_numpy(dtype=float),
            )
            for name in baseline_names
        }
        fold_metrics["ridge"] = metric_dict(actual, ridge_prediction)
        fold_coverage = math.nan
        if math.isfinite(half_width):
            fold_coverage = float(
                np.mean(
                    (actual >= ridge_prediction - half_width)
                    & (actual <= ridge_prediction + half_width)
                )
            )
        fold_rows.append(
            {
                "fold": fold,
                "split_group_column": split_column,
                "train_split_group_count": len(train_groups),
                "test_split_group_count": len(test_groups),
                "test_split_groups": sorted(test_groups),
                "train_battery_count": len(set(battery_groups[train_index])),
                "test_battery_count": len(set(battery_groups[test_index])),
                "train_test_group_overlap_count": len(overlap),
                "calibration_residual_count": int(len(calibration)),
                "conformal_half_width": half_width,
                "conformal_observed_coverage": fold_coverage,
                "persistence_mae": fold_metrics["persistence"]["mae"],
                "ridge_mae": fold_metrics["ridge"]["mae"],
                "ridge_improvement_percent": improvement_percent(
                    fold_metrics["persistence"]["mae"],
                    fold_metrics["ridge"]["mae"],
                ),
                "model_metrics": fold_metrics,
                "eligible_feature_count": len(eligible),
                "eligible_feature_columns": eligible,
                "dropped_feature_count": len(dropped),
                "dropped_feature_reasons": dropped,
                "train_only_feature_eligibility": True,
                "model_pipeline": pipeline_metadata(model, eligible),
            }
        )

        fold_baselines = baselines.iloc[test_index].reset_index(drop=True)
        for local_position, row_index in enumerate(test_index):
            source = forecast_table.iloc[row_index]
            lower = (
                ridge_prediction[local_position] - half_width
                if math.isfinite(half_width)
                else math.nan
            )
            upper = (
                ridge_prediction[local_position] + half_width
                if math.isfinite(half_width)
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
                    test_raw.iloc[local_position].isna().sum()
                ),
                "prediction_outside_plausibility_range": bool(
                    ridge_prediction[local_position] < config.plausibility_min
                    or ridge_prediction[local_position] > config.plausibility_max
                ),
            }
            if "source_cohort_id" in forecast_table.columns:
                row["source_cohort_id"] = source["source_cohort_id"]
            for column in fold_baselines.columns:
                row[column] = float(fold_baselines.iloc[local_position][column])
            prediction_rows.append(row)

    predictions = pd.DataFrame(prediction_rows)
    per_group, validation = finalize_grouped_validation(
        predictions=predictions,
        fold_rows=fold_rows,
        feature_columns=feature_list,
        baseline_names=baseline_names,
        baseline_metadata=baseline_metadata,
        config=config,
        split_column=split_column,
        split_method=split_method,
        split_count=split_count,
        leakage_violations=leakage_violations,
    )
    return predictions, per_group, validation
