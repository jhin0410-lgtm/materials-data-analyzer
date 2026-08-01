"""Post-hoc battery forecast error-structure diagnostics.

These diagnostics explain where models succeed or fail. Lifecycle and knee-phase
labels may use full observed trajectories and are therefore diagnostic labels
only; they are never fed back into the forecast models.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .common import BatteryIntelligenceConfig


def _model_names(predictions: pd.DataFrame) -> list[str]:
    names = [
        column.removesuffix("_prediction")
        for column in predictions.columns
        if column.endswith("_prediction")
        and column not in {"prediction_interval_low", "prediction_interval_high"}
    ]
    return sorted(set(names), key=lambda name: (name == "ridge", name))


def _metric_row(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    absolute = np.abs(actual - predicted)
    squared = (actual - predicted) ** 2
    return {
        "mae": float(np.mean(absolute)),
        "median_absolute_error": float(np.median(absolute)),
        "rmse": float(math.sqrt(np.mean(squared))),
        "p90_absolute_error": float(np.quantile(absolute, 0.90)),
        "p95_absolute_error": float(np.quantile(absolute, 0.95)),
        "maximum_absolute_error": float(np.max(absolute)),
    }


def _aggregate_by(
    frame: pd.DataFrame,
    group_columns: Iterable[str],
    model_names: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_columns = list(group_columns)
    grouped: Any
    if len(group_columns) == 1:
        grouped = frame.groupby(group_columns[0], dropna=False, sort=True)
    else:
        grouped = frame.groupby(group_columns, dropna=False, sort=True)
    for keys, group in grouped:
        key_values = keys if isinstance(keys, tuple) else (keys,)
        prefix = dict(zip(group_columns, key_values))
        actual = group["actual"].to_numpy(dtype=float)
        for model in model_names:
            predicted = group[f"{model}_prediction"].to_numpy(dtype=float)
            rows.append(
                {
                    **prefix,
                    "model": model,
                    "prediction_count": int(len(group)),
                    **_metric_row(actual, predicted),
                }
            )
    return pd.DataFrame(rows)


def _lifecycle_segment(value: float) -> str:
    if not math.isfinite(value):
        return "unknown"
    if value <= 1.0 / 3.0:
        return "early"
    if value <= 2.0 / 3.0:
        return "middle"
    return "late"


def _degradation_rate_bin(value: float) -> str:
    if not math.isfinite(value):
        return "unknown"
    if value >= 0:
        return "recovery_or_flat"
    if value >= -0.1:
        return "mild_decline"
    if value >= -0.5:
        return "moderate_decline"
    return "severe_decline"


def _knee_phase(row: pd.Series, horizon: int) -> str:
    knee = row.get("knee_cycle")
    status = row.get("status")
    if status not in {"candidate", "weak_candidate"} or pd.isna(knee):
        return "no_supported_knee_label"
    origin = float(row["origin_cycle"])
    knee_value = float(knee)
    if origin < knee_value - horizon:
        return "pre_knee"
    if origin > knee_value + horizon:
        return "post_knee"
    return "near_knee"


def _profile_comparison(
    battery_profiles: pd.DataFrame,
    *,
    comparison_flag: str,
    reference_name: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    improved = battery_profiles[battery_profiles[comparison_flag]]
    not_improved = battery_profiles[~battery_profiles[comparison_flag]]
    excluded = {
        "ridge_mae",
        "persistence_mae",
        "ridge_improvement_percent",
        "best_baseline_mae",
    }
    for column in battery_profiles.select_dtypes(include=[np.number]).columns:
        if column in excluded or column.endswith("_mae"):
            continue
        improved_values = improved[column].dropna().to_numpy(dtype=float)
        failed_values = not_improved[column].dropna().to_numpy(dtype=float)
        if not len(improved_values) or not len(failed_values):
            continue
        improved_mean = float(np.mean(improved_values))
        failed_mean = float(np.mean(failed_values))
        rows.append(
            {
                "comparison_reference": reference_name,
                "metric": column,
                "ridge_improved_battery_count": int(len(improved_values)),
                "ridge_not_improved_battery_count": int(len(failed_values)),
                "ridge_improved_mean": improved_mean,
                "ridge_not_improved_mean": failed_mean,
                "mean_difference": improved_mean - failed_mean,
                "interpretation_boundary": "descriptive association only",
            }
        )
    return rows


def build_error_diagnostics(
    *,
    predictions: pd.DataFrame,
    forecast_table: pd.DataFrame,
    per_group: pd.DataFrame,
    trajectory_diagnostics: pd.DataFrame,
    validation: dict[str, Any],
    config: BatteryIntelligenceConfig,
) -> dict[str, Any]:
    model_names = _model_names(predictions)
    if "ridge" not in model_names or "persistence" not in model_names:
        raise ValueError("error diagnostics require ridge and persistence predictions")

    merge_keys = [config.group_column, "origin_cycle", "target_cycle"]
    forecast_columns = [
        column
        for column in (
            *merge_keys,
            "current_target",
            "target_rolling_slope",
            "target_rolling_std",
            "target_rolling_mean",
        )
        if column in forecast_table.columns
    ]
    enriched = predictions.merge(
        forecast_table[forecast_columns],
        on=merge_keys,
        how="left",
        validate="one_to_one",
    )
    trajectory_columns = [
        column
        for column in (
            config.group_column,
            "last_cycle",
            "overall_slope_percent_per_cycle",
            "status",
            "knee_cycle",
            "sensitivity_cycle_span",
            "trajectory_point_count",
        )
        if column in trajectory_diagnostics.columns
    ]
    enriched = enriched.merge(
        trajectory_diagnostics[trajectory_columns],
        on=config.group_column,
        how="left",
        validate="many_to_one",
    )

    for model in model_names:
        enriched[f"{model}_absolute_error"] = np.abs(
            enriched["actual"] - enriched[f"{model}_prediction"]
        )
    baseline_names = [name for name in model_names if name != "ridge"]
    baseline_error_columns = [f"{name}_absolute_error" for name in baseline_names]
    all_error_columns = [f"{name}_absolute_error" for name in model_names]
    enriched["row_oracle_baseline_name"] = (
        enriched[baseline_error_columns]
        .idxmin(axis=1)
        .str.removesuffix("_absolute_error")
    )
    enriched["row_oracle_baseline_absolute_error"] = enriched[
        baseline_error_columns
    ].min(axis=1)
    enriched["best_model_name"] = (
        enriched[all_error_columns].idxmin(axis=1).str.removesuffix("_absolute_error")
    )
    enriched["ridge_minus_persistence_absolute_error"] = (
        enriched["ridge_absolute_error"] - enriched["persistence_absolute_error"]
    )
    enriched["ridge_minus_row_oracle_baseline_absolute_error"] = (
        enriched["ridge_absolute_error"]
        - enriched["row_oracle_baseline_absolute_error"]
    )
    # Compatibility aliases retain the v1 output names while the summary makes
    # clear that this is an outcome-known row oracle, not a deployable baseline.
    enriched["best_baseline_name"] = enriched["row_oracle_baseline_name"]
    enriched["best_baseline_absolute_error"] = enriched[
        "row_oracle_baseline_absolute_error"
    ]
    enriched["ridge_minus_best_baseline_absolute_error"] = enriched[
        "ridge_minus_row_oracle_baseline_absolute_error"
    ]
    enriched["domain_status"] = np.where(
        enriched["outside_training_range_feature_count"] > 0,
        "out_of_domain",
        "in_domain",
    )
    enriched["interval_width"] = (
        enriched["prediction_interval_high"] - enriched["prediction_interval_low"]
    )
    enriched["degradation_delta"] = enriched["actual"] - enriched["current_target"]
    enriched["degradation_rate_percent_per_cycle"] = (
        enriched["degradation_delta"] / float(config.horizon)
    )
    enriched["degradation_rate_bin"] = enriched[
        "degradation_rate_percent_per_cycle"
    ].map(_degradation_rate_bin)
    enriched["lifecycle_fraction"] = enriched["origin_cycle"] / enriched["last_cycle"]
    enriched["lifecycle_segment"] = enriched["lifecycle_fraction"].map(_lifecycle_segment)
    enriched["knee_phase"] = enriched.apply(
        lambda row: _knee_phase(row, config.horizon), axis=1
    )
    enriched["trajectory_regime"] = enriched["status"].fillna("unknown")
    try:
        enriched["interval_width_bin"] = pd.qcut(
            enriched["interval_width"], q=4, duplicates="drop"
        ).astype(str)
    except ValueError:
        enriched["interval_width_bin"] = "single_width"

    global_rows: list[dict[str, Any]] = []
    actual = enriched["actual"].to_numpy(dtype=float)
    persistence_mae = float(enriched["persistence_absolute_error"].mean())
    for model in model_names:
        metrics = _metric_row(
            actual, enriched[f"{model}_prediction"].to_numpy(dtype=float)
        )
        metrics["improvement_percent_vs_persistence"] = float(
            100.0
            * (persistence_mae - metrics["mae"])
            / max(persistence_mae, np.finfo(float).eps)
        )
        metrics["row_win_fraction"] = float(
            np.mean(enriched["best_model_name"] == model)
        )
        global_rows.append({"model": model, **metrics})
    model_comparison = pd.DataFrame(global_rows).sort_values(
        ["mae", "model"], kind="mergesort"
    ).reset_index(drop=True)

    by_battery = _aggregate_by(enriched, [config.group_column], model_names)
    by_lifecycle = _aggregate_by(enriched, ["lifecycle_segment"], model_names)
    by_knee = _aggregate_by(enriched, ["knee_phase"], model_names)
    by_domain = _aggregate_by(enriched, ["domain_status"], model_names)
    by_degradation = _aggregate_by(enriched, ["degradation_rate_bin"], model_names)
    by_regime = _aggregate_by(enriched, ["trajectory_regime"], model_names)
    by_interval = _aggregate_by(enriched, ["interval_width_bin"], model_names)

    battery_profiles = per_group.merge(
        trajectory_diagnostics,
        on=config.group_column,
        how="left",
        validate="one_to_one",
        suffixes=("", "_trajectory"),
    )
    numeric_forecast = [
        column
        for column in forecast_table.columns
        if column not in {config.group_column, "future_target", "target_cycle"}
        and pd.api.types.is_numeric_dtype(forecast_table[column])
    ]
    if numeric_forecast:
        feature_profiles = (
            forecast_table.groupby(config.group_column, sort=True)[numeric_forecast]
            .mean()
            .add_prefix("mean_")
            .reset_index()
        )
        battery_profiles = battery_profiles.merge(
            feature_profiles,
            on=config.group_column,
            how="left",
            validate="one_to_one",
        )

    profile_rows = _profile_comparison(
        battery_profiles,
        comparison_flag="ridge_improved",
        reference_name="persistence",
    )
    profile_rows.extend(
        _profile_comparison(
            battery_profiles,
            comparison_flag="ridge_improved_vs_best_baseline",
            reference_name="battery_specific_best_baseline",
        )
    )
    success_failure_profiles = pd.DataFrame(profile_rows)

    high_error_count = min(
        len(enriched), max(20, int(math.ceil(0.05 * len(enriched))))
    )
    high_error_predictions = enriched.nlargest(
        high_error_count, "ridge_absolute_error"
    ).reset_index(drop=True)

    best_model = str(model_comparison.iloc[0]["model"])
    best_baseline_row = model_comparison[model_comparison["model"] != "ridge"].iloc[0]
    ridge_row = model_comparison[model_comparison["model"] == "ridge"].iloc[0]
    domain_ridge = by_domain[by_domain["model"] == "ridge"].set_index("domain_status")
    in_domain_mae = (
        float(domain_ridge.loc["in_domain", "mae"])
        if "in_domain" in domain_ridge.index
        else math.nan
    )
    ood_mae = (
        float(domain_ridge.loc["out_of_domain", "mae"])
        if "out_of_domain" in domain_ridge.index
        else math.nan
    )
    summary = {
        "schema_version": "1.0",
        "prediction_count": int(len(enriched)),
        "model_names": model_names,
        "best_model_by_mae": best_model,
        "best_baseline_by_mae": str(best_baseline_row["model"]),
        "best_baseline_mae": float(best_baseline_row["mae"]),
        "ridge_mae": float(ridge_row["mae"]),
        "ridge_improvement_percent_vs_best_baseline": float(
            100.0
            * (float(best_baseline_row["mae"]) - float(ridge_row["mae"]))
            / max(float(best_baseline_row["mae"]), np.finfo(float).eps)
        ),
        "ridge_row_win_fraction": float(ridge_row["row_win_fraction"]),
        "ridge_in_domain_mae": in_domain_mae,
        "ridge_out_of_domain_mae": ood_mae,
        "ridge_ood_minus_in_domain_mae": (
            ood_mae - in_domain_mae
            if math.isfinite(ood_mae) and math.isfinite(in_domain_mae)
            else None
        ),
        "high_error_prediction_count": int(len(high_error_predictions)),
        "row_oracle_boundary": (
            "The row-oracle baseline selects the lowest-error baseline after the "
            "outcome is known. It is an error-envelope diagnostic, not a deployable model."
        ),
        "diagnostic_label_boundary": (
            "Lifecycle and knee-phase labels may use the complete observed trajectory. "
            "They are post-hoc diagnostic strata and are not forecast inputs."
        ),
        "causal_interpretation_supported": False,
    }

    return {
        "row_level": enriched,
        "model_comparison": model_comparison,
        "by_battery": by_battery,
        "by_lifecycle_segment": by_lifecycle,
        "by_knee_phase": by_knee,
        "by_domain_status": by_domain,
        "by_degradation_rate": by_degradation,
        "by_trajectory_regime": by_regime,
        "by_interval_width": by_interval,
        "battery_profiles": battery_profiles,
        "success_failure_profiles": success_failure_profiles,
        "high_error_predictions": high_error_predictions,
        "summary": summary,
    }
