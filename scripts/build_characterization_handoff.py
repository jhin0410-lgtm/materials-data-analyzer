"""Build a validated process-characterization sample table."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loaders.characterization_features import (  # noqa: E402
    run_characterization_handoff,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate long-format characterization features, pivot only "
            "unambiguous definitions, and optionally outer-join them to a "
            "process table by sample_id."
        )
    )
    parser.add_argument(
        "--characterization",
        nargs="+",
        required=True,
        help="One or more characterization *_features_long.csv files.",
    )
    parser.add_argument(
        "--process-table",
        default=None,
        help=(
            "Optional process or experiment CSV with one explicit unique row "
            "per sample_id."
        ),
    )
    parser.add_argument("--output", required=True, help="Output directory.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the handoff workflow and report generated artifacts."""
    args = parse_args(argv)
    try:
        outputs = run_characterization_handoff(
            args.characterization,
            args.output,
            process_table_path=args.process_table,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Characterization handoff failed: {exc}", file=sys.stderr)
        return 1

    print("Characterization handoff completed.")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
