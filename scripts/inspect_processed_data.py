"""Inspect processed CSV files before running the analyzer.

This utility is intentionally lightweight. It summarizes shape, column types,
missingness, duplicates, and simple numeric target candidates for processed
tabular engineering datasets.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


DEFAULT_TARGET_MISSING_THRESHOLD_PERCENT = 50.0


def inspect_processed_csv(
    input_path: str | Path,
    target_missing_threshold_percent: float = DEFAULT_TARGET_MISSING_THRESHOLD_PERCENT,
) -> dict[str, object]:
    """Return a compact inspection summary for a processed CSV file."""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file was not found: {path}")
    if not path.is_file():
        raise ValueError(f"Input path is not a file: {path}")

    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"CSV file is empty or has no columns: {path}") from exc

    if df.empty:
        raise ValueError(f"CSV file has no data rows: {path}")

    missing_percent_by_column = (df.isna().sum() / len(df) * 100).round(3)
    numeric_columns = df.select_dtypes(include="number").columns.tolist()
    non_numeric_columns = [
        column for column in df.columns.tolist() if column not in numeric_columns
    ]
    possible_target_columns = [
        column
        for column in numeric_columns
        if missing_percent_by_column[column] <= target_missing_threshold_percent
    ]

    return {
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": df.columns.tolist(),
        "numeric_columns": numeric_columns,
        "non_numeric_columns": non_numeric_columns,
        "missing_percent_by_column": missing_percent_by_column.to_dict(),
        "duplicate_row_count": int(df.duplicated().sum()),
        "possible_target_columns": possible_target_columns,
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Inspect a processed CSV before analyzer execution."
    )
    parser.add_argument("--input", required=True, help="Path to a processed CSV file.")
    return parser.parse_args()


def _print_list(name: str, values: list[object]) -> None:
    print(f"{name}:")
    if values:
        for value in values:
            print(f"- {value}")
    else:
        print("- none")


def print_summary(summary: dict[str, object]) -> None:
    """Print the inspection summary in a readable text format."""
    print(f"row_count: {summary['row_count']}")
    print(f"column_count: {summary['column_count']}")
    _print_list("columns", summary["columns"])
    _print_list("numeric_columns", summary["numeric_columns"])
    _print_list("non_numeric_columns", summary["non_numeric_columns"])

    print("missing_percent_by_column:")
    missing_percent_by_column = summary["missing_percent_by_column"]
    for column, percent in missing_percent_by_column.items():
        print(f"- {column}: {percent}")

    print(f"duplicate_row_count: {summary['duplicate_row_count']}")
    _print_list("possible_target_columns", summary["possible_target_columns"])


def main() -> None:
    """Run processed CSV inspection from the command line."""
    args = parse_args()
    try:
        summary = inspect_processed_csv(args.input)
    except (FileNotFoundError, ValueError, pd.errors.ParserError) as exc:
        print(f"Inspection failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print_summary(summary)


if __name__ == "__main__":
    main()
