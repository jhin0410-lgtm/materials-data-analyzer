"""Extract cycle-level discharge features from Kaggle NASA raw CSV files.

This module reads only the raw discharge CSV files referenced by the
analysis-ready cycle summary. Each raw time-series CSV is read one at a time,
summarized into scalar features, and then discarded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


TRACE_COLUMNS = [
    "analysis_row_index",
    "battery_id",
    "cycle_index",
    "source_filename",
    "uid",
    "test_id",
]

FEATURE_VALUE_COLUMNS = [
    "discharge_duration_s",
    "voltage_mean_v",
    "voltage_min_v",
    "voltage_max_v",
    "current_mean_a",
    "current_min_a",
    "current_max_a",
    "temperature_mean_c",
    "temperature_min_c",
    "temperature_max_c",
    "temperature_rise_c",
    "raw_sample_count",
]

FEATURE_STATUS_COLUMN = "feature_extraction_status"
DISCHARGE_FEATURE_COLUMNS = FEATURE_VALUE_COLUMNS + [FEATURE_STATUS_COLUMN]

COLUMN_CANDIDATES = {
    "time": ["time", "Time"],
    "voltage": ["voltage", "Voltage_measured", "Voltage_load"],
    "current": ["current", "Current_measured", "Current_load"],
    "temperature": ["temperature", "Temperature_measured"],
}


def resolve_discharge_file_path(raw_data_root: str | Path, source_filename: Any) -> Path:
    """Resolve a raw discharge CSV path from the root folder and source filename."""
    if pd.isna(source_filename) or str(source_filename).strip() == "":
        raise ValueError("source_filename is missing.")

    filename_path = Path(str(source_filename).strip())
    if filename_path.is_absolute():
        return filename_path
    return Path(raw_data_root) / filename_path


def load_discharge_csv(path: str | Path) -> pd.DataFrame:
    """Load one raw discharge CSV file."""
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Raw discharge CSV file was not found: {csv_path}")
    if not csv_path.is_file():
        raise FileNotFoundError(f"Raw discharge CSV path is not a file: {csv_path}")

    try:
        discharge_df = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"Raw discharge CSV is empty: {csv_path}") from exc

    if discharge_df.empty:
        raise ValueError(f"Raw discharge CSV has no data rows: {csv_path}")

    return discharge_df


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find a matching column by exact name first, then case-insensitive name."""
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    lowered_to_original = {str(column).strip().lower(): column for column in df.columns}
    for candidate in candidates:
        match = lowered_to_original.get(candidate.strip().lower())
        if match is not None:
            return str(match)
    return None


def _numeric_series(df: pd.DataFrame, column: str | None) -> pd.Series:
    """Return a numeric series, or an empty numeric series when missing."""
    if column is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").dropna()


def _series_mean(series: pd.Series) -> float:
    return float(series.mean()) if not series.empty else np.nan


def _series_min(series: pd.Series) -> float:
    return float(series.min()) if not series.empty else np.nan


def _series_max(series: pd.Series) -> float:
    return float(series.max()) if not series.empty else np.nan


def _empty_feature_record(status: str, raw_sample_count: int = 0) -> dict[str, object]:
    """Create a feature record with unavailable feature values."""
    record: dict[str, object] = {
        column: np.nan for column in FEATURE_VALUE_COLUMNS
    }
    record["raw_sample_count"] = raw_sample_count
    record[FEATURE_STATUS_COLUMN] = status
    return record


def extract_discharge_features(discharge_df: pd.DataFrame) -> dict[str, object]:
    """Extract scalar physical features from one raw discharge time-series table."""
    if discharge_df.empty:
        return _empty_feature_record("empty_raw_csv")

    selected_columns = {
        name: _find_column(discharge_df, candidates)
        for name, candidates in COLUMN_CANDIDATES.items()
    }
    missing_groups = [
        name for name, column in selected_columns.items() if column is None
    ]

    time = _numeric_series(discharge_df, selected_columns["time"])
    voltage = _numeric_series(discharge_df, selected_columns["voltage"])
    current = _numeric_series(discharge_df, selected_columns["current"])
    temperature = _numeric_series(discharge_df, selected_columns["temperature"])

    if len(missing_groups) == len(COLUMN_CANDIDATES):
        status = "missing_columns: time, voltage, current, temperature"
    elif missing_groups:
        status = f"missing_columns: {', '.join(missing_groups)}"
    else:
        status = "ok"

    discharge_duration = (
        float(time.max() - time.min()) if not time.empty else np.nan
    )
    temperature_rise = (
        float(temperature.max() - temperature.min())
        if not temperature.empty
        else np.nan
    )

    return {
        "discharge_duration_s": discharge_duration,
        "voltage_mean_v": _series_mean(voltage),
        "voltage_min_v": _series_min(voltage),
        "voltage_max_v": _series_max(voltage),
        "current_mean_a": _series_mean(current),
        "current_min_a": _series_min(current),
        "current_max_a": _series_max(current),
        "temperature_mean_c": _series_mean(temperature),
        "temperature_min_c": _series_min(temperature),
        "temperature_max_c": _series_max(temperature),
        "temperature_rise_c": temperature_rise,
        "raw_sample_count": int(len(discharge_df)),
        FEATURE_STATUS_COLUMN: status,
    }


def _trace_values(row: pd.Series, analysis_row_index: int) -> dict[str, object]:
    """Copy trace columns from an analysis summary row."""
    trace = {"analysis_row_index": analysis_row_index}
    for column in TRACE_COLUMNS:
        if column == "analysis_row_index":
            continue
        trace[column] = row[column] if column in row.index else pd.NA
    return trace


def build_discharge_feature_table(
    analysis_summary_df: pd.DataFrame,
    raw_data_root: str | Path,
    limit: int | None = None,
) -> pd.DataFrame:
    """Build a feature table for referenced analysis-ready discharge rows."""
    if "source_filename" not in analysis_summary_df.columns:
        raise ValueError("analysis_summary_df must include source_filename.")
    if limit is not None and limit < 1:
        raise ValueError("limit must be 1 or greater, or None for all rows.")

    selected_rows = (
        analysis_summary_df
        if limit is None
        else analysis_summary_df.head(limit)
    )
    records: list[dict[str, object]] = []

    for analysis_row_index, row in selected_rows.iterrows():
        record = _trace_values(row, int(analysis_row_index))
        try:
            raw_path = resolve_discharge_file_path(
                raw_data_root=raw_data_root,
                source_filename=row["source_filename"],
            )
            if not raw_path.exists():
                features = _empty_feature_record("source_file_not_found")
            else:
                discharge_df = load_discharge_csv(raw_path)
                features = extract_discharge_features(discharge_df)
        except ValueError as exc:
            features = _empty_feature_record(str(exc))
        except (OSError, pd.errors.ParserError) as exc:
            features = _empty_feature_record(f"read_error: {exc}")

        record.update(features)
        records.append(record)

    return pd.DataFrame(records, columns=TRACE_COLUMNS + DISCHARGE_FEATURE_COLUMNS)


def merge_discharge_features(
    analysis_summary_df: pd.DataFrame,
    feature_df: pd.DataFrame,
) -> pd.DataFrame:
    """Left-join extracted discharge features without changing summary row count."""
    if "analysis_row_index" in feature_df.columns:
        summary_with_index = analysis_summary_df.copy()
        summary_with_index["analysis_row_index"] = summary_with_index.index.astype(int)
        feature_columns = ["analysis_row_index"] + DISCHARGE_FEATURE_COLUMNS
        merged = summary_with_index.merge(
            feature_df[feature_columns],
            on="analysis_row_index",
            how="left",
            validate="one_to_one",
        )
        return merged.drop(columns=["analysis_row_index"])

    if "source_filename" not in analysis_summary_df.columns:
        raise ValueError("analysis_summary_df must include source_filename.")
    if "source_filename" not in feature_df.columns:
        raise ValueError("feature_df must include source_filename.")

    feature_columns = ["source_filename"] + DISCHARGE_FEATURE_COLUMNS
    return analysis_summary_df.merge(
        feature_df[feature_columns],
        on="source_filename",
        how="left",
        validate="many_to_one",
    )
