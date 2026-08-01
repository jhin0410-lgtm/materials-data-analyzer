"""CLI module for protocol-aware audit of an existing official NASA run."""
from __future__ import annotations

import argparse
from pathlib import Path

from platform_core.battery_intelligence.nasa_protocol_audit import (
    audit_nasa_protocol_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m materials_data_analyzer.nasa_protocol_audit_cli",
        description=(
            "Audit existing official NASA PCoE import and Battery Intelligence "
            "artifacts without reimporting data or refitting models."
        ),
    )
    parser.add_argument("--import-output", required=True, type=Path)
    parser.add_argument("--analysis-output", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = audit_nasa_protocol_run(
        import_output=args.import_output,
        analysis_output=args.analysis_output,
    )
    summary = result["summary"]
    print(f"import_output: {args.import_output}")
    print(f"analysis_output: {args.analysis_output}")
    print(f"protocol_audit_status: {summary['protocol_audit_status']}")
    print(f"predictive_evidence_level: {summary['predictive_evidence_level']}")
    print(
        "reference_start_context_battery_count: "
        f"{summary['reference_start_context_battery_count']}"
    )
    print(
        "reference_context_only_battery_count: "
        f"{summary['reference_context_only_battery_count']}"
    )
    print(
        "source_quality_issue_battery_count: "
        f"{summary['source_quality_issue_battery_count']}"
    )
    print(
        "trajectory_continuity_issue_battery_count: "
        f"{summary['trajectory_continuity_issue_battery_count']}"
    )
    print(
        "structural_or_coverage_issue_battery_count: "
        f"{summary['structural_or_coverage_issue_battery_count']}"
    )
    print(
        "disproportionate_error_influence_battery_count: "
        f"{summary['disproportionate_error_influence_battery_count']}"
    )
    print(
        "ridge_improvement_vs_persistence_percent: "
        f"{summary['ridge_improvement_vs_persistence_percent']}"
    )
    print(
        "ridge_better_than_persistence_battery_count: "
        f"{summary['ridge_better_than_persistence_battery_count']}"
    )
    print(
        "signal_enriched_improvement_percent: "
        f"{summary['signal_enriched_improvement_percent']}"
    )
    print(
        "supported_temperature_stratum_count: "
        f"{summary['supported_temperature_stratum_count']}"
    )
    for name, path in result["outputs"].items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
