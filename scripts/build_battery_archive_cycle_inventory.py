"""Build a Battery Archive cycle_data file inventory from local raw zip files."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from connectors.battery_archive_connector import (  # noqa: E402
    build_cycle_file_inventory,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Inventory Battery Archive *_cycle_data.csv files inside raw zip "
            "archives without extracting the zip files."
        )
    )
    parser.add_argument(
        "--raw-dir",
        required=True,
        help="Directory containing Battery Archive .zip files.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output CSV path for the cycle file inventory.",
    )
    return parser.parse_args()


def main() -> None:
    """Build and save the Battery Archive cycle file inventory."""
    args = parse_args()
    raw_dir = Path(args.raw_dir)
    output_path = Path(args.output)

    try:
        inventory_df = build_cycle_file_inventory(raw_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Battery Archive cycle inventory failed: {exc}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_df.to_csv(output_path, index=False)

    zip_count = len(sorted(raw_dir.glob("*.zip"), key=lambda path: path.name.casefold()))
    cycle_count = len(inventory_df)
    print(f"raw directory: {raw_dir}")
    print(f"output path: {output_path}")
    print(f"zip file count: {zip_count}")
    print(f"cycle_data file count: {cycle_count}")


if __name__ == "__main__":
    main()
