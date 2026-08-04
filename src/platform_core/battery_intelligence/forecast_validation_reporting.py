"""Aggregation and calibration reporting for grouped battery forecasts."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .common import BatteryIntelligenceConfig
from .forecast_validation_support import (
    coverage_summary,
    improvement_percent,
    metric_dict,
)


def finalize_grouped_validation(
    *,
    predictions: pd.DataFrame,
    fold_rows: list[dict[str, Any]],
    feature_columns: list[str],
    baseline_names: list[str],
    baseline_metadata: dict[str, Any],
    config: BatteryIntelligenceConfig,
    split_column: str,
    split_method: str,
    split_count: int,
    leakage_violations: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    actual = predictions["actual"].to_numpy(dtype=float)
    model_names = [*baseline_names, "ridge"]
    model_metrics = {
        name: metric_dict(
            actual, predictions[f"{name}_prediction"].to_numpy(dtype=float)
        )
        for name in model_names
    }
    ranking = sorted(model_names, key=lambda name: (model_metrics[name]["mae"], name))

    rows: list[dict[str, Any]] = []
    for battery_id, group in predictions.groupby(config.group_column, sort=True):
        actual_group = group["actual"].to_numpy(dtype=float)
        metrics = {
            name: metric_dict(
                actual_group, group[f"{name}_prediction"].to_numpy(dtype=float)
            )
            for name in model_names
        }
        best_baseline = min(
            baseline_names, key=lambda name: (metrics[name]["mae"], name)
        )
        interval_count, coverage, width = coverage_summary(group)
        row: dict[str, Any] = {
            config.group_column: battery_id,
            "prediction_count": int(len(group)),
            "persistence_mae": metrics["persistence"]["mae"],
            "ridge_mae": metrics["ridge"]["mae"],
            "ridge_improved": bool(metrics["ridge"]["mae"] < metrics["persistence"]["mae"]),
            "ridge_improvement_percent": improvement_percent(
                metrics["persistence"]["mae"], metrics["ridge"]["mae"]
            ),
            "best_baseline_name": best_baseline,
            "best_baseline_mae": metrics[best_baseline]["mae"],
            "ridge_improved_vs_best_baseline": bool(
                metrics["ridge"]["mae"] < metrics[best_baseline]["mae"]
            ),
            "ood_prediction_fraction": float(
                np.mean(group["outside_training_range_feature_count"] > 0)
            ),
            "interval_prediction_count": interval_count,
            "conformal_observed_coverage": coverage,
            "mean_prediction_interval_width": width,
        }
        if "source_cohort_id" in group.columns:
            cohorts = sorted(group["source_cohort_id"].dropna().astype(str).unique())
            row["source_cohort_id"] = cohorts[0] if len(cohorts) == 1 else ";".join(cohorts)
        for name in model_names:
            row[f"{name}_mae"] = metrics[name]["mae"]
        rows.append(row)
    per_group = pd.DataFrame(rows)

    decision_metrics = {
        name: {
            "battery_macro_mae": float(per_group[f"{name}_mae"].mean()),
            "fold_balanced_mae": float(
                np.mean([row["model_metrics"][name]["mae"] for row in fold_rows])
            ),
            "pooled_row_mae": model_metrics[name]["mae"],
        }
        for name in model_names
    }
    primary_ranking = sorted(
        model_names,
        key=lambda name: (decision_metrics[name]["battery_macro_mae"], name),
    )
    best_baseline = min(
        baseline_names,
        key=lambda name: (decision_metrics[name]["battery_macro_mae"], name),
    )
    interval_available = predictions["interval_contains_actual"].notna()
    pooled_coverage = (
        float(
            predictions.loc[
                interval_available, "interval_contains_actual"
            ].astype(bool).mean()
        )
        if interval_available.any()
        else math.nan
    )
    finite_battery = per_group.dropna(subset=["conformal_observed_coverage"])
    battery_macro_coverage = (
        float(finite_battery["conformal_observed_coverage"].mean())
        if not finite_battery.empty
        else math.nan
    )
    worst_battery_id: str | None = None
    worst_battery_coverage = math.nan
    if not finite_battery.empty:
        index = finite_battery["conformal_observed_coverage"].idxmin()
        worst_battery_id = str(finite_battery.loc[index, config.group_column])
        worst_battery_coverage = float(
            finite_battery.loc[index, "conformal_observed_coverage"]
        )

    cohort_rows: list[dict[str, Any]] = []
    if "source_cohort_id" in predictions.columns:
        for cohort_id, group in predictions.groupby("source_cohort_id", sort=True):
            count, coverage, width = coverage_summary(group)
            cohort_rows.append(
                {
                    "source_cohort_id": str(cohort_id),
                    "prediction_count": int(len(group)),
                    "battery_count": int(group[config.group_column].nunique()),
                    "ridge_mae": metric_dict(
                        group["actual"].to_numpy(dtype=float),
                        group["ridge_prediction"].to_numpy(dtype=float),
                    )["mae"],
                    "interval_prediction_count": count,
                    "conformal_observed_coverage": coverage,
                    "mean_prediction_interval_width": width,
                }
            )
    cohort_metrics = pd.DataFrame(cohort_rows)
    fold_coverages = [
        float(row["conformal_observed_coverage"])
        for row in fold_rows
        if math.isfinite(float(row["conformal_observed_coverage"]))
    ]
    persistence = model_metrics["persistence"]
    ridge = model_metrics["ridge"]
    best_metrics = model_metrics[best_baseline]
    summary: dict[str, Any] = {
        "split_method": split_method,
        "split_group_column": split_column,
        "split_count": int(split_count),
        "train_test_group_overlap_count": int(leakage_violations),
        "battery_disjoint": split_column == config.group_column and leakage_violations == 0,
        "source_cohort_disjoint": split_column == "source_cohort_id" and leakage_violations == 0,
        "prediction_count": int(len(predictions)),
        "evaluated_battery_count": int(len(per_group)),
        "feature_columns": feature_columns,
        "feature_selection_policy": (
            "training-fold-only removal of all-missing, constant, and exact-duplicate columns; median imputation with indicators"
        ),
        "baseline_metadata": baseline_metadata,
        "model_metrics": model_metrics,
        "model_ranking_by_mae": ranking,
        "model_ranking_by_battery_macro_mae": primary_ranking,
        "primary_decision_metric": "battery_macro_mae",
        "primary_decision_rule": "lowest battery-macro MAE; pooled row MAE is secondary",
        "decision_metrics": decision_metrics,
        "best_model_name": primary_ranking[0],
        "best_baseline_name": best_baseline,
        "best_baseline_metrics": best_metrics,
        "persistence_metrics": persistence,
        "ridge_metrics": ridge,
        "ridge_improvement_percent": improvement_percent(persistence["mae"], ridge["mae"]),
        "ridge_improvement_percent_vs_best_baseline": improvement_percent(
            best_metrics["mae"], ridge["mae"]
        ),
        "ridge_battery_macro_improvement_percent_vs_best_baseline": improvement_percent(
            decision_metrics[best_baseline]["battery_macro_mae"],
            decision_metrics["ridge"]["battery_macro_mae"],
        ),
        "improved_battery_count": int(per_group["ridge_improved"].sum()),
        "not_improved_battery_count": int((~per_group["ridge_improved"]).sum()),
        "improved_vs_best_baseline_battery_count": int(
            per_group["ridge_improved_vs_best_baseline"].sum()
        ),
        "not_improved_vs_best_baseline_battery_count": int(
            (~per_group["ridge_improved_vs_best_baseline"]).sum()
        ),
        "conformal_target_coverage": config.conformal_coverage,
        "conformal_observed_coverage": pooled_coverage,
        "conformal_battery_macro_coverage": battery_macro_coverage,
        "conformal_worst_battery_id": worst_battery_id,
        "conformal_worst_battery_coverage": worst_battery_coverage,
        "conformal_fold_mean_coverage": float(np.mean(fold_coverages)) if fold_coverages else math.nan,
        "conformal_fold_min_coverage": float(np.min(fold_coverages)) if fold_coverages else math.nan,
        "interval_prediction_count": int(interval_available.sum()),
        "ood_prediction_fraction": float(
            np.mean(predictions["outside_training_range_feature_count"] > 0)
        ),
        "implausible_prediction_count": int(
            predictions["prediction_outside_plausibility_range"].sum()
        ),
        "source_cohort_count": int(len(cohort_metrics)),
        "external_cohort_validation_status": "not_performed",
        "external_cohort_validation_boundary": (
            "Source-cohort-disjoint internal validation does not establish external-dataset generalization."
        ),
    }
    if not cohort_metrics.empty:
        finite = cohort_metrics.dropna(subset=["conformal_observed_coverage"])
        summary["conformal_source_cohort_macro_coverage"] = (
            float(finite["conformal_observed_coverage"].mean())
            if not finite.empty
            else math.nan
        )
        if not finite.empty:
            index = finite["conformal_observed_coverage"].idxmin()
            summary["conformal_worst_source_cohort_id"] = str(
                finite.loc[index, "source_cohort_id"]
            )
            summary["conformal_worst_source_cohort_coverage"] = float(
                finite.loc[index, "conformal_observed_coverage"]
            )
    return per_group, {
        "summary": summary,
        "folds": fold_rows,
        "source_cohort_metrics": cohort_metrics.to_dict(orient="records"),
    }
