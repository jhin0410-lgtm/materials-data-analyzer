"""CLI for a focused review queue from existing NASA PCoE audit artifacts."""
from __future__ import annotations

import argparse
from pathlib import Path

from platform_core.battery_intelligence.nasa_review_queue import (
    audit_nasa_focused_review_queue,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m materials_data_analyzer.nasa_review_queue_cli",
        description=(
            "Create a deterministic, non-causal review queue from an existing "
            "NASA PCoE protocol audit without reimporting data or refitting models."
        ),
    )
    parser.add_argument("--analysis-output", required=True, type=Path)
    return parser


def _ids(summary: dict[str, object], field: str) -> str:
    values = summary.get(field, [])
    if not isinstance(values, list):
        return ""
    return ",".join(str(value) for value in values)


def main() -> None:
    args = build_parser().parse_args()
    result = audit_nasa_focused_review_queue(
        analysis_output=args.analysis_output,
    )
    summary = result["summary"]
    print(f"analysis_output: {args.analysis_output}")
    print(f"review_status: {summary['review_status']}")
    print(
        "predictive_evidence_level: "
        f"{summary['predictive_evidence_level']}"
    )
    print(
        "unevaluated_battery_count: "
        f"{summary['unevaluated_battery_count']}"
    )
    print(
        "disproportionate_error_influence_battery_count: "
        f"{summary['disproportionate_error_influence_battery_count']}"
    )
    print(
        "influence_with_source_quality_count: "
        f"{summary['influence_with_source_quality_count']}"
    )
    print(
        "influence_with_trajectory_continuity_count: "
        f"{summary['influence_with_trajectory_continuity_count']}"
    )
    print(
        "influence_without_structural_or_coverage_count: "
        f"{summary['influence_without_structural_or_coverage_count']}"
    )
    print(
        "structural_or_coverage_without_influence_count: "
        f"{summary['structural_or_coverage_without_influence_count']}"
    )
    print(
        "unevaluated_battery_ids: "
        f"{_ids(summary, 'unevaluated_battery_ids')}"
    )
    print(
        "source_quality_plus_influence_battery_ids: "
        f"{_ids(summary, 'source_quality_plus_influence_battery_ids')}"
    )
    print(
        "trajectory_continuity_plus_influence_battery_ids: "
        f"{_ids(summary, 'trajectory_continuity_plus_influence_battery_ids')}"
    )
    print(
        "influence_without_structural_or_coverage_battery_ids: "
        f"{_ids(summary, 'influence_without_structural_or_coverage_battery_ids')}"
    )
    for name, path in result["outputs"].items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
