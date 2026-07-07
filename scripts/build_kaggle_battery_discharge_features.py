"""Build cycle-level raw discharge features for Kaggle NASA battery data."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loaders.kaggle_battery_discharge_features import (  # noqa: E402
    DISCHARGE_FEATURE_COLUMNS,
    FEATURE_STATUS_COLUMN,
    FEATURE_VALUE_COLUMNS,
    build_discharge_feature_table,
    merge_discharge_features,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Extract scalar discharge features from raw Kaggle NASA battery "
            "CSV files referenced by an analysis-ready summary."
        )
    )
    parser.add_argument("--summary", required=True, help="Analysis-ready summary CSV.")
    parser.add_argument("--raw-root", required=True, help="Raw discharge CSV folder.")
    parser.add_argument("--output", required=True, help="Output feature table CSV.")
    parser.add_argument(
        "--merged-output",
        required=True,
        help="Output analysis-ready summary joined with feature columns.",
    )
    parser.add_argument(
        "--limit",
        default="100",
        help="Number of summary rows to process. Use 'none' for all rows.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Process every analysis-ready summary row.",
    )
    return parser.parse_args()


def parse_limit(limit_value: str, full: bool) -> int | None:
    """Parse limit CLI value into an integer or None for full processing."""
    if full:
        return None
    normalized = str(limit_value).strip().lower()
    if normalized in {"none", "all", "full"}:
        return None
    try:
        limit = int(normalized)
    except ValueError as exc:
        raise ValueError("--limit must be an integer, 'none', 'all', or 'full'.") from exc
    if limit < 1:
        raise ValueError("--limit must be 1 or greater.")
    return limit


def load_summary(path: str | Path) -> pd.DataFrame:
    """Load the analysis-ready summary CSV."""
    summary_path = Path(path)
    if not summary_path.exists():
        raise FileNotFoundError(f"Analysis-ready summary CSV was not found: {summary_path}")
    if not summary_path.is_file():
        raise FileNotFoundError(f"Analysis-ready summary path is not a file: {summary_path}")

    try:
        summary_df = pd.read_csv(summary_path)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"Analysis-ready summary CSV is empty: {summary_path}") from exc

    if summary_df.empty:
        raise ValueError(f"Analysis-ready summary CSV has no data rows: {summary_path}")
    return summary_df


def missing_feature_ratio(feature_df: pd.DataFrame) -> float:
    """Return missing ratio across scalar numeric feature columns."""
    if feature_df.empty or not FEATURE_VALUE_COLUMNS:
        return 0.0
    missing_count = int(feature_df[FEATURE_VALUE_COLUMNS].isna().sum().sum())
    total_count = len(feature_df) * len(FEATURE_VALUE_COLUMNS)
    return missing_count / total_count if total_count else 0.0


def print_summary(feature_df: pd.DataFrame, merged_df: pd.DataFrame) -> None:
    """Print a concise feature extraction summary."""
    print(f"feature table row count: {len(feature_df)}")
    print(f"merged output row count: {len(merged_df)}")

    print("feature_extraction_status counts:")
    status_counts = (
        feature_df[FEATURE_STATUS_COLUMN].value_counts(dropna=False).sort_index()
        if FEATURE_STATUS_COLUMN in feature_df.columns
        else pd.Series(dtype="int64")
    )
    if status_counts.empty:
        print("- none")
    else:
        for status, count in status_counts.items():
            print(f"- {status}: {count}")

    print("extracted feature columns:")
    for column in DISCHARGE_FEATURE_COLUMNS:
        print(f"- {column}")

    print(f"missing feature ratio: {missing_feature_ratio(feature_df):.6f}")


def main() -> None:
    """Run raw discharge feature extraction."""
    args = parse_args()
    try:
        limit = parse_limit(args.limit, args.full)
        analysis_summary_df = load_summary(args.summary)
        feature_df = build_discharge_feature_table(
            analysis_summary_df=analysis_summary_df,
            raw_data_root=args.raw_root,
            limit=limit,
        )
        merged_df = merge_discharge_features(analysis_summary_df, feature_df)

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        feature_df.to_csv(output_path, index=False)

        merged_output_path = Path(args.merged_output)
        merged_output_path.parent.mkdir(parents=True, exist_ok=True)
        merged_df.to_csv(merged_output_path, index=False)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Kaggle battery discharge feature build failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print_summary(feature_df, merged_df)


if __name__ == "__main__":
    main()
