"""Build a Kaggle NASA battery discharge cycle summary from metadata.csv."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loaders.kaggle_battery_metadata_loader import (  # noqa: E402
    build_analysis_ready_summary,
    build_battery_quality_summary,
    build_discharge_cycle_summary,
    load_kaggle_battery_metadata,
    save_kaggle_battery_summary,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Build a discharge-only cycle summary from Kaggle NASA battery "
            "cleaned_dataset metadata.csv."
        )
    )
    parser.add_argument("--metadata", required=True, help="Path to metadata.csv.")
    parser.add_argument("--output", required=True, help="Output processed CSV path.")
    parser.add_argument(
        "--analysis-output",
        default="data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv",
        help="Output CSV path for analyzer-ready normal-quality rows.",
    )
    parser.add_argument(
        "--quality-output",
        default="data/processed/kaggle_nasa_battery_quality_summary.csv",
        help="Output CSV path for battery-level quality summary.",
    )
    parser.add_argument(
        "--reference-method",
        choices=("first_valid", "first_n_median", "max_observed"),
        default="first_n_median",
        help="Reference capacity method for derived retention values.",
    )
    parser.add_argument(
        "--reference-window",
        type=int,
        default=5,
        help="Initial valid capacity count for first_n_median.",
    )
    return parser.parse_args()


def print_summary(
    full_output_path: Path,
    analysis_output_path: Path,
    quality_output_path: Path,
    full_summary_df,
    analysis_ready_df,
    quality_summary_df,
    reference_method: str,
    reference_window: int,
) -> None:
    """Print a concise build summary."""
    print(f"full output path: {full_output_path}")
    print(f"analysis-ready output path: {analysis_output_path}")
    print(f"quality summary output path: {quality_output_path}")
    print(f"reference method: {reference_method}")
    print(f"reference window: {reference_window}")
    print(f"full row count: {len(full_summary_df)}")
    print(f"analysis-ready row count: {len(analysis_ready_df)}")
    print(f"removed row count: {len(full_summary_df) - len(analysis_ready_df)}")

    print("battery_id row count:")
    battery_counts = full_summary_df["battery_id"].value_counts().sort_index()
    for battery_id, count in battery_counts.items():
        print(f"- {battery_id}: {count}")

    retention = full_summary_df["capacity_retention_percent"]
    print(
        "capacity_retention_percent min/max: "
        f"{retention.min(skipna=True)} / {retention.max(skipna=True)}"
    )

    print("retention_quality_flag value counts:")
    flag_counts = (
        full_summary_df["retention_quality_flag"]
        .value_counts(dropna=False)
        .sort_index()
    )
    for value, count in flag_counts.items():
        print(f"- {value}: {count}")

    print("battery_quality_flag counts:")
    battery_quality_counts = (
        quality_summary_df["battery_quality_flag"]
        .value_counts(dropna=False)
        .sort_index()
    )
    for value, count in battery_quality_counts.items():
        print(f"- {value}: {count}")

    print("failed counts in analysis-ready data:")
    failed_counts = analysis_ready_df["failed"].value_counts(dropna=False).sort_index()
    for value, count in failed_counts.items():
        print(f"- {value}: {count}")


def main() -> None:
    """Build and save the discharge cycle summary."""
    args = parse_args()
    try:
        metadata_df = load_kaggle_battery_metadata(args.metadata)
        summary_df = build_discharge_cycle_summary(
            metadata_df,
            reference_capacity_method=args.reference_method,
            reference_window=args.reference_window,
        )
        analysis_ready_df = build_analysis_ready_summary(summary_df)
        quality_summary_df = build_battery_quality_summary(summary_df)
        full_output_path = save_kaggle_battery_summary(summary_df, args.output)
        analysis_output_path = save_kaggle_battery_summary(
            analysis_ready_df,
            args.analysis_output,
        )
        quality_output_path = Path(args.quality_output)
        quality_output_path.parent.mkdir(parents=True, exist_ok=True)
        quality_summary_df.to_csv(quality_output_path, index=False)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Kaggle battery summary build failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print_summary(
        full_output_path=full_output_path,
        analysis_output_path=analysis_output_path,
        quality_output_path=quality_output_path,
        full_summary_df=summary_df,
        analysis_ready_df=analysis_ready_df,
        quality_summary_df=quality_summary_df,
        reference_method=args.reference_method,
        reference_window=args.reference_window,
    )


if __name__ == "__main__":
    main()
