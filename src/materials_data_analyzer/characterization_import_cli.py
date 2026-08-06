"""Installed command for validated characterization-bundle consumption."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from materials_data_analyzer.characterization_use_policy import (
    USE_LEVELS,
    consume_characterization_bundle_for_use,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-characterization-import",
        description=(
            "Validate and consume a versioned materials-characterization-analyzer "
            "handoff bundle, enforce its downstream-use boundary, preserve provenance, "
            "and build sample-level integrated and audit outputs."
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
    parser.add_argument(
        "--requested-use",
        choices=USE_LEVELS,
        default="descriptive",
        help=(
            "Strongest intended downstream use. Legacy bundles without an explicit "
            "policy are accepted only for descriptive use."
        ),
    )
    parser.add_argument(
        "--split-group-field",
        help=(
            "Independent grouping field used for association analysis or model splitting. "
            "Required for association, predictive, causal, or engineering use and must "
            "match the producer policy."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = consume_characterization_bundle_for_use(
            args.bundle_manifest,
            args.output,
            process_table_path=args.process_table,
            requested_use=args.requested_use,
            split_group_field=args.split_group_field,
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
