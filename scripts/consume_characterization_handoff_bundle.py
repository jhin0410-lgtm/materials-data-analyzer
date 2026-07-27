"""Validate and consume a versioned characterization handoff bundle."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loaders.characterization_bundle import (  # noqa: E402
    consume_characterization_bundle,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle-manifest",
        required=True,
        help="Path to characterization_handoff_bundle.json from the producer repository.",
    )
    parser.add_argument(
        "--process-table",
        help=(
            "Optional consumer-owned CSV with process variables. Its sample_id set and "
            "shared case/trace/material/system identity columns must match the producer "
            "bundle context exactly before integration."
        ),
    )
    parser.add_argument("--output", required=True, help="Empty consumer output directory.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        outputs = consume_characterization_bundle(
            args.bundle_manifest,
            args.output,
            process_table_path=args.process_table,
        )
    except (
        FileNotFoundError,
        FileExistsError,
        ValueError,
        OSError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        print(
            f"Cross-repository characterization handoff failed: {exc}",
            file=sys.stderr,
        )
        return 1

    print("Cross-repository characterization handoff completed.")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
