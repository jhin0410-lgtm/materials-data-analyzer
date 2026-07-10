"""Enrich Battery Archive cycle file inventory with filename-derived metadata."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from connectors.battery_archive_connector import (  # noqa: E402
    BATTERY_ARCHIVE_METADATA_COLUMNS,
    enrich_cycle_file_inventory,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Add conservative filename-derived metadata to a Battery Archive "
            "cycle file inventory CSV."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input battery_archive_cycle_file_inventory.csv path.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output enriched inventory CSV path.",
    )
    return parser.parse_args()


def _coverage_summary(enriched_df: pd.DataFrame) -> list[tuple[str, int, float]]:
    """Return non-null/non-unknown coverage by metadata field."""
    rows: list[tuple[str, int, float]] = []
    for column in BATTERY_ARCHIVE_METADATA_COLUMNS:
        if column in {"metadata_parse_status", "metadata_parse_message"}:
            continue
        series = enriched_df[column]
        if pd.api.types.is_numeric_dtype(series):
            count = int(series.notna().sum())
        else:
            coverage_mask = (
                series.notna()
                & series.astype(str).str.strip().ne("")
                & series.astype(str).str.lower().ne("unknown")
            )
            count = int(coverage_mask.sum())
        coverage = count / len(enriched_df) * 100 if len(enriched_df) else 0.0
        rows.append((column, count, coverage))
    return rows


def print_parse_summary(enriched_df: pd.DataFrame) -> None:
    """Print parse coverage and value-count summary."""
    total_rows = len(enriched_df)
    status_counts = (
        enriched_df["metadata_parse_status"].value_counts(dropna=False).sort_index()
    )
    print(f"total rows: {total_rows}")
    print(f"parsed rows: {int(status_counts.get('parsed', 0))}")
    print(f"partially parsed rows: {int(status_counts.get('partially_parsed', 0))}")
    print(f"unparsed rows: {int(status_counts.get('unparsed', 0))}")

    print("metadata field coverage:")
    for column, count, coverage in _coverage_summary(enriched_df):
        print(f"- {column}: {count}/{total_rows} ({coverage:.1f}%)")

    print("chemistry value counts:")
    chemistry_counts = enriched_df["chemistry"].value_counts(dropna=False).sort_index()
    for value, count in chemistry_counts.items():
        print(f"- {value}: {count}")

    print("form factor value counts:")
    for value, count in (
        enriched_df["form_factor"].value_counts(dropna=False).sort_index().items()
    ):
        print(f"- {value}: {count}")

    unparsed = enriched_df[
        enriched_df["metadata_parse_status"].isin(["unparsed", "partially_parsed"])
    ]
    print("unparsed or partially parsed filename examples:")
    if unparsed.empty:
        print("- none")
    else:
        for value in unparsed["file_name"].head(10):
            print(f"- {value}")


def main() -> None:
    """Run inventory enrichment from the command line."""
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        inventory_df = pd.read_csv(input_path)
        enriched_df = enrich_cycle_file_inventory(inventory_df)
    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError) as exc:
        print(f"Battery Archive inventory enrichment failed: {exc}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    enriched_df.to_csv(output_path, index=False)

    print(f"input path: {input_path}")
    print(f"output path: {output_path}")
    print_parse_summary(enriched_df)


if __name__ == "__main__":
    main()
