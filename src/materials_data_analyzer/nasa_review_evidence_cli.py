"""CLI for manifest-bound NASA PCoE battery review evidence."""
from __future__ import annotations

import argparse
from pathlib import Path

from platform_core.battery_intelligence.nasa_review_evidence import (
    audit_nasa_review_evidence,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m materials_data_analyzer.nasa_review_evidence_cli",
        description=(
            "Link an existing NASA PCoE focused review queue to exact source "
            "quarantines and validation-error rows without reimporting data, "
            "refitting models, filtering batteries, or assigning causality."
        ),
    )
    parser.add_argument("--import-output", required=True, type=Path)
    parser.add_argument("--analysis-output", required=True, type=Path)
    return parser


def _ids(summary: dict[str, object], field: str) -> str:
    values = summary.get(field, [])
    return ",".join(str(value) for value in values) if isinstance(values, list) else ""


def main() -> None:
    args = build_parser().parse_args()
    result = audit_nasa_review_evidence(
        import_output=args.import_output,
        analysis_output=args.analysis_output,
    )
    summary = result["summary"]
    print(f"import_output: {args.import_output}")
    print(f"analysis_output: {args.analysis_output}")
    print(f"review_evidence_status: {summary['review_status']}")
    print(f"predictive_evidence_level: {summary['predictive_evidence_level']}")
    print(f"packet_count: {summary['packet_count']}")
    print(f"priority_packet_count: {summary['priority_packet_count']}")
    print(
        "linked_excluded_operation_count: "
        f"{summary['linked_excluded_operation_count']}"
    )
    print(
        "linked_validation_prediction_count: "
        f"{summary['linked_validation_prediction_count']}"
    )
    print(
        "retrieval_receipt_verified: "
        f"{summary['retrieval_receipt_verified']}"
    )
    print(f"priority_battery_ids: {_ids(summary, 'priority_battery_ids')}")
    print(
        "source_quality_and_error_influence_battery_ids: "
        f"{_ids(summary, 'source_quality_and_error_influence_battery_ids')}"
    )
    print(
        "trajectory_continuity_and_error_influence_battery_ids: "
        f"{_ids(summary, 'trajectory_continuity_and_error_influence_battery_ids')}"
    )
    print(
        "model_or_unmodeled_protocol_battery_ids: "
        f"{_ids(summary, 'model_or_unmodeled_protocol_battery_ids')}"
    )
    for name, path in result["outputs"].items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
