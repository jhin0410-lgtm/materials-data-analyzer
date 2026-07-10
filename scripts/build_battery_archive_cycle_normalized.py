"""Build a normalized Battery Archive cycle table from audited cycle CSV schemas."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loaders.battery_archive_cycle_loader import (  # noqa: E402
    load_battery_archive_cycle_data,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Load Battery Archive cycle_data CSVs directly from raw zip members "
            "and create a canonical normalized cycle table."
        )
    )
    parser.add_argument("--raw-dir", required=True, help="Raw Battery Archive zip directory.")
    parser.add_argument("--inventory", required=True, help="Enriched cycle file inventory CSV.")
    parser.add_argument("--schema-inventory", required=True, help="Cycle schema inventory CSV.")
    parser.add_argument("--column-inventory", required=True, help="Cycle column inventory CSV.")
    parser.add_argument("--normalized-output", required=True, help="Normalized cycle CSV path.")
    parser.add_argument("--summary-output", required=True, help="File-level load summary CSV path.")
    parser.add_argument("--mapping-output", required=True, help="Column mapping contract CSV path.")
    return parser.parse_args()


def print_console_summary(
    normalized_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    mapping_df: pd.DataFrame,
) -> None:
    """Print concise normalization summary."""
    print(f"cycle file count: {len(summary_df)}")
    print(f"normalized row count: {len(normalized_df)}")
    print(f"raw row count: {int(summary_df['raw_row_count'].sum()) if not summary_df.empty else 0}")
    print(
        "load status counts: "
        + str(summary_df["load_status"].value_counts(dropna=False).to_dict())
    )
    print(
        "dropped blank rows: "
        + str(int(summary_df["dropped_blank_row_count"].sum()) if not summary_df.empty else 0)
    )
    invalid_columns = [
        "invalid_cycle_index_count",
        "invalid_charge_capacity_count",
        "invalid_discharge_capacity_count",
        "invalid_charge_energy_count",
        "invalid_discharge_energy_count",
    ]
    invalid_counts = {
        column: int(summary_df[column].sum()) if column in summary_df else 0
        for column in invalid_columns
    }
    print(f"invalid numeric counts: {invalid_counts}")
    schema_file_counts = summary_df["schema_fingerprint"].value_counts(dropna=False).to_dict()
    schema_row_counts = (
        normalized_df["schema_fingerprint"].value_counts(dropna=False).to_dict()
        if "schema_fingerprint" in normalized_df
        else {}
    )
    source_row_counts = (
        normalized_df["source"].value_counts(dropna=False).head(20).to_dict()
        if "source" in normalized_df
        else {}
    )
    print(f"schema file counts: {schema_file_counts}")
    print(f"schema row counts: {schema_row_counts}")
    print(f"source row counts: {source_row_counts}")
    print(f"mapping rows: {len(mapping_df)}")
    print("normalized columns: " + ", ".join(normalized_df.columns.astype(str)))


def main() -> None:
    """Run Battery Archive cycle normalization."""
    args = parse_args()
    normalized_output = Path(args.normalized_output)
    summary_output = Path(args.summary_output)
    mapping_output = Path(args.mapping_output)

    try:
        inventory_df = pd.read_csv(args.inventory)
        schema_inventory_df = pd.read_csv(args.schema_inventory)
        column_inventory_df = pd.read_csv(args.column_inventory)
        normalized_df, summary_df, mapping_df = load_battery_archive_cycle_data(
            raw_dir=args.raw_dir,
            inventory_df=inventory_df,
            schema_inventory_df=schema_inventory_df,
            column_inventory_df=column_inventory_df,
        )
    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError) as exc:
        print(f"Battery Archive cycle normalization failed: {exc}", file=sys.stderr)
        sys.exit(1)

    normalized_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    mapping_output.parent.mkdir(parents=True, exist_ok=True)

    normalized_df.to_csv(normalized_output, index=False)
    summary_df.to_csv(summary_output, index=False)
    mapping_df.to_csv(mapping_output, index=False)

    print(f"normalized output: {normalized_output}")
    print(f"summary output: {summary_output}")
    print(f"mapping output: {mapping_output}")
    print_console_summary(normalized_df, summary_df, mapping_df)


if __name__ == "__main__":
    main()
