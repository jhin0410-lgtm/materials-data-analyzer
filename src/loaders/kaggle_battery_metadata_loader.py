"""Kaggle NASA battery metadata loader.

This loader converts the cleaned Kaggle metadata.csv into a discharge-only
cycle-level summary for the existing tabular analyzer. It intentionally reads
metadata.csv only and does not merge the thousands of raw per-cycle CSV files.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd

from domain_constraints import DomainConstraint, validate_domain_constraints


KAGGLE_BATTERY_SUMMARY_COLUMNS = [
    "battery_id",
    "cycle_index",
    "ambient_temperature_c",
    "discharge_capacity_ah",
    "reference_capacity_ah",
    "reference_capacity_method",
    "capacity_retention_percent",
    "retention_quality_flag",
    "internal_resistance_ohm",
    "failed",
    "source_filename",
    "uid",
    "test_id",
]

KAGGLE_BATTERY_SUMMARY_CONSTRAINTS = [
    DomainConstraint(
        column="cycle_index",
        min_value=1,
        description="Cycle index should start at 1 within each battery.",
    ),
    DomainConstraint(
        column="discharge_capacity_ah",
        min_value=0,
        description="Discharge capacity should not be negative.",
    ),
    DomainConstraint(
        column="capacity_retention_percent",
        min_value=0,
        max_value=120,
        description=(
            "Capacity retention is expected to stay in a conservative "
            "0-120 percent screening range."
        ),
    ),
    DomainConstraint(
        column="reference_capacity_ah",
        min_value=0,
        description="Reference capacity should not be negative when present.",
    ),
    DomainConstraint(
        column="reference_capacity_method",
        allowed_values=["first_valid", "first_n_median", "max_observed"],
        description="Supported reference capacity calculation methods.",
    ),
    DomainConstraint(
        column="retention_quality_flag",
        allowed_values=[
            "normal",
            "invalid_capacity",
            "invalid_reference_capacity",
            "high_retention_warning",
            "invalid_retention",
        ],
        description="Quality flag for derived capacity retention values.",
    ),
    DomainConstraint(
        column="internal_resistance_ohm",
        min_value=0,
        description=(
            "Internal resistance is reserved for a future impedance join and "
            "should not be negative when present."
        ),
    ),
    DomainConstraint(
        column="failed",
        allowed_values=[0, 1],
        description=(
            "Derived label: 1 when capacity_retention_percent is below 80."
        ),
    ),
]

KAGGLE_BATTERY_QUALITY_SUMMARY_COLUMNS = [
    "battery_id",
    "row_count",
    "normal_count",
    "high_retention_warning_count",
    "invalid_capacity_count",
    "warning_rate",
    "min_retention",
    "max_retention",
    "reference_capacity_ah",
    "battery_quality_flag",
]


def load_kaggle_battery_metadata(metadata_path: str | Path) -> pd.DataFrame:
    """Load Kaggle cleaned_dataset metadata.csv."""
    path = Path(metadata_path)
    if not path.exists():
        raise FileNotFoundError(f"Kaggle battery metadata file was not found: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"Kaggle battery metadata path is not a file: {path}")

    try:
        metadata_df = pd.read_csv(path)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"Kaggle battery metadata CSV is empty: {path}") from exc

    if metadata_df.empty:
        raise ValueError(f"Kaggle battery metadata CSV has no data rows: {path}")

    return metadata_df


def _find_column_case_insensitive(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find the first matching column, preferring exact names then case-insensitive."""
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    lowered_to_original = {str(column).strip().lower(): column for column in df.columns}
    for candidate in candidates:
        match = lowered_to_original.get(candidate.strip().lower())
        if match is not None:
            return str(match)
    return None


def _parse_start_time(value: Any) -> pd.Timestamp | pd.NaT:
    """Parse Kaggle/NASA start_time strings into sortable timestamps when possible."""
    if pd.isna(value):
        return pd.NaT

    parsed = pd.to_datetime(value, errors="coerce")
    if not pd.isna(parsed):
        return parsed

    numbers = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", str(value))
    if len(numbers) < 6:
        return pd.NaT

    try:
        year, month, day, hour, minute = [int(float(number)) for number in numbers[:5]]
        second = float(numbers[5])
        base = pd.Timestamp(
            year=year,
            month=month,
            day=day,
            hour=hour,
            minute=minute,
            second=0,
        )
        return base + pd.to_timedelta(second, unit="s")
    except (ValueError, OverflowError):
        return pd.NaT


def _optional_column(df: pd.DataFrame, column: str, default: object = pd.NA) -> pd.Series:
    """Return an existing column or a default-valued Series."""
    if column in df.columns:
        return df[column]
    return pd.Series([default] * len(df), index=df.index)


def _calculate_reference_capacity(
    capacity: pd.Series,
    battery_ids: pd.Series,
    reference_capacity_method: str,
    reference_window: int,
) -> pd.Series:
    """Calculate per-row battery reference capacity from positive capacities."""
    valid_methods = {"first_valid", "first_n_median", "max_observed"}
    if reference_capacity_method not in valid_methods:
        raise ValueError(
            "Unsupported reference capacity method: "
            f"{reference_capacity_method}. Supported methods: {sorted(valid_methods)}"
        )
    if reference_window < 1:
        raise ValueError("reference_window must be 1 or greater.")

    def calculate_for_group(series: pd.Series) -> float:
        positive = series[(series.notna()) & (series > 0)]
        if positive.empty:
            return np.nan
        if reference_capacity_method == "first_valid":
            return float(positive.iloc[0])
        if reference_capacity_method == "first_n_median":
            return float(positive.head(reference_window).median())
        return float(positive.max())

    return capacity.groupby(battery_ids, sort=False).transform(calculate_for_group)


def _build_retention_quality_flags(
    capacity: pd.Series,
    reference_capacity: pd.Series,
    capacity_retention: pd.Series,
) -> pd.Series:
    """Return quality flags for derived capacity-retention values."""
    flags = pd.Series("normal", index=capacity.index, dtype="object")
    flags.loc[capacity.isna() | (capacity <= 0)] = "invalid_capacity"
    flags.loc[
        flags.eq("normal")
        & (reference_capacity.isna() | (reference_capacity <= 0))
    ] = "invalid_reference_capacity"
    flags.loc[
        flags.eq("normal")
        & capacity_retention.notna()
        & (capacity_retention > 120)
    ] = "high_retention_warning"
    flags.loc[
        flags.eq("normal")
        & capacity_retention.notna()
        & (capacity_retention < 0)
    ] = "invalid_retention"
    return flags


def build_discharge_cycle_summary(
    metadata_df: pd.DataFrame,
    reference_capacity_method: str = "first_n_median",
    reference_window: int = 5,
) -> pd.DataFrame:
    """Build a discharge-only cycle summary from Kaggle battery metadata."""
    type_column = _find_column_case_insensitive(metadata_df, ["type"])
    battery_column = _find_column_case_insensitive(metadata_df, ["battery_id"])
    capacity_column = _find_column_case_insensitive(metadata_df, ["Capacity", "capacity"])

    missing_required = [
        name
        for name, column in {
            "type": type_column,
            "battery_id": battery_column,
            "Capacity/capacity": capacity_column,
        }.items()
        if column is None
    ]
    if missing_required:
        raise ValueError(
            "Kaggle battery metadata is missing required column(s): "
            f"{missing_required}"
        )

    discharge_mask = (
        metadata_df[type_column].astype("string").str.strip().str.lower()
        == "discharge"
    )
    discharge_df = metadata_df.loc[discharge_mask].copy()
    if discharge_df.empty:
        raise ValueError("No discharge rows were found in Kaggle battery metadata.")

    sort_columns = [battery_column]
    if "start_time" in discharge_df.columns:
        discharge_df["_sort_start_time"] = discharge_df["start_time"].apply(
            _parse_start_time
        )
        sort_columns.append("_sort_start_time")
    for column in ("test_id", "uid"):
        if column in discharge_df.columns:
            sort_columns.append(column)

    discharge_df = discharge_df.sort_values(
        by=sort_columns,
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
    discharge_df["cycle_index"] = (
        discharge_df.groupby(battery_column, sort=False).cumcount() + 1
    )

    capacity = pd.to_numeric(discharge_df[capacity_column], errors="coerce")
    reference_capacity = _calculate_reference_capacity(
        capacity=capacity,
        battery_ids=discharge_df[battery_column],
        reference_capacity_method=reference_capacity_method,
        reference_window=reference_window,
    )
    capacity_retention = np.where(
        (reference_capacity.notna())
        & (reference_capacity > 0)
        & (capacity.notna()),
        capacity / reference_capacity * 100,
        np.nan,
    )
    capacity_retention_series = pd.Series(
        capacity_retention,
        index=discharge_df.index,
        dtype="float64",
    )
    quality_flags = _build_retention_quality_flags(
        capacity=capacity,
        reference_capacity=reference_capacity,
        capacity_retention=capacity_retention_series,
    )

    summary_df = pd.DataFrame(
        {
            "battery_id": discharge_df[battery_column].astype("string"),
            "cycle_index": discharge_df["cycle_index"].astype(int),
            "ambient_temperature_c": pd.to_numeric(
                _optional_column(discharge_df, "ambient_temperature"),
                errors="coerce",
            ),
            "discharge_capacity_ah": capacity,
            "reference_capacity_ah": reference_capacity,
            "reference_capacity_method": reference_capacity_method,
            "capacity_retention_percent": capacity_retention_series,
            "retention_quality_flag": quality_flags,
            "internal_resistance_ohm": np.nan,
            "failed": (capacity_retention_series < 80).fillna(False).astype(int),
            "source_filename": _optional_column(discharge_df, "filename"),
            "uid": _optional_column(discharge_df, "uid"),
            "test_id": _optional_column(discharge_df, "test_id"),
        },
        columns=KAGGLE_BATTERY_SUMMARY_COLUMNS,
    )

    validate_kaggle_battery_summary_schema(summary_df)
    return summary_df


def save_kaggle_battery_summary(
    summary_df: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Validate and save the Kaggle battery cycle summary CSV."""
    validate_kaggle_battery_summary_schema(summary_df)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(output, index=False)
    return output


def _require_columns(df: pd.DataFrame, columns: list[str], table_name: str) -> None:
    """Raise a clear error when a table is missing required columns."""
    missing_columns = [column for column in columns if column not in df.columns]
    if missing_columns:
        raise ValueError(
            f"{table_name} is missing required columns: {missing_columns}"
        )


def build_battery_quality_summary(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Build a battery-level quality summary from the full cycle summary."""
    _require_columns(
        summary_df,
        [
            "battery_id",
            "capacity_retention_percent",
            "reference_capacity_ah",
            "retention_quality_flag",
        ],
        "Kaggle battery cycle summary",
    )

    rows: list[dict[str, object]] = []
    for battery_id, group in summary_df.groupby("battery_id", sort=True):
        row_count = int(len(group))
        quality_flags = group["retention_quality_flag"].astype("string")
        normal_count = int((quality_flags == "normal").sum())
        high_warning_count = int((quality_flags == "high_retention_warning").sum())
        invalid_capacity_count = int((quality_flags == "invalid_capacity").sum())
        warning_rate = high_warning_count / row_count if row_count else 0.0
        retention = pd.to_numeric(
            group["capacity_retention_percent"],
            errors="coerce",
        )
        reference_values = pd.to_numeric(
            group["reference_capacity_ah"],
            errors="coerce",
        ).dropna()
        reference_capacity = (
            float(reference_values.iloc[0]) if not reference_values.empty else np.nan
        )

        if warning_rate > 0.3:
            battery_quality_flag = "high_warning_battery"
        elif invalid_capacity_count > 0:
            battery_quality_flag = "has_invalid_capacity"
        elif row_count < 5:
            battery_quality_flag = "too_few_rows"
        else:
            battery_quality_flag = "analysis_candidate"

        rows.append(
            {
                "battery_id": battery_id,
                "row_count": row_count,
                "normal_count": normal_count,
                "high_retention_warning_count": high_warning_count,
                "invalid_capacity_count": invalid_capacity_count,
                "warning_rate": warning_rate,
                "min_retention": retention.min(skipna=True),
                "max_retention": retention.max(skipna=True),
                "reference_capacity_ah": reference_capacity,
                "battery_quality_flag": battery_quality_flag,
            }
        )

    return pd.DataFrame(rows, columns=KAGGLE_BATTERY_QUALITY_SUMMARY_COLUMNS)


def build_analysis_ready_summary(
    summary_df: pd.DataFrame,
    allowed_flags: tuple[str, ...] = ("normal",),
) -> pd.DataFrame:
    """Return rows whose retention quality flags are allowed for analyzer input."""
    _require_columns(
        summary_df,
        ["retention_quality_flag"],
        "Kaggle battery cycle summary",
    )
    allowed_flag_set = set(allowed_flags)
    mask = summary_df["retention_quality_flag"].isin(allowed_flag_set)
    analysis_ready_df = summary_df.loc[mask].copy().reset_index(drop=True)
    validate_kaggle_battery_summary_schema(analysis_ready_df)
    return analysis_ready_df


def validate_kaggle_battery_summary_schema(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Validate required summary columns and return domain violations."""
    _require_columns(
        summary_df,
        KAGGLE_BATTERY_SUMMARY_COLUMNS,
        "Kaggle battery cycle summary",
    )

    return validate_domain_constraints(
        df=summary_df,
        constraints=KAGGLE_BATTERY_SUMMARY_CONSTRAINTS,
    )
