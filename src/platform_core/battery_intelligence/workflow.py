"""End-to-end Battery Degradation Intelligence workflow."""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import Any, Mapping
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from .common import (
    ARTIFACT_KIND,
    SCHEMA_VERSION,
    BatteryIntelligenceConfig,
    canonical_json,
    file_sha256,
    validate_cycle_summary,
    validate_raw_signal,
)
from .degradation import analyze_trajectories
from .signals import extract_signal_features
from .forecast_table import build_forecast_table
from .forecast_validation import evaluate_grouped_forecast
from .closeout import scientific_closeout


def _write_closeout_markdown(path: Path, closeout: Mapping[str, Any]) -> None:
    strongest = closeout["strongest_evidence"]
    lines = [
        "# Battery Degradation Intelligence Scientific Closeout",
        "",
        f"**Evidence level:** {closeout['evidence_level']}",
        "",
        "## Result",
        "",
        str(closeout["result"]),
        "",
        "## Strongest Evidence",
        "",
        f"- Battery-disjoint validation: `{strongest['battery_disjoint_validation']}`",
        f"- Evaluated batteries: `{strongest['evaluated_battery_count']}`",
        f"- Ridge improvement versus persistence: `{strongest['ridge_improvement_percent_vs_persistence']:.3f}%`",
        f"- Improved battery fraction: `{strongest['improved_battery_fraction']:.3f}`",
        f"- Observed conformal coverage: `{strongest['conformal_observed_coverage']}`",
        f"- Knee candidates: `{strongest['knee_candidate_count']}`",
        "",
        "## Primary Limitation",
        "",
        str(closeout["primary_limitation"]),
        "",
        "## Evidence That Would Change the Conclusion",
        "",
    ]
    lines.extend(
        f"- {item}" for item in closeout["evidence_that_would_change_the_conclusion"]
    )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in closeout["limitations"])
    lines.extend(
        [
            "",
            "## Suitability",
            "",
            "- Exploration: yes",
            "- Engineering decision: no",
            "- Scientific claim: no",
            "- Production control: no",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _plot_trajectories(
    cycle_summary: pd.DataFrame,
    diagnostics: pd.DataFrame,
    config: BatteryIntelligenceConfig,
    output_path: Path,
) -> None:
    figure, axis = plt.subplots(figsize=(10, 6))
    knee_lookup = diagnostics.set_index(config.group_column)["knee_cycle"].to_dict()
    for battery_id, group in cycle_summary.groupby(config.group_column, sort=True):
        ordered = group.sort_values(config.cycle_column, kind="mergesort")
        axis.plot(
            ordered[config.cycle_column],
            ordered[config.target_column],
            linewidth=1.0,
            alpha=0.65,
        )
        knee = knee_lookup.get(battery_id)
        if knee is not None and pd.notna(knee):
            nearest = ordered.iloc[
                int(
                    np.argmin(
                        np.abs(
                            ordered[config.cycle_column].to_numpy(dtype=float)
                            - float(knee)
                        )
                    )
                )
            ]
            axis.scatter(
                [nearest[config.cycle_column]],
                [nearest[config.target_column]],
                s=16,
            )
    axis.set_xlabel(config.cycle_column)
    axis.set_ylabel(config.target_column)
    axis.set_title("Battery capacity-retention trajectories and knee candidates")
    axis.grid(True, alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _plot_predictions(predictions: pd.DataFrame, output_path: Path) -> None:
    figure, axis = plt.subplots(figsize=(7, 7))
    axis.scatter(
        predictions["actual"],
        predictions["ridge_prediction"],
        s=12,
        alpha=0.6,
    )
    lower = float(
        min(predictions["actual"].min(), predictions["ridge_prediction"].min())
    )
    upper = float(
        max(predictions["actual"].max(), predictions["ridge_prediction"].max())
    )
    axis.plot([lower, upper], [lower, upper], linestyle="--", linewidth=1)
    axis.set_xlabel("Actual future retention (%)")
    axis.set_ylabel("Ridge prediction (%)")
    axis.set_title("Battery-disjoint forecast predictions")
    axis.grid(True, alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def run_battery_intelligence(
    *,
    cycle_summary_path: str | Path,
    output_dir: str | Path,
    raw_signal_path: str | Path | None = None,
    config: BatteryIntelligenceConfig | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    config = config or BatteryIntelligenceConfig()
    config.validate()
    cycle_path = Path(cycle_summary_path)
    raw_path = Path(raw_signal_path) if raw_signal_path is not None else None
    output = Path(output_dir)
    if not cycle_path.is_file():
        raise FileNotFoundError(f"cycle summary file not found: {cycle_path}")
    if raw_path is not None and not raw_path.is_file():
        raise FileNotFoundError(f"raw signal file not found: {raw_path}")
    if output.exists() and not output.is_dir():
        raise FileExistsError(f"output path is not a directory: {output}")
    if output.exists() and any(output.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"output directory is non-empty: {output}; "
                "choose another path or pass overwrite=True"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    tables = output / "tables"
    figures = output / "figures"
    reports = output / "reports"
    for directory in (tables, figures, reports):
        directory.mkdir(parents=True, exist_ok=True)

    cycle_source = pd.read_csv(cycle_path)
    cycle_summary, cycle_flags, readiness = validate_cycle_summary(
        cycle_source, config
    )
    signal_features: pd.DataFrame | None = None
    signal_flags = pd.DataFrame()
    raw_readiness: dict[str, Any] | None = None
    if raw_path is not None:
        raw_source = pd.read_csv(raw_path)
        validated_raw, raw_validation_flags, raw_readiness = validate_raw_signal(
            raw_source
        )
        signal_features, extraction_flags = extract_signal_features(validated_raw)
        signal_flags = pd.concat(
            [raw_validation_flags, extraction_flags],
            ignore_index=True,
            sort=False,
        ).drop_duplicates()
        signal_features.to_csv(tables / "signal_features.csv", index=False)

    trajectory_diagnostics, trajectory_points = analyze_trajectories(
        cycle_summary, config
    )
    forecast_table, feature_columns, forecast_metadata = build_forecast_table(
        cycle_summary, config, signal_features
    )
    predictions, per_group, validation = evaluate_grouped_forecast(
        forecast_table, feature_columns, config
    )

    all_flags = pd.concat([cycle_flags, signal_flags], ignore_index=True, sort=False)
    closeout = scientific_closeout(
        readiness={
            "cycle_summary": readiness,
            "raw_signal": raw_readiness,
            "forecast_table": forecast_metadata,
            "quality_flag_count": int(len(all_flags)),
        },
        trajectory_diagnostics=trajectory_diagnostics,
        validation=validation,
        raw_signal_available=raw_path is not None,
    )

    cycle_summary.to_csv(tables / "validated_cycle_summary.csv", index=False)
    all_flags.to_csv(tables / "quality_flags.csv", index=False)
    trajectory_diagnostics.to_csv(
        tables / "trajectory_diagnostics.csv", index=False
    )
    trajectory_points.to_csv(tables / "trajectory_points.csv", index=False)
    forecast_table.to_csv(tables / "forecast_feature_table.csv", index=False)
    predictions.to_csv(tables / "validation_predictions.csv", index=False)
    per_group.to_csv(tables / "validation_by_battery.csv", index=False)
    (reports / "validation_summary.json").write_text(
        canonical_json(validation), encoding="utf-8"
    )
    (reports / "scientific_closeout.json").write_text(
        canonical_json(closeout), encoding="utf-8"
    )
    _write_closeout_markdown(reports / "scientific_closeout.md", closeout)
    _plot_trajectories(
        cycle_summary,
        trajectory_diagnostics,
        config,
        figures / "capacity_trajectories.png",
    )
    _plot_predictions(predictions, figures / "forecast_predictions.png")

    config_payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "config": config.to_dict(),
    }
    (output / "config_snapshot.json").write_text(
        canonical_json(config_payload), encoding="utf-8"
    )

    artifact_paths = sorted(
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "cycle_summary_source": {
            "path": str(cycle_path),
            "sha256": file_sha256(cycle_path),
        },
        "raw_signal_source": (
            {"path": str(raw_path), "sha256": file_sha256(raw_path)}
            if raw_path is not None
            else None
        ),
        "config": config.to_dict(),
        "readiness": readiness,
        "forecast_metadata": forecast_metadata,
        "validation_summary": validation["summary"],
        "scientific_closeout": closeout,
        "artifact_paths": artifact_paths,
        "artifact_checksums": {
            relative: file_sha256(output / relative) for relative in artifact_paths
        },
        "software_validation": "generated",
        "scientific_validation": closeout["evidence_level"],
        "limitations": closeout["limitations"],
    }
    (output / "run_manifest.json").write_text(
        canonical_json(manifest), encoding="utf-8"
    )
    return manifest
