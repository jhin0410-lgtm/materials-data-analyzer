"""Build Battery Archive analysis-ready cycle tables from normalized cycles."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loaders.battery_archive_cycle_features import (  # noqa: E402
    assert_no_absolute_paths,
    build_analysis_ready_tables,
    output_size_bytes,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Create Battery Archive cycle-level analysis-ready and quality "
            "summary tables from the v1.1.3b normalized cycle CSV."
        )
    )
    parser.add_argument("--input", required=True, help="Normalized cycle CSV path.")
    parser.add_argument(
        "--analysis-ready-output",
        required=True,
        help="Cycle-level analysis-ready CSV path.",
    )
    parser.add_argument(
        "--series-summary-output",
        required=True,
        help="Compact cycle-series summary CSV path.",
    )
    parser.add_argument(
        "--quality-summary-output",
        required=True,
        help="Compact data-quality summary CSV path.",
    )
    return parser.parse_args()


def _print_summary(
    analysis_ready_df: pd.DataFrame,
    series_summary_df: pd.DataFrame,
    quality_summary_df: pd.DataFrame,
    analysis_ready_output: Path,
    series_summary_output: Path,
    quality_summary_output: Path,
) -> None:
    """Print concise CLI smoke summary."""
    total_rows = len(analysis_ready_df)
    print(f"analysis-ready row count: {total_rows}")
    print(f"series count: {len(series_summary_df)}")
    print(
        "row quality counts: "
        + str(analysis_ready_df["quality_status"].value_counts(dropna=False).to_dict())
    )
    print(
        "baseline status counts: "
        + str(series_summary_df["baseline_status"].value_counts(dropna=False).to_dict())
    )
    print(
        "retention coverage rows: "
        + str(int(analysis_ready_df["capacity_retention_pct"].notna().sum()))
    )
    print(
        "mixed unit series count: "
        + str(int(series_summary_df["mixed_capacity_unit"].sum()))
    )
    print(
        "duplicate cycle-index series count: "
        + str(int(series_summary_df["has_duplicate_cycle_index"].sum()))
    )
    print(
        "nonmonotonic cycle-index series count: "
        + str(int(series_summary_df["has_nonmonotonic_cycle_index"].sum()))
    )
    print(
        "80pct threshold reached series: "
        + str(int(series_summary_df["reached_80pct_threshold"].sum()))
    )
    print(
        "70pct threshold reached series: "
        + str(int(series_summary_df["reached_70pct_threshold"].sum()))
    )
    print(
        "80pct observed-censored series: "
        + str(int(series_summary_df["observed_censored_80pct"].sum()))
    )
    print(
        "70pct observed-censored series: "
        + str(int(series_summary_df["observed_censored_70pct"].sum()))
    )
    print(
        "source series counts: "
        + str(series_summary_df["source"].value_counts(dropna=False).to_dict())
    )
    print(f"quality summary rows: {len(quality_summary_df)}")
    print(
        "output sizes bytes: "
        + str(
            {
                str(analysis_ready_output): output_size_bytes(analysis_ready_output),
                str(series_summary_output): output_size_bytes(series_summary_output),
                str(quality_summary_output): output_size_bytes(quality_summary_output),
            }
        )
    )


def main() -> None:
    """Run Battery Archive analysis-ready table generation."""
    args = parse_args()
    input_path = Path(args.input)
    analysis_ready_output = Path(args.analysis_ready_output)
    series_summary_output = Path(args.series_summary_output)
    quality_summary_output = Path(args.quality_summary_output)

    try:
        normalized_df = pd.read_csv(input_path, low_memory=False)
        analysis_ready_df, series_summary_df, quality_summary_df = (
            build_analysis_ready_tables(normalized_df)
        )
        assert_no_absolute_paths(analysis_ready_df)
        assert_no_absolute_paths(series_summary_df)
    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError) as exc:
        print(f"Battery Archive analysis-ready build failed: {exc}", file=sys.stderr)
        sys.exit(1)

    for output_path in [
        analysis_ready_output,
        series_summary_output,
        quality_summary_output,
    ]:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    analysis_ready_df.to_csv(analysis_ready_output, index=False)
    series_summary_df.to_csv(series_summary_output, index=False)
    quality_summary_df.to_csv(quality_summary_output, index=False)

    print(f"input: {input_path}")
    print("overwrite policy: explicit output paths are overwritten when present")
    print(f"analysis-ready output: {analysis_ready_output}")
    print(f"series summary output: {series_summary_output}")
    print(f"quality summary output: {quality_summary_output}")
    _print_summary(
        analysis_ready_df,
        series_summary_df,
        quality_summary_df,
        analysis_ready_output,
        series_summary_output,
        quality_summary_output,
    )


if __name__ == "__main__":
    main()
