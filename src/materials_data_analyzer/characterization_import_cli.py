"""Installed command for validated characterization-bundle consumption."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from loaders.characterization_bundle import consume_characterization_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-characterization-import",
        description=(
            "Validate and consume a versioned materials-characterization-analyzer "
            "handoff bundle, preserve provenance and scientific boundaries, and build "
            "sample-level long, wide, integrated, join-audit, report, and manifest outputs."
        ),
    )
    parser.add_argument(
        "--bundle-manifest",
        required=True,
        type=Path,
        help="Path to characterization_handoff_bundle.json from the producer repository.",
    )
    parser.add_argument(
        "--process-table",
        type=Path,
        help=(
            "Optional consumer-owned CSV with process variables. Its sample_id set and "
            "shared case/trace/material/system identity fields must match the producer "
            "bundle context exactly before integration."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Empty or not-yet-created consumer output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
