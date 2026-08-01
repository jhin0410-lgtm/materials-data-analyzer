"""End-to-end Battery Degradation Intelligence workflow."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .closeout import scientific_closeout
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
from .error_diagnostics import build_error_diagnostics
from .forecast_table import build_forecast_table
from .forecast_validation import evaluate_grouped_forecast
from .raw_signal_admission import audit_raw_signal_admission
from .signals import extract_signal_features


def _write_closeout_markdown(path: Path, closeout: Mapping[str, Any]) -> None:
    strongest = closeout["strongest_evidence"]
    lines = [
        "# Battery Degradation Intelligence Scientific Closeout",
        "",
        f"**Primary claim:** `{closeout['primary_claim']}`",
        f"**Primary evidence level:** {closeout['evidence_level']}",
        "",
        "## Result",
        "",
        str(closeout["result"]),
        "",
        "## Component Statuses",
        "",
        "| Component | Status | Scope |",
        "|---|---|---|",
    ]
    for name, item in closeout["component_statuses"].items():
        lines.append(
            f"| `{name}` | **{item['status']}** | {item['scope']} |"
        )
    lines.extend(
        [
            "",
            "## Strongest Evidence",
            "",
            f"- Battery-disjoint validation: `{strongest['battery_disjoint_validation']}`",
            f"- Evaluated batteries: `{strongest['evaluated_battery_count']}`",
            f"- Strongest origin-only baseline: `{strongest['best_baseline_name']}`",
            f"- Best baseline MAE: `{strongest['best_baseline_mae']:.6f}`",
            f"- Ridge MAE: `{strongest['ridge_mae']:.6f}`",
            f"- Ridge improvement versus best baseline: `{strongest['ridge_improvement_percent_vs_best_baseline']:.3f}%`",
            f"- Improved-battery fraction versus best baseline: `{strongest['improved_vs_best_baseline_battery_fraction']:.3f}`",
            f"- Observed conformal coverage: `{strongest['conformal_observed_coverage']}`",
            f"- Knee candidates: `{strongest['knee_candidate_count']}`",
            f"- Weak knee candidates: `{strongest['weak_knee_candidate_count']}`",
            "",
            "## Primary Limitation",
            "",
            str(closeout["primary_limitation"]),
            "",
            "## Evidence That Would Change the Conclusion",
            "",
        ]
    )
    lines.extend(
        f"- {item}" for item in closeout["evidence_that_would_change_the_conclusion"]
    )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in closeout["limitations"])
    lines.extend(["", "## Suitability", ""])
    for name, value in closeout["suitability"].items():
        lines.append(f"- {name.replace('_', ' ').title()}: {'yes' if value else 'no'}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _plot_trajectories(
    cycle_summary: pd.DataFrame,
    diagnostics: pd.DataFrame,
    config: BatteryIntelligenceConfig,
    output_path: Path,
) -> None:
    figure, axis = plt.subplots(figsize=(10, 6))
    knee_lookup = diagnostics.set_index(config.group_column)["knee_cycle"].to_dict()
    status_lookup = diagnostics.set_index(config.group_column)["status"].to_dict()
    for battery_id, group in cycle_summary.groupby(config.group_column, sort=True):
        ordered = group.sort_values(config.cycle_column, kind="mergesort")
        axis.plot(
            ordered[config.cycle_column],
            ordered[config.target_column],
            linewidth=1.0,
            alpha=0.65,
        )
        knee = knee_lookup.get(battery_id)
        if status_lookup.get(battery_id) == "candidate" and knee is not None and pd.notna(knee):
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
    axis.set_title("Battery capacity-retention trajectories and supported knee candidates")
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
    axis.set_title("Battery-disjoint Ridge predictions")
    axis.grid(True, alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _plot_model_comparison(model_comparison: pd.DataFrame, output_path: Path) -> None:
    ordered = model_comparison.sort_values("mae", ascending=True, kind="mergesort")
    figure, axis = plt.subplots(figsize=(9, 5))
    axis.barh(ordered["model"], ordered["mae"])
    axis.set_xlabel("Mean absolute error")
    axis.set_ylabel("Model")
    axis.set_title("Origin-only baseline and Ridge comparison")
    axis.grid(True, axis="x", alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _plot_error_delta(row_level: pd.DataFrame, output_path: Path) -> None:
    values = row_level["ridge_minus_best_baseline_absolute_error"].to_numpy(dtype=float)
    figure, axis = plt.subplots(figsize=(9, 5))
    axis.hist(values, bins=40)
    axis.axvline(0.0, linestyle="--", linewidth=1)
    axis.set_xlabel("Ridge absolute error minus best-baseline absolute error")
    axis.set_ylabel("Prediction count")
    axis.set_title("Where Ridge wins or loses against the strongest row-level baseline")
    axis.grid(True, alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _write_diagnostic_tables(
    diagnostics: Mapping[str, Any], tables: Path, reports: Path
) -> None:
    file_map = {
        "row_level": "forecast_error_diagnostics.csv",
        "model_comparison": "model_comparison.csv",
        "by_battery": "error_by_battery.csv",
        "by_lifecycle_segment": "error_by_lifecycle_segment.csv",
        "by_knee_phase": "error_by_knee_phase.csv",
        "by_domain_status": "error_by_domain_status.csv",
        "by_degradation_rate": "error_by_degradation_rate.csv",
        "by_trajectory_regime": "error_by_trajectory_regime.csv",
        "by_interval_width": "error_by_interval_width.csv",
        "battery_profiles": "battery_error_profiles.csv",
        "success_failure_profiles": "ridge_success_failure_profiles.csv",
        "high_error_predictions": "high_error_predictions.csv",
    }
    for key, filename in file_map.items():
        diagnostics[key].to_csv(tables / filename, index=False)
    (reports / "error_diagnostics_summary.json").write_text(
        canonical_json(diagnostics["summary"]), encoding="utf-8"
    )


def run_battery_intelligence(
    *,
    cycle_summary_path: str | Path,
    output_dir: str | Path,
    raw_signal_path: str | Path | None = None,
    raw_signal_provenance_path: str | Path | None = None,
    config: BatteryIntelligenceConfig | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    config = config or BatteryIntelligenceConfig()
    config.validate()
    cycle_path = Path(cycle_summary_path)
    raw_path = Path(raw_signal_path) if raw_signal_path is not None else None
    provenance_path = (
        Path(raw_signal_provenance_path)
        if raw_signal_provenance_path is not None
        else None
    )
    output = Path(output_dir)
    if not cycle_path.is_file():
        raise FileNotFoundError(f"cycle summary file not found: {cycle_path}")
    if raw_path is not None and not raw_path.is_file():
        raise FileNotFoundError(f"raw signal file not found: {raw_path}")
    if provenance_path is not None and raw_path is None:
        raise ValueError("raw signal provenance requires --raw-signal")
    if provenance_path is not None and not provenance_path.is_file():
        raise FileNotFoundError(
            f"raw signal provenance file not found: {provenance_path}"
        )
    if output.exists() and not output.is_dir():
        raise FileExistsError(f"output path is not a directory: {output}")
    if output.exists() and any(output.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"output directory is non-empty: {output}; choose another path or pass overwrite=True"
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
    raw_admission: dict[str, Any] | None = None
    raw_provenance: Mapping[str, Any] | None = None
    validated_raw: pd.DataFrame | None = None
    if provenance_path is not None:
        loaded = json.loads(provenance_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, Mapping):
            raise ValueError("raw signal provenance must be a JSON object")
        raw_provenance = loaded
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
        raw_admission = audit_raw_signal_admission(
            cycle_summary=cycle_summary,
            raw_signal=validated_raw,
            provenance=raw_provenance,
            raw_sha256=file_sha256(raw_path),
            group_column=config.group_column,
            cycle_column=config.cycle_column,
        )
        (reports / "raw_signal_admission.json").write_text(
            canonical_json(raw_admission), encoding="utf-8"
        )

    trajectory_diagnostics, trajectory_points = analyze_trajectories(
        cycle_summary, config
    )

    capacity_table, capacity_features, capacity_metadata = build_forecast_table(
        cycle_summary, config, None
    )
    capacity_predictions, capacity_per_group, capacity_validation = (
        evaluate_grouped_forecast(capacity_table, capacity_features, config)
    )
    forecast_table = capacity_table
    feature_columns = capacity_features
    forecast_metadata = capacity_metadata
    predictions = capacity_predictions
    per_group = capacity_per_group
    validation = capacity_validation
    signal_feature_comparison: dict[str, Any] | None = None

    if signal_features is not None and raw_admission and raw_admission[
        "admitted_for_predictive_comparison"
    ]:
        enriched_table, enriched_features, enriched_metadata = build_forecast_table(
            cycle_summary, config, signal_features
        )
        enriched_predictions, enriched_per_group, enriched_validation = (
            evaluate_grouped_forecast(enriched_table, enriched_features, config)
        )
        capacity_ridge_mae = float(
            capacity_validation["summary"]["ridge_metrics"]["mae"]
        )
        enriched_ridge_mae = float(
            enriched_validation["summary"]["ridge_metrics"]["mae"]
        )
        signal_feature_comparison = {
            "capacity_only_ridge_mae": capacity_ridge_mae,
            "signal_enriched_ridge_mae": enriched_ridge_mae,
            "improvement_percent": float(
                100.0
                * (capacity_ridge_mae - enriched_ridge_mae)
                / max(capacity_ridge_mae, np.finfo(float).eps)
            ),
            "capacity_only_feature_count": len(capacity_features),
            "signal_enriched_feature_count": len(enriched_features),
            "same_grouped_split_policy": True,
        }
        capacity_table.to_csv(
            tables / "forecast_feature_table_capacity_only.csv", index=False
        )
        capacity_predictions.to_csv(
            tables / "validation_predictions_capacity_only.csv", index=False
        )
        capacity_per_group.to_csv(
            tables / "validation_by_battery_capacity_only.csv", index=False
        )
        (reports / "validation_summary_capacity_only.json").write_text(
            canonical_json(capacity_validation), encoding="utf-8"
        )
        forecast_table = enriched_table
        feature_columns = enriched_features
        forecast_metadata = enriched_metadata
        predictions = enriched_predictions
        per_group = enriched_per_group
        validation = enriched_validation

    error_diagnostics = build_error_diagnostics(
        predictions=predictions,
        forecast_table=forecast_table,
        per_group=per_group,
        trajectory_diagnostics=trajectory_diagnostics,
        validation=validation,
        config=config,
    )
    _write_diagnostic_tables(error_diagnostics, tables, reports)

    all_flags = pd.concat([cycle_flags, signal_flags], ignore_index=True, sort=False)
    closeout = scientific_closeout(
        readiness={
            "cycle_summary": readiness,
            "raw_signal": raw_readiness,
            "raw_signal_admission": raw_admission,
            "forecast_table": forecast_metadata,
            "quality_flag_count": int(len(all_flags)),
        },
        trajectory_diagnostics=trajectory_diagnostics,
        validation=validation,
        raw_signal_available=raw_path is not None,
        error_diagnostics=error_diagnostics["summary"],
        raw_signal_admission=raw_admission,
        signal_feature_comparison=signal_feature_comparison,
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
    if signal_feature_comparison is not None:
        (reports / "signal_feature_comparison.json").write_text(
            canonical_json(signal_feature_comparison), encoding="utf-8"
        )
    _write_closeout_markdown(reports / "scientific_closeout.md", closeout)
    _plot_trajectories(
        cycle_summary,
        trajectory_diagnostics,
        config,
        figures / "capacity_trajectories.png",
    )
    _plot_predictions(predictions, figures / "forecast_predictions.png")
    _plot_model_comparison(
        error_diagnostics["model_comparison"],
        figures / "model_mae_comparison.png",
    )
    _plot_error_delta(
        error_diagnostics["row_level"],
        figures / "ridge_vs_best_baseline_error_delta.png",
    )

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
        "raw_signal_provenance_source": (
            {"path": str(provenance_path), "sha256": file_sha256(provenance_path)}
            if provenance_path is not None
            else None
        ),
        "raw_signal_admission": raw_admission,
        "signal_feature_comparison": signal_feature_comparison,
        "config": config.to_dict(),
        "readiness": readiness,
        "forecast_metadata": forecast_metadata,
        "validation_summary": validation["summary"],
        "error_diagnostics_summary": error_diagnostics["summary"],
        "scientific_closeout": closeout,
        "artifact_paths": artifact_paths,
        "artifact_checksums": {
            relative: file_sha256(output / relative) for relative in artifact_paths
        },
        "runtime_execution": "supported",
        "scientific_validation": closeout["evidence_level"],
        "limitations": closeout["limitations"],
    }
    (output / "run_manifest.json").write_text(
        canonical_json(manifest), encoding="utf-8"
    )
    return manifest
