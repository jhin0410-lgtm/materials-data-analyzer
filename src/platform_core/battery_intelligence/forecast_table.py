"""Leakage-safe exact-horizon forecast table construction."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .common import BatteryIntelligenceConfig
from .degradation import _rolling_slope


def build_forecast_table(
    cycle_summary: pd.DataFrame,
    config: BatteryIntelligenceConfig,
    signal_features: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    config.validate()
    base = cycle_summary.copy()
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
                "origin_target_percent": origin_target,
                # Backward-compatible artifact alias. It means the target value at
                # the forecast origin, never electrical current, and is excluded
                # from fitted feature columns to avoid duplicate predictors.
                "current_target": origin_target,
                "future_target": float(future[config.target_column]),
            }
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
    missing_feature_columns = [
        column for column in ordered_features if table[column].isna().any()
    ]
    if missing_feature_columns:
        table = table.drop(columns=missing_feature_columns)
        ordered_features = [
            column
            for column in ordered_features
            if column not in missing_feature_columns
        ]
    if not ordered_features:
        raise ValueError("no finite numeric forecast features were available")
    metadata = {
        "forecast_row_count": int(len(table)),
        "battery_count": int(table[config.group_column].nunique()),
        "feature_count": int(len(ordered_features)),
        "feature_columns": ordered_features,
        "dropped_sparse_feature_columns": missing_feature_columns,
        "exclusion_counts": exclusion_counts,
        "exact_horizon_only": True,
        "origin_target_field": "origin_target_percent",
        "legacy_current_target_alias_retained": True,
        "legacy_current_target_alias_is_electrical_current": False,
    }
    return table, ordered_features, metadata
