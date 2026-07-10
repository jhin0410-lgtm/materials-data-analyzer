"""Audit Battery Archive cycle CSV schemas without extracting raw zips."""

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
    build_cycle_schema_audit_tables,
    summarize_mapping_coverage,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Inspect Battery Archive cycle_data CSV headers and bounded sample "
            "rows directly from raw zip members."
        )
    )
    parser.add_argument("--raw-dir", required=True, help="Raw Battery Archive zip directory.")
    parser.add_argument("--inventory", required=True, help="Cycle file inventory CSV path.")
    parser.add_argument("--schema-output", required=True, help="Schema inventory CSV path.")
    parser.add_argument("--column-output", required=True, help="Column inventory CSV path.")
    parser.add_argument("--report-output", required=True, help="Markdown audit report path.")
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=50,
        help="Maximum sample rows to read per cycle CSV member.",
    )
    return parser.parse_args()


def _markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    """Render a small DataFrame as a Markdown table."""
    if df.empty:
        return "_No rows._"
    view = df.head(max_rows).copy()
    columns = [str(column) for column in view.columns]
    rows = ["| " + " | ".join(columns) + " |"]
    rows.append("| " + " | ".join(["---"] * len(columns)) + " |")
    for _, row in view.iterrows():
        values = [
            str(row[column]).replace("\n", " ").replace("|", "\\|")
            for column in view.columns
        ]
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join(rows)


def _value_counts_table(series: pd.Series, name: str, count_name: str = "count") -> pd.DataFrame:
    """Build a deterministic value-count table."""
    return (
        series.value_counts(dropna=False)
        .rename_axis(name)
        .reset_index(name=count_name)
        .sort_values([count_name, name], ascending=[False, True])
        .reset_index(drop=True)
    )


def _mapping_file_count(column_df: pd.DataFrame, mapping_candidate: str) -> int:
    """Return number of files containing a mapping candidate."""
    if column_df.empty:
        return 0
    subset = column_df[column_df["mapping_candidate"].eq(mapping_candidate)]
    return int(subset["internal_csv_path"].nunique())


def _unit_variation_table(column_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize observed unit candidates by normalized column."""
    if column_df.empty:
        return pd.DataFrame(columns=["normalized_column_name", "unit_candidate", "count"])
    return (
        column_df.groupby(["normalized_column_name", "unit_candidate"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["count", "normalized_column_name"], ascending=[False, True])
        .reset_index(drop=True)
    )


def _schema_examples(schema_df: pd.DataFrame) -> pd.DataFrame:
    """Return top schemas with representative files."""
    if schema_df.empty:
        return pd.DataFrame(
            columns=["schema_fingerprint", "file_count", "column_count", "example_files"]
        )
    rows: list[dict[str, object]] = []
    for fingerprint, group in schema_df.groupby("schema_fingerprint", dropna=False):
        rows.append(
            {
                "schema_fingerprint": fingerprint,
                "file_count": len(group),
                "column_count": int(group["column_count"].iloc[0])
                if not group.empty
                else 0,
                "example_files": "; ".join(group["file_name"].head(3).astype(str)),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["file_count", "schema_fingerprint"], ascending=[False, True])
        .reset_index(drop=True)
    )


def build_schema_audit_report(
    raw_dir: str,
    inventory_path: str,
    schema_df: pd.DataFrame,
    column_df: pd.DataFrame,
    sample_rows: int,
) -> str:
    """Build a Markdown schema audit report from actual audit tables."""
    zip_count = int(schema_df["zip_file"].nunique()) if not schema_df.empty else 0
    inventory_rows = len(schema_df)
    status_counts = _value_counts_table(schema_df["read_status"], "read_status")
    success_like = schema_df["read_status"].isin(["success", "header_only"])
    audited_files = int(success_like.sum())
    unique_schema_count = int(schema_df["schema_fingerprint"].nunique())
    top_schema_df = _schema_examples(schema_df)
    top_raw_columns = _value_counts_table(column_df["raw_column_name"], "raw_column", "files")
    top_normalized_columns = _value_counts_table(
        column_df["normalized_column_name"],
        "normalized_column",
        "files",
    )
    mapping_coverage = summarize_mapping_coverage(column_df)
    unit_variation = _unit_variation_table(column_df)
    source_variation = (
        schema_df.groupby("zip_file", dropna=False)
        .agg(
            file_count=("internal_csv_path", "count"),
            unique_schema_count=("schema_fingerprint", "nunique"),
            read_error_count=(
                "read_status",
                lambda values: int((values == "read_error").sum()),
            ),
        )
        .reset_index()
        .sort_values(["zip_file"])
    )
    read_errors = schema_df[schema_df["read_status"].eq("read_error")][
        ["zip_file", "internal_csv_path", "read_message"]
    ]

    total_files = len(schema_df)
    coverage_rows = []
    for mapping in [
        "cycle_index",
        "charge_capacity",
        "discharge_capacity",
        "charge_energy",
        "discharge_energy",
        "coulombic_efficiency",
        "capacity_retention",
        "soh",
        "internal_resistance",
        "temperature",
        "elapsed_time",
        "date_or_timestamp",
    ]:
        file_count = _mapping_file_count(column_df, mapping)
        coverage_rows.append(
            {
                "mapping_candidate": mapping,
                "file_count": file_count,
                "coverage_percent": round(file_count / total_files * 100, 1)
                if total_files
                else 0.0,
            }
        )
    coverage_df = pd.DataFrame(coverage_rows)

    clear_mapping = coverage_df[coverage_df["file_count"].gt(0)]
    uncertain_mapping = column_df[
        column_df["mapping_confidence"].isin(["none", "low", "medium"])
    ][
        [
            "raw_column_name",
            "normalized_column_name",
            "mapping_candidate",
            "mapping_confidence",
            "mapping_note",
        ]
    ].drop_duplicates()

    lines = [
        "# Battery Archive Cycle Schema Audit",
        "",
        "Scope: cycle CSV schema audit only. Raw zip files were read in place with "
        "Python `zipfile`; no zip archive was extracted and no final normalized "
        "cycle table was created.",
        "",
        "## Inputs",
        "",
        f"- Raw directory: `{raw_dir}`",
        f"- Inventory: `{inventory_path}`",
        f"- Maximum sample rows per file: `{sample_rows}`",
        "",
        "## Summary",
        "",
        f"- Zip files represented: {zip_count}",
        f"- Inventory rows: {inventory_rows}",
        f"- Audited cycle files with readable headers: {audited_files}",
        f"- Unique schema fingerprints: {unique_schema_count}",
        f"- Unique raw columns: {int(column_df['raw_column_name'].nunique()) if not column_df.empty else 0}",
        "",
        "## Read Status Counts",
        "",
        _markdown_table(status_counts),
        "",
        "## Top Schema Fingerprints",
        "",
        _markdown_table(top_schema_df, max_rows=10),
        "",
        "## Source Archive Schema Variation",
        "",
        _markdown_table(source_variation),
        "",
        "## Frequent Raw Columns",
        "",
        _markdown_table(top_raw_columns, max_rows=20),
        "",
        "## Frequent Normalized Columns",
        "",
        _markdown_table(top_normalized_columns, max_rows=20),
        "",
        "## Mapping Candidate Coverage",
        "",
        _markdown_table(coverage_df),
        "",
        "## Unit Variation",
        "",
        _markdown_table(unit_variation, max_rows=30),
        "",
        "## Clearly Mappable Areas",
        "",
        _markdown_table(clear_mapping),
        "",
        "## Uncertain Or Non-target Mapping Areas",
        "",
        _markdown_table(uncertain_mapping, max_rows=30),
        "",
        "## Read Errors",
        "",
        _markdown_table(read_errors, max_rows=20),
        "",
        "## v1.1.3b Normalization Recommendations",
        "",
        "- Use `Cycle_Index` as the initial `cycle_index` candidate when present.",
        "- Preserve `Start_Time` and `End_Time` as optional timestamp-like columns.",
        "- Keep `Charge_Capacity` and `Discharge_Capacity` separate; do not infer "
        "direction from generic `Capacity` columns.",
        "- Preserve observed units such as `Ah`, `Wh`, `A`, `V`, and `s`; unit "
        "conversion is a later explicit step.",
        "- Treat missing direct retention, SOH, temperature, and internal resistance "
        "columns as schema facts, not failures.",
        "",
        "## Risks Before Normalization",
        "",
        "- A schema audit does not validate battery science conclusions.",
        "- Sample-row dtype inference may miss rare values outside the first rows.",
        "- Semantic mappings are candidates only; final normalization should remain "
        "reviewable and source-traceable.",
        "- Derived capacity retention, SOH, cycle-life proxy, and quality flags are "
        "out of scope for this audit.",
        "",
        "## Raw Zip Extraction Check",
        "",
        "This audit reads zip members directly and does not write extracted raw CSV "
        "files to `data/raw/` or any temporary extraction folder.",
        "",
        "## Generated Outputs",
        "",
        "- `data/processed/battery_archive_cycle_schema_inventory.csv`",
        "- `data/processed/battery_archive_cycle_column_inventory.csv`",
        "- `docs/BATTERY_ARCHIVE_CYCLE_SCHEMA_AUDIT.md`",
        "",
    ]
    return "\n".join(lines)


def print_console_summary(schema_df: pd.DataFrame, column_df: pd.DataFrame) -> None:
    """Print concise audit summary to stdout."""
    print(f"schema inventory rows: {len(schema_df)}")
    print(f"column inventory rows: {len(column_df)}")
    print(f"zip files represented: {schema_df['zip_file'].nunique() if not schema_df.empty else 0}")
    print(
        "read status counts: "
        + str(schema_df["read_status"].value_counts(dropna=False).to_dict())
    )
    print(
        "unique schema fingerprints: "
        + str(schema_df["schema_fingerprint"].nunique() if not schema_df.empty else 0)
    )
    print(
        "unique raw columns: "
        + str(column_df["raw_column_name"].nunique() if not column_df.empty else 0)
    )


def main() -> None:
    """Run Battery Archive cycle schema audit."""
    args = parse_args()
    inventory_path = Path(args.inventory)
    schema_output = Path(args.schema_output)
    column_output = Path(args.column_output)
    report_output = Path(args.report_output)

    try:
        inventory_df = pd.read_csv(inventory_path)
        schema_df, column_df = build_cycle_schema_audit_tables(
            raw_dir=args.raw_dir,
            inventory_df=inventory_df,
            sample_rows=args.sample_rows,
        )
    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError) as exc:
        print(f"Battery Archive cycle schema audit failed: {exc}", file=sys.stderr)
        sys.exit(1)

    schema_output.parent.mkdir(parents=True, exist_ok=True)
    column_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)

    schema_df.to_csv(schema_output, index=False)
    column_df.to_csv(column_output, index=False)
    report = build_schema_audit_report(
        raw_dir=args.raw_dir,
        inventory_path=args.inventory,
        schema_df=schema_df,
        column_df=column_df,
        sample_rows=args.sample_rows,
    )
    report_output.write_text(report, encoding="utf-8")

    print(f"schema output: {schema_output}")
    print(f"column output: {column_output}")
    print(f"report output: {report_output}")
    print_console_summary(schema_df, column_df)


if __name__ == "__main__":
    main()
