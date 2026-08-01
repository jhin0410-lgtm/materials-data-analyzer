"""Installed command for post-hoc Battery Intelligence comparability audits."""
from __future__ import annotations

import argparse
from pathlib import Path

from platform_core.battery_intelligence.target_comparability import (
    audit_battery_intelligence_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-battery-result-audit",
        description=(
            "Audit an existing Battery Degradation Intelligence run for target and "
            "reference integrity, cycle gaps, observed-condition ranges, and "
            "battery-level error concentration without filtering or renormalizing data."
        ),
    )
    parser.add_argument("--run-output", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = audit_battery_intelligence_run(args.run_output)
    summary = result["summary"]
    print(f"run_output: {args.run_output}")
    print(
        "pooled_cross_battery_interpretation: "
        f"{summary['pooled_cross_battery_interpretation']}"
    )
    print(f"pooled_error_stability_status: {summary['pooled_error_stability_status']}")
    print(
        "target_comparability_flag_battery_count: "
        f"{summary['target_comparability_flag_battery_count']}"
    )
    print(
        "persistence_top_three_absolute_error_fraction: "
        f"{summary['persistence_top_three_absolute_error_fraction']}"
    )
    print(
        "ridge_top_three_absolute_error_fraction: "
        f"{summary['ridge_top_three_absolute_error_fraction']}"
    )
    for name, path in result["outputs"].items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
