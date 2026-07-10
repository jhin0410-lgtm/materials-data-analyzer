"""Build Battery Archive reliability case-study summary artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loaders.battery_archive_case_study import (  # noqa: E402
    build_case_study_markdown,
    build_methodology_markdown,
    build_reliability_group_summary,
    save_group_summary,
    write_text,
)


def _count_true(series: pd.Series) -> int:
    """Count bool-like values from CSV safely."""
    return int(
        series.map(
            lambda value: (
                False
                if pd.isna(value)
                else str(value).strip().lower() in {"true", "1", "yes"}
            )
        ).sum()
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Build compact Battery Archive reliability group summaries and "
            "case-study documentation from the cycle-series summary table."
        )
    )
    parser.add_argument(
        "--series-summary",
        required=True,
        help="Input battery_archive_cycle_series_summary.csv path.",
    )
    parser.add_argument(
        "--group-summary-output",
        required=True,
        help="Output battery_archive_reliability_group_summary.csv path.",
    )
    parser.add_argument(
        "--report-output",
        required=True,
        help="Output Battery Archive case_study.md path.",
    )
    parser.add_argument(
        "--methodology-output",
        default=None,
        help="Optional methodology.md output path.",
    )
    return parser.parse_args()


def main() -> None:
    """Run Battery Archive case-study artifact generation."""
    args = parse_args()
    try:
        series_df = pd.read_csv(args.series_summary)
        group_summary_df = build_reliability_group_summary(series_df)
        report_markdown = build_case_study_markdown(series_df, group_summary_df)
        save_group_summary(group_summary_df, args.group_summary_output)
        write_text(args.report_output, report_markdown)
        if args.methodology_output:
            write_text(args.methodology_output, build_methodology_markdown())
    except (FileNotFoundError, pd.errors.EmptyDataError, ValueError) as exc:
        print(f"Battery Archive case-study build failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"series summary input: {args.series_summary}")
    print(f"group summary output: {args.group_summary_output}")
    print(f"case-study report output: {args.report_output}")
    if args.methodology_output:
        print(f"methodology output: {args.methodology_output}")
    print(f"group count: {len(group_summary_df)}")
    print(f"series count: {len(series_df)}")
    print(
        "threshold summary: "
        + str(
            {
                "reached_80pct": _count_true(series_df["reached_80pct_threshold"]),
                "reached_70pct": _count_true(series_df["reached_70pct_threshold"]),
                "observed_censored_80pct": _count_true(
                    series_df["observed_censored_80pct"]
                ),
                "observed_censored_70pct": _count_true(
                    series_df["observed_censored_70pct"]
                ),
            }
        )
    )
    print(
        "small group count: "
        + str(int(group_summary_df["small_group_flag"].astype(bool).sum()))
    )
    print(
        "warning group count: "
        + str(int(group_summary_df["warning_series_count"].gt(0).sum()))
    )
    print(
        "output sizes bytes: "
        + str(
            {
                args.group_summary_output: Path(args.group_summary_output).stat().st_size,
                args.report_output: Path(args.report_output).stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    main()
