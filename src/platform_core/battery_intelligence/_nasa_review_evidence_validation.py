"""Validation contracts for NASA PCoE review evidence packets."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .common import canonical_json, file_sha256

_REQUIRED_QUEUE_COLUMNS = {
    "battery_id",
    "review_order",
    "review_tier",
    "review_tier_label",
    "review_dimensions",
    "is_evaluated",
    "prediction_count",
    "reference_start_context_flag",
    "reference_context_only",
    "source_quality_issue",
    "trajectory_continuity_issue",
    "evaluation_coverage_issue",
    "structural_or_coverage_issue",
    "disproportionate_error_influence",
    "context_reasons",
    "structural_review_reasons",
    "influence_review_reasons",
    "persistence_mae",
    "ridge_mae",
    "ridge_minus_persistence_mae",
    "excluded_discharge_operation_count",
    "invalid_capacity_operation_count",
    "cycle_gap_count",
    "maximum_absolute_adjacent_target_change_percent",
}
_REQUIRED_PREDICTION_COLUMNS = {
    "battery_id",
    "actual",
    "persistence_prediction",
    "ridge_prediction",
}
_REQUIRED_EXCLUSION_COLUMNS = {
    "source_location",
    "battery_id",
    "source_operation_index",
    "cycle_index",
    "capacity_issue",
    "observed_value",
    "severity",
    "code",
    "message",
}
_BOOLEAN_COLUMNS = {
    "is_evaluated",
    "reference_start_context_flag",
    "reference_context_only",
    "source_quality_issue",
    "trajectory_continuity_issue",
    "evaluation_coverage_issue",
    "structural_or_coverage_issue",
    "disproportionate_error_influence",
}
_INVENTORY_COUNT_FIELDS = (
    "imported_discharge_operation_count",
    "excluded_discharge_operation_count",
    "invalid_capacity_operation_count",
    "missing_capacity_operation_count",
    "nonnumeric_capacity_operation_count",
    "nonscalar_capacity_operation_count",
    "complex_capacity_operation_count",
    "nonfinite_capacity_operation_count",
    "nonpositive_capacity_operation_count",
)
_TRUE_TOKENS = {"true", "1", "yes"}
_FALSE_TOKENS = {"false", "0", "no"}
_DUPLICATE_SKIP_REASON = "duplicate_identical_source_copy"
_TOP_ERROR_ROWS = 3


def _require_columns(frame: pd.DataFrame, required: set[str], *, context: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{context} missing required columns: {', '.join(missing)}")


def _ids(frame: pd.DataFrame, *, context: str) -> pd.Series:
    _require_columns(frame, {"battery_id"}, context=context)
    if frame["battery_id"].isna().any():
        raise ValueError(f"{context} battery_id may not be missing")
    values = frame["battery_id"].astype(str).str.strip()
    if (values == "").any():
        raise ValueError(f"{context} battery_id may not be blank")
    return values


def _bools(series: pd.Series, *, context: str) -> pd.Series:
    if series.isna().any():
        raise ValueError(f"{context} contains missing boolean values")
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.casefold()
    invalid = ~normalized.isin(_TRUE_TOKENS | _FALSE_TOKENS)
    if invalid.any():
        values = sorted({repr(value) for value in series.loc[invalid].tolist()})
        raise ValueError(
            f"{context} contains invalid boolean values: {', '.join(values)}"
        )
    return normalized.isin(_TRUE_TOKENS)


def _integer_column(frame: pd.DataFrame, column: str, *, minimum: int = 0) -> None:
    values = pd.to_numeric(frame[column], errors="coerce")
    if values.isna().any() or (values < minimum).any():
        raise ValueError(f"{column} must contain integers >= {minimum}")
    if not np.isclose(values, np.round(values)).all():
        raise ValueError(f"{column} must contain integer values")
    frame[column] = values.astype(int)


def _finite_column(frame: pd.DataFrame, column: str, *, context: str) -> None:
    values = pd.to_numeric(frame[column], errors="coerce")
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError(f"{context}.{column} must contain finite numeric values")
    frame[column] = values.astype(float)


def _validated_queue(frame: pd.DataFrame) -> pd.DataFrame:
    context = "NASA protocol review queue"
    _require_columns(frame, _REQUIRED_QUEUE_COLUMNS, context=context)
    result = frame.copy()
    result["battery_id"] = _ids(result, context=context)
    if result["battery_id"].duplicated().any():
        raise ValueError("NASA protocol review queue battery_id values must be unique")
    for column in _BOOLEAN_COLUMNS:
        result[column] = _bools(result[column], context=f"{context}.{column}")
    for column in (
        "review_order",
        "review_tier",
        "prediction_count",
        "excluded_discharge_operation_count",
        "invalid_capacity_operation_count",
        "cycle_gap_count",
    ):
        _integer_column(result, column, minimum=0)
    if sorted(result["review_order"].tolist()) != list(range(1, len(result) + 1)):
        raise ValueError("review_order must be a complete one-based sequence")
    if (result["review_tier"] < 1).any():
        raise ValueError("review_tier must be positive")
    for column in (
        "persistence_mae",
        "ridge_mae",
        "ridge_minus_persistence_mae",
        "maximum_absolute_adjacent_target_change_percent",
    ):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    evaluated = result["is_evaluated"]
    model_columns = ["persistence_mae", "ridge_mae", "ridge_minus_persistence_mae"]
    if result.loc[evaluated, model_columns].isna().any().any():
        raise ValueError("evaluated batteries require finite model MAE values")
    if not np.isfinite(result.loc[evaluated, model_columns].to_numpy(dtype=float)).all():
        raise ValueError("evaluated battery MAE values must be finite")
    if (result["is_evaluated"] != (result["prediction_count"] > 0)).any():
        raise ValueError("evaluation status conflicts with prediction_count")
    if (
        result["excluded_discharge_operation_count"]
        != result["invalid_capacity_operation_count"]
    ).any():
        raise ValueError("excluded and invalid Capacity counts differ")
    return result.sort_values("review_order", kind="mergesort").reset_index(drop=True)


def _validated_predictions(frame: pd.DataFrame, known_ids: set[str]) -> pd.DataFrame:
    context = "NASA validation predictions"
    _require_columns(frame, _REQUIRED_PREDICTION_COLUMNS, context=context)
    result = frame.copy()
    result["battery_id"] = _ids(result, context=context)
    unknown = sorted(set(result["battery_id"]) - known_ids)
    if unknown:
        raise ValueError(f"validation predictions contain unknown batteries: {', '.join(unknown)}")
    for column in ("actual", "persistence_prediction", "ridge_prediction"):
        _finite_column(result, column, context=context)
    result["validation_row_number"] = np.arange(2, len(result) + 2)
    result["persistence_absolute_error"] = (
        result["actual"] - result["persistence_prediction"]
    ).abs()
    result["ridge_absolute_error"] = (
        result["actual"] - result["ridge_prediction"]
    ).abs()
    return result


def _validated_exclusions(frame: pd.DataFrame, known_ids: set[str]) -> pd.DataFrame:
    context = "NASA excluded operations"
    _require_columns(frame, _REQUIRED_EXCLUSION_COLUMNS, context=context)
    result = frame.copy()
    if result.empty:
        return result
    result["battery_id"] = _ids(result, context=context)
    unknown = sorted(set(result["battery_id"]) - known_ids)
    if unknown:
        raise ValueError(f"excluded operations contain unknown batteries: {', '.join(unknown)}")
    for column in ("source_operation_index", "cycle_index"):
        _integer_column(result, column, minimum=1)
    if (result["capacity_issue"].fillna("").astype(str).str.strip() == "").any():
        raise ValueError("excluded operation capacity_issue may not be blank")
    return result.sort_values(
        ["battery_id", "cycle_index", "source_operation_index"],
        kind="mergesort",
    ).reset_index(drop=True)

