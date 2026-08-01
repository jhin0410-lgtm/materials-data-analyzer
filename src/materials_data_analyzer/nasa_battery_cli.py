"""Installed CLI for the local NASA PCoE battery MATLAB importer."""
from __future__ import annotations

import argparse
from pathlib import Path

from platform_core.battery_intelligence import import_nasa_pcoe_battery
from platform_core.battery_intelligence.nasa_pcoe import (
    NASA_PCOE_SOURCE_IDENTIFIER,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-nasa-battery-import",
        description=(
            "Convert a local NASA PCoE battery .mat file, directory, or ZIP "
            "archive into canonical cycle-summary, raw-signal, provenance, "
            "inventory, protocol, warning, and manifest artifacts. This command "
            "performs no network access."
        ),
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help=(
            "Local .mat file, ZIP archive, or directory containing NASA PCoE "
            ".mat files."
        ),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--retrieval-receipt",
        type=Path,
        help=(
            "JSON receipt from scripts/download_nasa_pcoe_battery_dataset.ps1. "
            "For ZIP inputs, its archive SHA-256 is verified before provenance "
            "is marked retrieval-backed."
        ),
    )
    parser.add_argument(
        "--retrieved-at",
        help=(
            "Explicit source acquisition timestamp when no verified receipt is "
            "available. Omit rather than invent this value."
        ),
    )
    parser.add_argument(
        "--source-identifier",
        default=NASA_PCOE_SOURCE_IDENTIFIER,
        help="Stable landing-page or archive identifier recorded in provenance.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    manifest = import_nasa_pcoe_battery(
        input_path=args.input,
        output_dir=args.output,
        retrieval_receipt_path=args.retrieval_receipt,
        retrieved_at=args.retrieved_at,
        source_identifier=args.source_identifier,
        overwrite=args.overwrite,
    )
    print(f"output: {args.output}")
    print(f"batteries: {manifest['battery_count']}")
    print(f"discharge_cycles: {manifest['discharge_cycle_count']}")
    print(f"raw_points: {manifest['raw_point_count']}")
    print(
        "retrieval_receipt_verified: "
        f"{manifest['retrieval_receipt_verified']}"
    )
    target_reference = manifest.get("target_reference")
    if target_reference is not None:
        print(f"target_reference_method: {target_reference['method']}")
        print(f"rated_capacity_ah: {target_reference['rated_capacity_ah']}")
    for name, path in manifest["outputs"].items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
