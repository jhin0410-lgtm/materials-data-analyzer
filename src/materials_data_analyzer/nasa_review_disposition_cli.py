"""CLI for reviewer-controlled NASA PCoE evidence dispositions."""
from __future__ import annotations

import argparse
from pathlib import Path

from platform_core.battery_intelligence.nasa_review_disposition import (
    finalize_nasa_review_disposition,
    initialize_nasa_review_disposition,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m materials_data_analyzer.nasa_review_disposition_cli",
        description=(
            "Initialize or validate human review dispositions over the exact current "
            "NASA PCoE evidence packets without refitting models, changing data, or "
            "assigning causal conclusions automatically."
        ),
    )
    parser.add_argument("--analysis-output", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--initialize", action="store_true")
    mode.add_argument("--finalize", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--disposition-input", type=Path)
    return parser


def _ids(summary: dict[str, object], field: str) -> str:
    values = summary.get(field, [])
    return ",".join(str(value) for value in values) if isinstance(values, list) else ""


def main() -> None:
    args = build_parser().parse_args()
    if args.initialize:
        if args.disposition_input is not None:
            raise SystemExit("--disposition-input is valid only with --finalize")
        result = initialize_nasa_review_disposition(
            analysis_output=args.analysis_output,
            overwrite=args.overwrite,
        )
        summary = result["summary"]
        print(f"analysis_output: {args.analysis_output}")
        print(f"worksheet_status: {summary['worksheet_status']}")
        print(f"battery_count: {summary['battery_count']}")
        print(f"priority_battery_count: {summary['priority_battery_count']}")
        print(f"source_evidence_sha256: {summary['source_evidence_sha256']}")
    else:
        if args.overwrite:
            raise SystemExit("--overwrite is valid only with --initialize")
        result = finalize_nasa_review_disposition(
            analysis_output=args.analysis_output,
            disposition_input=args.disposition_input,
        )
        summary = result["summary"]
        print(f"analysis_output: {args.analysis_output}")
        print(f"disposition_status: {summary['disposition_status']}")
        print(f"predictive_evidence_level: {summary['predictive_evidence_level']}")
        print(f"reviewed_battery_count: {summary['reviewed_battery_count']}")
        print(f"pending_battery_count: {summary['pending_battery_count']}")
        print(
            "pending_priority_battery_ids: "
            f"{_ids(summary, 'pending_priority_battery_ids')}"
        )
    for name, path in result["outputs"].items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
