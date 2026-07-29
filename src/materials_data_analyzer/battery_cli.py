"""Installed command for Battery Degradation Intelligence v1."""

from __future__ import annotations

import argparse
from pathlib import Path

from platform_core.battery_intelligence import (
    BatteryIntelligenceConfig,
    run_battery_intelligence,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mda-battery-intelligence",
        description=(
            "Run leakage-safe battery degradation diagnostics, optional raw-signal "
            "feature extraction, uncertainty calibration, extrapolation checks, "
            "and a bounded scientific closeout."
        ),
    )
    parser.add_argument("--cycle-summary", required=True, type=Path)
    parser.add_argument("--raw-signal", type=Path)
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
        output_dir=args.output,
        config=config,
        overwrite=args.overwrite,
    )
    summary = manifest["validation_summary"]
    closeout = manifest["scientific_closeout"]
    print(f"output: {args.output}")
    print(f"evidence_level: {closeout['evidence_level']}")
    print(f"ridge_mae: {summary['ridge_metrics']['mae']:.6f}")
    print(f"persistence_mae: {summary['persistence_metrics']['mae']:.6f}")
    print(f"ood_prediction_fraction: {summary['ood_prediction_fraction']:.6f}")


if __name__ == "__main__":
    main()
