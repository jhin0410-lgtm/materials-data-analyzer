"""Data cleaning and column-name preprocessing helpers."""

from __future__ import annotations

import re

import pandas as pd


def clean_column_name(column_name: str) -> str:
    """Convert one column name to lowercase snake_case.

    Example: "Process Temp C" becomes "process_temp_c".
    """
    cleaned = column_name.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_")


def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of the data with clean, unique column names.

    If two original columns become the same after cleanup, this function adds a
    suffix such as _2 or _3. That keeps pandas from confusing the columns.
    """
    cleaned_df = df.copy()
    cleaned_names = [clean_column_name(str(column)) for column in cleaned_df.columns]

    seen_names: dict[str, int] = {}
    unique_names: list[str] = []
    for name in cleaned_names:
        base_name = name or "column"
        seen_names[base_name] = seen_names.get(base_name, 0) + 1

        if seen_names[base_name] == 1:
            unique_names.append(base_name)
        else:
            unique_names.append(f"{base_name}_{seen_names[base_name]}")

    cleaned_df.columns = unique_names
    return cleaned_df


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Compatibility alias for the older function name."""
    return standardize_column_names(df)


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Apply light data cleaning before analysis.

    This function avoids changing measured experiment values too aggressively.
    It only performs simple cleanup steps:
    - Remove rows that are completely empty.
    - Strip leading and trailing spaces from text columns.
    - Treat empty strings as missing values.
    - Convert text columns to numbers when most values look numeric.
    - Remove exact duplicate rows.
    """
    cleaned_df = df.copy()
    cleaned_df = cleaned_df.dropna(how="all")

    for column in cleaned_df.columns:
        if (
            pd.api.types.is_object_dtype(cleaned_df[column])
            or pd.api.types.is_string_dtype(cleaned_df[column])
        ):
            cleaned_df[column] = cleaned_df[column].astype("string").str.strip()
            cleaned_df[column] = cleaned_df[column].replace("", pd.NA)

            # If almost all non-missing values can become numbers, convert the
            # whole column to numeric. This helps with CSV files where numbers
            # were read as text.
            converted = pd.to_numeric(cleaned_df[column], errors="coerce")
            original_non_missing = cleaned_df[column].notna()
            if original_non_missing.any():
                success_rate = converted[original_non_missing].notna().mean()
                if success_rate >= 0.9:
                    cleaned_df[column] = converted

    cleaned_df = cleaned_df.drop_duplicates()
    return cleaned_df.reset_index(drop=True)


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
