"""Installed command for Battery Degradation Intelligence v1."""

from __future__ import annotations

import argparse
from pathlib import Path

from platform_core.battery_intelligence import (
    BatteryIntelligenceConfig,
    audit_battery_influence_run,
    audit_battery_intelligence_run,
    run_battery_intelligence,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-battery-intelligence",
        description=(
            "Run leakage-safe battery degradation diagnostics, strong origin-only "
            "baseline comparison, error-structure analysis, optional admitted raw-"
            "signal features, uncertainty, extrapolation checks, target/reference "
            "comparability auditing, battery-level influence triage, and a bounded "
            "scientific closeout."
        ),
    )
    parser.add_argument("--cycle-summary", required=True, type=Path)
    parser.add_argument("--raw-signal", type=Path)
    parser.add_argument(
        "--raw-signal-provenance",
        type=Path,
        help=(
            "JSON sidecar declaring source identity, checksum, units, license/terms, "
            "and battery/cycle mapping. Raw signals are not predictive inputs unless "
            "the admission gate passes."
        ),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--group-column", default="battery_id")
    parser.add_argument("--cycle-column", default="cycle_index")
    parser.add_argument("--target-column", default="capacity_retention_percent")
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--lags", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--rolling-window", type=int, default=5)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--ridge-alpha", type=float, default=1.0)
    parser.add_argument("--conformal-coverage", type=float, default=0.90)
    parser.add_argument("--minimum-trajectory-points", type=int, default=12)
    parser.add_argument("--knee-min-segment", type=int, default=5)
    parser.add_argument("--knee-bootstrap-samples", type=int, default=200)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _top_ids(summary: dict, model: str) -> str:
    records = summary["top_absolute_error_contributors"].get(model, [])
    return ",".join(str(next(iter(record.values()))) for record in records)


def main() -> None:
    args = build_parser().parse_args()
    config = BatteryIntelligenceConfig(
        group_column=args.group_column,
        cycle_column=args.cycle_column,
        target_column=args.target_column,
        horizon=args.horizon,
        lags=tuple(sorted(set(args.lags))),
        rolling_window=args.rolling_window,
        n_splits=args.n_splits,
        ridge_alpha=args.ridge_alpha,
        conformal_coverage=args.conformal_coverage,
        minimum_trajectory_points=args.minimum_trajectory_points,
        knee_min_segment=args.knee_min_segment,
        knee_bootstrap_samples=args.knee_bootstrap_samples,
        random_seed=args.random_seed,
    )
    manifest = run_battery_intelligence(
        cycle_summary_path=args.cycle_summary,
        raw_signal_path=args.raw_signal,
        raw_signal_provenance_path=args.raw_signal_provenance,
        output_dir=args.output,
        config=config,
        overwrite=args.overwrite,
    )
    audit = audit_battery_intelligence_run(args.output)
    triage = audit_battery_influence_run(args.output)
    summary = manifest["validation_summary"]
    closeout = manifest["scientific_closeout"]
    audit_summary = audit["summary"]
    triage_summary = triage["summary"]
    print(f"output: {args.output}")
    print(f"evidence_level: {closeout['evidence_level']}")
    print(f"best_baseline: {summary['best_baseline_name']}")
    print(f"best_baseline_mae: {summary['best_baseline_metrics']['mae']:.6f}")
    print(f"ridge_mae: {summary['ridge_metrics']['mae']:.6f}")
    print(
        "ridge_improvement_vs_best_baseline: "
        f"{summary['ridge_improvement_percent_vs_best_baseline']:.6f}%"
    )
    print(f"persistence_mae: {summary['persistence_metrics']['mae']:.6f}")
    print(f"ood_prediction_fraction: {summary['ood_prediction_fraction']:.6f}")
    admission = manifest.get("raw_signal_admission")
    if admission is not None:
        print(f"raw_signal_admission: {admission['status']}")
    print(
        "pooled_cross_battery_interpretation: "
        f"{audit_summary['pooled_cross_battery_interpretation']}"
    )
    print(
        "pooled_error_stability_status: "
        f"{audit_summary['pooled_error_stability_status']}"
    )
    print(
        "source_protocol_review_battery_count: "
        f"{triage_summary['source_protocol_review_battery_count']}"
    )
    print(
        "persistence_top_error_batteries: "
        f"{_top_ids(triage_summary, 'persistence')}"
    )
    print(f"ridge_top_error_batteries: {_top_ids(triage_summary, 'ridge')}")


if __name__ == "__main__":
    main()
