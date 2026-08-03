"""Data cleaning and column-name preprocessing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd


PREPROCESSING_AUDIT_SCHEMA_VERSION = "1.0"
DEFAULT_NUMERIC_CONVERSION_THRESHOLD = 0.9


def is_protected_semantic_column(column: str) -> bool:
    """Return whether automatic numeric coercion could damage column semantics."""
    name = clean_column_name(column)
    identifier_names = {
        "id", "uid", "uuid", "sample", "sample_id", "battery_id", "measurement_id",
        "material_id", "lot_id", "batch_id", "wafer_id", "asset_id", "group_id",
        "serial_number", "source_file", "source_filename", "source_path",
        "file_path", "sha256", "checksum", "method", "unit", "label", "code",
    }
    return (
        name in identifier_names
        or name.endswith(("_id", "_identifier", "_uuid", "_uid", "_sha256", "_checksum"))
        or name.endswith(("_path", "_filename", "_file"))
        or name.startswith(("id_", "uuid_", "uid_"))
    )


@dataclass(frozen=True)
class PreprocessingResult:
    """Preprocessed data plus a JSON-safe audit of every automatic change."""

    dataframe: pd.DataFrame
    audit: dict[str, Any]
    warnings: tuple[str, ...]


def clean_column_name(column_name: str) -> str:
    """Convert one column name to lowercase snake_case.

    Example: "Process Temp C" becomes "process_temp_c".
    """
    cleaned = column_name.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_")


def _column_name_plan(
    columns: list[object], *, fail_on_collision: bool
) -> tuple[list[str], list[dict[str, Any]]]:
    original_names = [str(column) for column in columns]
    normalized_names = [clean_column_name(name) or "column" for name in original_names]

    normalized_counts: dict[str, int] = {}
    for name in normalized_names:
        normalized_counts[name] = normalized_counts.get(name, 0) + 1

    collisions = {
        name: [
            original
            for original, normalized in zip(original_names, normalized_names)
            if normalized == name
        ]
        for name, count in normalized_counts.items()
        if count > 1
    }
    if collisions and fail_on_collision:
        collision_text = "; ".join(
            f"{normalized}: {originals}" for normalized, originals in collisions.items()
        )
        raise ValueError(
            "Column names collide after normalization. Rename the source columns "
            "instead of relying on an inferred suffix. "
            f"Collisions: {collision_text}"
        )

    seen_names: dict[str, int] = {}
    final_names: list[str] = []
    mapping_rows: list[dict[str, Any]] = []
    for position, (original, normalized) in enumerate(
        zip(original_names, normalized_names), start=1
    ):
        seen_names[normalized] = seen_names.get(normalized, 0) + 1
        occurrence = seen_names[normalized]
        final_name = normalized if occurrence == 1 else f"{normalized}_{occurrence}"
        collision_detected = normalized_counts[normalized] > 1
        final_names.append(final_name)
        mapping_rows.append(
            {
                "column_position": position,
                "original_name": original,
                "normalized_base_name": normalized,
                "final_name": final_name,
                "collision_detected": collision_detected,
                "action": (
                    "normalized_with_suffix"
                    if collision_detected and occurrence > 1
                    else "normalized"
                ),
            }
        )

    return final_names, mapping_rows


def standardize_column_names(
    df: pd.DataFrame, *, fail_on_collision: bool = False
) -> pd.DataFrame:
    """Return a copy with normalized column names.

    The compatibility default keeps the historical suffix behavior. User-facing
    workflows should pass ``fail_on_collision=True`` so ambiguous source headers
    are rejected rather than silently assigned ``_2`` or ``_3`` suffixes.
    """
    cleaned_df = df.copy()
    final_names, _ = _column_name_plan(
        list(cleaned_df.columns), fail_on_collision=fail_on_collision
    )
    cleaned_df.columns = final_names
    return cleaned_df


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Compatibility alias for the older function name."""
    return standardize_column_names(df)


def _clean_data_with_operations(
    df: pd.DataFrame,
    *,
    numeric_conversion_threshold: float,
    protected_columns: Iterable[str] = (),
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[str], int, list[dict[str, Any]]]:
    if not 0.0 <= numeric_conversion_threshold <= 1.0:
        raise ValueError("numeric_conversion_threshold must be between 0 and 1")

    cleaned_df = df.copy()
    input_row_count = len(cleaned_df)
    empty_mask = cleaned_df.isna().all(axis=1)
    excluded_rows = [
        {"source_row_number": int(position + 2), "reason": "all_values_missing"}
        for position, excluded in enumerate(empty_mask.tolist())
        if excluded
    ]
    cleaned_df = cleaned_df.loc[~empty_mask].copy()
    dropped_all_empty_rows = input_row_count - len(cleaned_df)

    protected_column_set = {clean_column_name(name) for name in protected_columns}
    operations: list[dict[str, Any]] = []
    warnings: list[str] = []

    for column in cleaned_df.columns:
        series_before = cleaned_df[column].copy()
        original_dtype = str(series_before.dtype)
        missing_before = int(series_before.isna().sum())
        blank_strings_normalized = 0
        numeric_conversion_applied = False
        numeric_conversion_success_rate: float | None = None
        numeric_conversion_failures = 0
        numeric_conversion_skipped_reason: str | None = None
        protected_semantic_column = (
            is_protected_semantic_column(str(column))
            or clean_column_name(str(column)) in protected_column_set
        )

        if (
            pd.api.types.is_object_dtype(cleaned_df[column])
            or pd.api.types.is_string_dtype(cleaned_df[column])
        ):
            text_series = cleaned_df[column].astype("string").str.strip()
            blank_mask = text_series.eq("")
            blank_strings_normalized = int(blank_mask.fillna(False).sum())
            text_series = text_series.replace("", pd.NA)
            cleaned_df[column] = text_series

            converted = pd.to_numeric(text_series, errors="coerce")
            original_non_missing = text_series.notna()
            if protected_semantic_column:
                numeric_conversion_skipped_reason = "protected_identifier_or_provenance_semantics"
            elif original_non_missing.any():
                numeric_conversion_success_rate = float(
                    converted[original_non_missing].notna().mean()
                )
                if numeric_conversion_success_rate >= numeric_conversion_threshold:
                    failure_mask = original_non_missing & converted.isna()
                    numeric_conversion_failures = int(failure_mask.sum())
                    numeric_conversion_applied = True
                    cleaned_df[column] = converted
                    if numeric_conversion_failures:
                        warnings.append(
                            f"Column '{column}' was converted to numeric and "
                            f"{numeric_conversion_failures} non-missing value(s) "
                            "could not be converted; they are recorded as missing."
                        )

        missing_after = int(cleaned_df[column].isna().sum())
        operations.append(
            {
                "column": str(column),
                "original_dtype": original_dtype,
                "final_dtype": str(cleaned_df[column].dtype),
                "missing_before": missing_before,
                "missing_after": missing_after,
                "introduced_missing_count": max(0, missing_after - missing_before),
                "blank_strings_normalized": blank_strings_normalized,
                "numeric_conversion_applied": numeric_conversion_applied,
                "numeric_conversion_success_rate": numeric_conversion_success_rate,
                "numeric_conversion_failures": numeric_conversion_failures,
                "protected_semantic_column": protected_semantic_column,
                "numeric_conversion_skipped_reason": numeric_conversion_skipped_reason,
            }
        )

    return (
        cleaned_df.reset_index(drop=True),
        operations,
        warnings,
        dropped_all_empty_rows,
        excluded_rows,
    )


def preprocess_data(
    df: pd.DataFrame,
    *,
    fail_on_column_collision: bool = True,
    numeric_conversion_threshold: float = DEFAULT_NUMERIC_CONVERSION_THRESHOLD,
    protected_columns: Iterable[str] = (),
) -> PreprocessingResult:
    """Run conservative preprocessing and return a complete transformation audit."""
    standardized_df = df.copy()
    final_names, column_mappings = _column_name_plan(
        list(standardized_df.columns),
        fail_on_collision=fail_on_column_collision,
    )
    standardized_df.columns = final_names

    (
        cleaned_df,
        column_operations,
        warnings,
        dropped_rows,
        excluded_rows,
    ) = _clean_data_with_operations(
        standardized_df,
        numeric_conversion_threshold=numeric_conversion_threshold,
        protected_columns=protected_columns,
    )

    audit: dict[str, Any] = {
        "schema_version": PREPROCESSING_AUDIT_SCHEMA_VERSION,
        "input_row_count": int(len(df)),
        "output_row_count": int(len(cleaned_df)),
        "input_column_count": int(df.shape[1]),
        "output_column_count": int(cleaned_df.shape[1]),
        "dropped_all_empty_row_count": int(dropped_rows),
        "excluded_rows": excluded_rows,
        "source_row_number_convention": "one-based CSV row including header",
        "duplicate_rows_preserved": True,
        "column_name_policy": (
            "fail_on_collision"
            if fail_on_column_collision
            else "suffix_on_collision"
        ),
        "numeric_conversion_threshold": float(numeric_conversion_threshold),
        "column_mappings": column_mappings,
        "column_operations": column_operations,
        "warning_count": len(warnings),
        "warnings": list(warnings),
    }
    return PreprocessingResult(
        dataframe=cleaned_df,
        audit=audit,
        warnings=tuple(warnings),
    )


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the historical conservative cleanup and return only the DataFrame.

    Use :func:`preprocess_data` in user-facing workflows when provenance of
    automatic conversions and exclusions must be retained.
    """
    cleaned_df, _, _, _, _ = _clean_data_with_operations(
        df,
        numeric_conversion_threshold=DEFAULT_NUMERIC_CONVERSION_THRESHOLD,
    )
    return cleaned_df


def get_numeric_columns(df: pd.DataFrame) -> list[str]:
    """Return columns that pandas recognizes as numeric."""
    return df.select_dtypes(include="number").columns.tolist()


def prepare_target_column(target: str | None, df: pd.DataFrame) -> str | None:
    """Clean and validate the optional target column name."""
    if target is None:
        return None

    cleaned_target = clean_column_name(target)
    if cleaned_target not in df.columns:
        available_columns = ", ".join(df.columns)
        raise ValueError(
            f"Target column was not found: {target}\n"
            f"After column-name cleanup, it was searched as: {cleaned_target}\n"
            f"Available columns are: {available_columns}"
        )

    if not pd.api.types.is_numeric_dtype(df[cleaned_target]):
        raise ValueError(
            f"Target column exists but is not numeric: {cleaned_target}\n"
            "Correlation analysis needs a numeric target column."
        )

    return cleaned_target
