"""Input validation and lightweight profiling helpers for engineering CSV data."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pandas as pd


SUPPORTED_INPUT_EXTENSIONS = {".csv"}
DATETIME_NAME_HINTS = ("date", "time", "timestamp", "datetime")


def validate_input_file(path: str | Path, allowed_extensions=None) -> Path:
    """
    Validate that the input file exists, is a file, and has an allowed extension.
    Return pathlib.Path.
    """
    input_path = Path(path)
    extensions = allowed_extensions or SUPPORTED_INPUT_EXTENSIONS
    allowed = {extension.lower() for extension in extensions}

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input file was not found: {input_path}\n"
            "Please check the file path or create the CSV file first."
        )

    if not input_path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")

    if input_path.suffix.lower() not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(
            f"Unsupported input file extension '{input_path.suffix}' for {input_path}.\n"
            f"Supported extension(s): {allowed_text}."
        )

    return input_path


def load_engineering_csv(path: str | Path, min_rows: int = 2) -> pd.DataFrame:
    """
    Load an engineering CSV file and run basic validation.
    The function should:
    - validate file path and extension
    - handle empty CSV files
    - strip column name whitespace
    - detect duplicate columns after stripping
    - validate minimum shape
    - return a clean DataFrame
    """
    input_path = validate_input_file(path, SUPPORTED_INPUT_EXTENSIONS)
    _validate_header_has_no_duplicate_columns(input_path)

    try:
        df = pd.read_csv(input_path)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(
            f"The input file is empty: {input_path}\n"
            "Please add a header row and data rows before running the analyzer."
        ) from exc
    except pd.errors.ParserError as exc:
        raise ValueError(
            f"The input file could not be parsed as CSV: {input_path}\n"
            "Please check that the file is saved in a valid CSV format."
        ) from exc

    df = strip_column_whitespace(df)
    validate_no_duplicate_columns(df)
    validate_minimum_shape(df, min_rows=min_rows, min_columns=1)
    return df


def strip_column_whitespace(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading/trailing whitespace from column names."""
    cleaned = df.copy()
    cleaned.columns = [str(column).strip() for column in cleaned.columns]
    return cleaned


def validate_no_duplicate_columns(df: pd.DataFrame) -> None:
    """
    Detect duplicate column names.
    Do not silently rename duplicate columns.
    Raise ValueError with a clear message.
    """
    duplicate_names = _duplicate_values([str(column) for column in df.columns])
    if duplicate_names:
        duplicate_text = ", ".join(duplicate_names)
        raise ValueError(
            f"Duplicate column name(s) found after cleaning column headers: {duplicate_text}.\n"
            "Please rename duplicate columns in the CSV file."
        )


def validate_minimum_shape(df: pd.DataFrame, min_rows: int = 2, min_columns: int = 1) -> None:
    """Raise ValueError if the DataFrame is too small."""
    row_count, column_count = df.shape

    if column_count < min_columns:
        raise ValueError(
            f"The input dataset has too few columns: {column_count} column(s).\n"
            f"At least {min_columns} column(s) are required."
        )

    if row_count < min_rows:
        raise ValueError(
            f"The input dataset has too few rows: {row_count} row(s).\n"
            f"At least {min_rows} data row(s) are required for this workflow."
        )


def detect_numeric_columns(df: pd.DataFrame) -> list[str]:
    """Detect numeric columns using pandas dtype."""
    return df.select_dtypes(include="number").columns.tolist()


def detect_categorical_columns(df: pd.DataFrame) -> list[str]:
    """Detect object/category/bool columns as categorical candidates."""
    categorical_columns: list[str] = []

    for column in df.columns:
        dtype = df[column].dtype
        if (
            pd.api.types.is_object_dtype(dtype)
            or pd.api.types.is_string_dtype(dtype)
            or isinstance(dtype, pd.CategoricalDtype)
            or pd.api.types.is_bool_dtype(dtype)
        ):
            categorical_columns.append(str(column))

    return categorical_columns


def detect_datetime_like_columns(df: pd.DataFrame) -> list[str]:
    """
    Detect datetime-like columns.
    Keep this conservative. Do not aggressively convert all object columns.
    """
    datetime_columns: list[str] = []

    for column in df.columns:
        series = df[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            datetime_columns.append(str(column))
            continue

        if not _column_name_looks_datetime_like(str(column)):
            continue

        if not (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
            or isinstance(series.dtype, pd.CategoricalDtype)
        ):
            continue

        non_missing = series.dropna()
        if non_missing.empty:
            continue

        try:
            parsed = pd.to_datetime(non_missing, errors="coerce")
        except (TypeError, ValueError, OverflowError):
            continue

        valid_ratio = parsed.notna().mean()
        if valid_ratio >= 0.8:
            datetime_columns.append(str(column))

    return datetime_columns


def validate_target_column(df: pd.DataFrame, target: str | None) -> str | None:
    """Validate that target column exists when target is provided."""
    if target is None:
        return None

    cleaned_target = target.strip()
    if cleaned_target not in df.columns:
        available = ", ".join(map(str, df.columns))
        raise ValueError(
            f"Target column '{target}' was not found in the input dataset.\n"
            f"Available columns: {available}"
        )

    return cleaned_target


def validate_groupby_columns(df: pd.DataFrame, columns: list[str] | None) -> list[str]:
    """Validate that groupby columns exist when provided."""
    if columns is None:
        return []

    cleaned_columns = [column.strip() for column in columns]
    missing_columns = [column for column in cleaned_columns if column not in df.columns]

    if missing_columns:
        missing_text = ", ".join(missing_columns)
        available = ", ".join(map(str, df.columns))
        raise ValueError(
            f"Groupby column(s) were not found in the input dataset: {missing_text}.\n"
            f"Available columns: {available}"
        )

    return cleaned_columns


def build_data_profile(df: pd.DataFrame) -> dict[str, object]:
    """
    Build a data profile dictionary suitable for reports.
    Include:
    - row_count
    - column_count
    - numeric_columns
    - categorical_columns
    - datetime_like_columns
    - duplicate_rows_count
    - missing_values
    - numeric_summary
    - categorical_summary
    """
    numeric_columns = detect_numeric_columns(df)
    categorical_columns = detect_categorical_columns(df)
    datetime_like_columns = detect_datetime_like_columns(df)

    missing_count = df.isna().sum()
    missing_percent = (missing_count / len(df) * 100).round(2) if len(df) else missing_count
    missing_values = pd.DataFrame(
        {
            "column": missing_count.index,
            "missing_count": missing_count.astype(int).values,
            "missing_percent": missing_percent.values,
        }
    )

    if numeric_columns:
        numeric_summary = df[numeric_columns].describe().T.reset_index()
        numeric_summary = numeric_summary.rename(columns={"index": "column"})
    else:
        numeric_summary = pd.DataFrame()

    categorical_summary = pd.DataFrame(
        [
            {
                "column": column,
                "unique_count": int(df[column].nunique(dropna=True)),
                "missing_count": int(df[column].isna().sum()),
            }
            for column in categorical_columns
        ]
    )

    return {
        "row_count": int(len(df)),
        "column_count": int(df.shape[1]),
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "datetime_like_columns": datetime_like_columns,
        "duplicate_rows_count": int(df.duplicated().sum()),
        "missing_values": missing_values,
        "numeric_summary": numeric_summary,
        "categorical_summary": categorical_summary,
    }


def _validate_header_has_no_duplicate_columns(path: Path) -> None:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            header = next(csv.reader(csv_file), None)
    except UnicodeDecodeError:
        return

    if header is None:
        return

    stripped_header = [column.strip() for column in header]
    duplicate_names = _duplicate_values(stripped_header)

    if duplicate_names:
        duplicate_text = ", ".join(duplicate_names)
        raise ValueError(
            f"Duplicate column name(s) found after stripping whitespace: {duplicate_text}.\n"
            "Please rename duplicate columns in the CSV header."
        )


def _duplicate_values(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _column_name_looks_datetime_like(column_name: str) -> bool:
    normalized = column_name.lower().replace("-", "_").replace(" ", "_")
    return any(hint in normalized for hint in DATETIME_NAME_HINTS)