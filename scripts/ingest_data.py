"""CLI for source-specific data ingestion probes.

This script prepares raw and processed files only. It does not automatically run
the analyzer; run `src/process_data.py` separately on any processed CSV.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from connectors.base import IngestionResult  # noqa: E402
from connectors.battery_archive_connector import BatteryArchiveConnector  # noqa: E402
from connectors.htem_connector import HTEMConnector  # noqa: E402
from connectors.kaggle_connector import KaggleConnector  # noqa: E402
from connectors.materials_project_connector import MaterialsProjectConnector  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Read ingestion CLI options."""
    parser = argparse.ArgumentParser(description="Probe external data sources.")
    parser.add_argument(
        "--source",
        choices=("materials_project", "kaggle", "htem", "battery_archive"),
        required=True,
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--dataset", help="Kaggle dataset slug, e.g. owner/name.")
    parser.add_argument(
        "--elements",
        nargs="*",
        default=None,
        help="Element symbols for HTEM or Materials Project probes.",
    )
    return parser.parse_args()


def build_connector(args: argparse.Namespace):
    """Create the connector selected by CLI arguments."""
    if args.source == "materials_project":
        return MaterialsProjectConnector(elements=args.elements)
    if args.source == "kaggle":
        if not args.dataset:
            raise ValueError("--dataset is required for --source kaggle")
        return KaggleConnector(dataset_slug=args.dataset)
    if args.source == "htem":
        return HTEMConnector(elements=args.elements)
    if args.source == "battery_archive":
        return BatteryArchiveConnector()
    raise ValueError(f"Unsupported source: {args.source}")


def print_result(result: IngestionResult) -> None:
    """Print a concise ingestion summary."""
    print(f"Source: {result.source_name}")
    print(f"Rows: {result.row_count}")
    print(f"Columns: {result.column_count}")
    print("Raw paths:")
    if result.raw_paths:
        for path in result.raw_paths:
            print(f"- {path}")
    else:
        print("- none")
    print("Processed paths:")
    if result.processed_paths:
        for path in result.processed_paths:
            print(f"- {path}")
    else:
        print("- none")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")


def main() -> None:
    """Run the requested ingestion probe."""
    args = parse_args()
    try:
        connector = build_connector(args)
        result = connector.fetch(limit=args.limit, full=args.full)
    except (RuntimeError, ValueError) as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print_result(result)


if __name__ == "__main__":
    main()
