"""Leakage-safe exact-horizon forecast table construction."""
from __future__ import annotations

import math
from pathlib import PurePosixPath
from typing import Any

import numpy as np
import pandas as pd

from .common import BatteryIntelligenceConfig
from .degradation import _rolling_slope


def source_cohort_id_from_location(value: Any) -> str | None:
    """Return a stable archive-level cohort identifier from source lineage.

    NASA PCoE source locations use ``!`` between nested ZIP members. The
    innermost ZIP archive is the experimental source cohort; the MAT filename is
    intentionally excluded. Directory/MAT inputs fall back to their first
    lineage component and remain diagnostic rather than being silently merged.
    """
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace("\\", "/")
    if not text:
        return None
    components = [part.strip() for part in text.split("!") if part.strip()]
    archive_components = [
        PurePosixPath(part).name for part in components if part.lower().endswith(".zip")
    ]
    if archive_components:
        return archive_components[-1]
    if len(components) >= 2:
        return PurePosixPath(components[-2]).name
    path = PurePosixPath(components[0])
    return path.parent.name or path.name


def build_forecast_table(
    cycle_summary: pd.DataFrame,
    config: BatteryIntelligenceConfig,
    signal_features: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    config.validate()
    base = cycle_summary.copy()
    if "source_cohort_id" not in base.columns and "source_mat_file" in base.columns:
        base["source_cohort_id"] = base["source_mat_file"].map(
            source_cohort_id_from_location
        )
    if signal_features is not None and not signal_features.empty:
        base = base.merge(
            signal_features,
            left_on=[config.group_column, config.cycle_column],
            right_on=["battery_id", "cycle_index"],
            how="left",
            validate="one_to_one",
            suffixes=("", "_signal"),
        )
        for duplicate in ("battery_id_signal", "cycle_index_signal"):
            if duplicate in base.columns:
                base = base.drop(columns=duplicate)

    records: list[dict[str, Any]] = []
    feature_columns: set[str] = set()
    exclusion_counts = {
        "insufficient_history": 0,
        "missing_exact_horizon_target": 0,
        "non_finite_feature": 0,
    }
    excluded_identifiers = {
        config.group_column,
        config.cycle_column,
        config.target_column,
        "failed",
        "source_filename",
        "uid",
        "test_id",
        "reference_capacity_ah",
        "rated_capacity_ah",
        "reference_capacity_method",
        "retention_quality_flag",
        "source_cohort_id",
    }

    numeric_candidates = [
        column
        for column in base.columns
        if column not in excluded_identifiers
        and not column.startswith("source_")
        and pd.api.types.is_numeric_dtype(base[column])
    ]

    for battery_id, group in base.groupby(config.group_column, sort=True):
        ordered = group.sort_values(config.cycle_column, kind="mergesort").copy()
        cycle_to_row = {
            float(row[config.cycle_column]): row for _, row in ordered.iterrows()
        }
        target_values = ordered[config.target_column].to_numpy(dtype=float)
        for position, (_, row) in enumerate(ordered.iterrows()):
            if position < max(max(config.lags), config.rolling_window - 1):
                exclusion_counts["insufficient_history"] += 1
                continue
            origin_cycle = float(row[config.cycle_column])
            target_cycle = origin_cycle + config.horizon
            future = cycle_to_row.get(target_cycle)
            if future is None:
                exclusion_counts["missing_exact_horizon_target"] += 1
                continue

            origin_target = float(row[config.target_column])
            record: dict[str, Any] = {
                config.group_column: battery_id,
                "origin_cycle": origin_cycle,
                "target_cycle": target_cycle,
                "origin_target_value": origin_target,
                # Backward-compatible artifact alias. It means the configured
                # target value at the forecast origin, never electrical current,
                # and is excluded from fitted features to avoid duplication.
                "current_target": origin_target,
                "future_target": float(future[config.target_column]),
            }
            cohort_id = row.get("source_cohort_id")
            if cohort_id is not None and not pd.isna(cohort_id):
                record["source_cohort_id"] = str(cohort_id)
            history = target_values[: position + 1]
            for lag in config.lags:
                record[f"target_lag_{lag}"] = float(target_values[position - lag])
            trailing = history[-config.rolling_window :]
            record["target_rolling_mean"] = float(np.mean(trailing))
            record["target_rolling_std"] = float(np.std(trailing, ddof=0))
            record["target_rolling_slope"] = float(_rolling_slope(trailing))
            record["origin_cycle_feature"] = origin_cycle

            for column in numeric_candidates:
                value = row[column]
                if pd.notna(value) and math.isfinite(float(value)):
                    record[column] = float(value)

            candidate_features = [
                column
                for column in record
                if column
                not in {
                    config.group_column,
                    "source_cohort_id",
                    "origin_cycle",
                    "target_cycle",
                    "current_target",
                    "future_target",
                }
            ]
            if any(
                not math.isfinite(float(record[column]))
                for column in candidate_features
            ):
                exclusion_counts["non_finite_feature"] += 1
                continue
            feature_columns.update(candidate_features)
            records.append(record)

    table = pd.DataFrame(records)
    ordered_features = sorted(feature_columns)
    if table.empty:
        raise ValueError("no leakage-safe exact-horizon forecast rows were available")
    sparse_feature_columns = [
        column for column in ordered_features if table[column].isna().any()
    ]
    if not ordered_features:
        raise ValueError("no finite numeric forecast features were available")
    cohort_count = (
        int(table["source_cohort_id"].nunique())
        if "source_cohort_id" in table.columns
        else 0
    )
    metadata = {
        "forecast_row_count": int(len(table)),
        "battery_count": int(table[config.group_column].nunique()),
        "feature_count": int(len(ordered_features)),
        "feature_columns": ordered_features,
        "dropped_sparse_feature_columns": [],
        "sparse_feature_columns_retained_for_fold_local_handling": sparse_feature_columns,
        "feature_missingness_policy": "train_fold_eligibility_and_median_imputation",
        "source_cohort_column": (
            "source_cohort_id" if "source_cohort_id" in table.columns else None
        ),
        "source_cohort_count": cohort_count,
        "source_cohort_derivation": (
            "innermost nested ZIP archive from source_mat_file lineage"
            if cohort_count
            else None
        ),
        "exclusion_counts": exclusion_counts,
        "exact_horizon_only": True,
        "origin_target_field": "origin_target_value",
        "origin_target_source_column": config.target_column,
        "legacy_current_target_alias_retained": True,
        "legacy_current_target_alias_is_electrical_current": False,
    }
    return table, ordered_features, metadata
