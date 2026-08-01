"""Post-hoc target-integrity and pooled-error comparability diagnostics.

The audit never filters batteries, clips targets, changes reference capacities,
interpolates gaps, or feeds diagnostic labels back into forecasting.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .common import BatteryIntelligenceConfig, canonical_json, file_sha256

_REFERENCE_TOLERANCE_PERCENT = 1e-6
_FIRST_TARGET_TOLERANCE_PERCENT = 5.0
_LARGE_TARGET_STEP_PERCENT = 20.0
_TOP_THREE_ERROR_SHARE_THRESHOLD = 0.50
_MEAN_MEDIAN_ERROR_RATIO_THRESHOLD = 5.0
_CONDITION_COLUMNS = (
    "ambient_temperature_c",
    "current_target",
    "discharge_duration_s",
    "voltage_min_v",
    "voltage_max_v",
    "temperature_min_c",
    "temperature_max_c",
    "temperature_span_c",
)


def _target_integrity(
    cycle_summary: pd.DataFrame,
    forecast_table: pd.DataFrame,
    config: BatteryIntelligenceConfig,
) -> pd.DataFrame:
    condition_columns = [
        column
        for column in _CONDITION_COLUMNS
        if column in forecast_table.columns
        and pd.api.types.is_numeric_dtype(forecast_table[column])
    ]
    condition_profiles: pd.DataFrame | None = None
    if condition_columns:
        condition_profiles = (
            forecast_table.groupby(config.group_column, sort=True)[condition_columns]
            .median()
            .add_prefix("median_observed_")
            .reset_index()
        )

    rows: list[dict[str, Any]] = []
    for battery_id, group in cycle_summary.groupby(config.group_column, sort=True):
        ordered = group.sort_values(config.cycle_column, kind="mergesort")
        cycles = ordered[config.cycle_column].to_numpy(dtype=float)
        targets = ordered[config.target_column].to_numpy(dtype=float)
        cycle_steps = np.diff(cycles)
        target_steps = np.diff(targets)
        outside = (targets < config.plausibility_min) | (
            targets > config.plausibility_max
        )

        reference_unique_count: int | None = None
        invalid_reference_count: int | None = None
        reconstruction_error: float | None = None
        if {
            "reference_capacity_ah",
            "discharge_capacity_ah",
        }.issubset(ordered.columns):
            reference = pd.to_numeric(
                ordered["reference_capacity_ah"], errors="coerce"
            ).to_numpy(dtype=float)
            discharge = pd.to_numeric(
                ordered["discharge_capacity_ah"], errors="coerce"
            ).to_numpy(dtype=float)
            finite_reference = reference[np.isfinite(reference)]
            reference_unique_count = int(np.unique(finite_reference).size)
            invalid_reference_count = int(
                np.sum(~np.isfinite(reference) | (reference <= 0))
            )
            valid = (
                np.isfinite(reference)
                & (reference > 0)
                & np.isfinite(discharge)
                & np.isfinite(targets)
            )
            if np.any(valid):
                reconstructed = 100.0 * discharge[valid] / reference[valid]
                reconstruction_error = float(
                    np.max(np.abs(reconstructed - targets[valid]))
                )

        first_deviation = float(abs(targets[0] - 100.0))
        maximum_target_step = (
            float(np.max(np.abs(target_steps))) if len(target_steps) else 0.0
        )
        reference_flag = bool(
            (reference_unique_count is not None and reference_unique_count > 1)
            or (invalid_reference_count is not None and invalid_reference_count > 0)
            or (
                reconstruction_error is not None
                and reconstruction_error > _REFERENCE_TOLERANCE_PERCENT
            )
        )
        target_flag = bool(
            np.any(outside)
            or reference_flag
            or first_deviation > _FIRST_TARGET_TOLERANCE_PERCENT
            or maximum_target_step > _LARGE_TARGET_STEP_PERCENT
        )
        rows.append(
            {
                config.group_column: battery_id,
                "observed_cycle_count": int(len(ordered)),
                "first_cycle": float(cycles[0]),
                "last_cycle": float(cycles[-1]),
                "cycle_gap_count": int(np.sum(cycle_steps > 1)),
                "maximum_cycle_step": (
                    float(np.max(cycle_steps)) if len(cycle_steps) else 0.0
                ),
                "first_target_percent": float(targets[0]),
                "last_target_percent": float(targets[-1]),
                "minimum_target_percent": float(np.min(targets)),
                "median_target_percent": float(np.median(targets)),
                "maximum_target_percent": float(np.max(targets)),
                "target_range_percent": float(np.max(targets) - np.min(targets)),
                "outside_plausibility_count": int(np.sum(outside)),
                "outside_plausibility_fraction": float(np.mean(outside)),
                "first_target_deviation_from_100_percent": first_deviation,
                "maximum_absolute_adjacent_target_change_percent": maximum_target_step,
                "median_absolute_adjacent_target_change_percent": (
                    float(np.median(np.abs(target_steps)))
                    if len(target_steps)
                    else 0.0
                ),
                "reference_capacity_unique_count": reference_unique_count,
                "invalid_reference_capacity_count": invalid_reference_count,
                "target_reconstruction_max_absolute_error_percent": reconstruction_error,
                "reference_consistency_flag": reference_flag,
                "target_comparability_flag": target_flag,
                "interpretation_boundary": (
                    "Diagnostic only; no row or battery was excluded, clipped, "
                    "renormalized, interpolated, or assigned to a protocol cohort."
                ),
            }
        )

    result = pd.DataFrame(rows)
    if condition_profiles is not None:
        result = result.merge(
            condition_profiles,
            on=config.group_column,
            how="left",
            validate="one_to_one",
        )
    return result.sort_values(config.group_column, kind="mergesort").reset_index(
        drop=True
    )


def _model_names(predictions: pd.DataFrame) -> list[str]:
    return sorted(
        {
            column.removesuffix("_prediction")
            for column in predictions.columns
            if column.endswith("_prediction")
            and column
            not in {"prediction_interval_low", "prediction_interval_high"}
        }
    )


def _error_concentration(
    predictions: pd.DataFrame, config: BatteryIntelligenceConfig
) -> pd.DataFrame:
    required = {config.group_column, "actual"}
    missing = sorted(required - set(predictions.columns))
    if missing:
        raise ValueError(
            "validation predictions missing required audit columns: "
            + ", ".join(missing)
        )
    models = _model_names(predictions)
    if not models:
        raise ValueError("validation predictions contain no model prediction columns")

    enriched = predictions.copy()
    totals: dict[str, float] = {}
    for model in models:
        errors = np.abs(
            enriched["actual"] - enriched[f"{model}_prediction"]
        )
        enriched[f"{model}_absolute_error"] = errors
        totals[model] = float(errors.sum())

    rows: list[dict[str, Any]] = []
    for battery_id, group in enriched.groupby(config.group_column, sort=True):
        row: dict[str, Any] = {
            config.group_column: battery_id,
            "prediction_count": int(len(group)),
            "actual_minimum": float(group["actual"].min()),
            "actual_median": float(group["actual"].median()),
            "actual_maximum": float(group["actual"].max()),
        }
        for model in models:
            errors = group[f"{model}_absolute_error"].to_numpy(dtype=float)
            error_sum = float(np.sum(errors))
            row[f"{model}_absolute_error_sum"] = error_sum
            row[f"{model}_mae"] = float(np.mean(errors))
            row[f"{model}_median_absolute_error"] = float(np.median(errors))
            row[f"{model}_maximum_absolute_error"] = float(np.max(errors))
            row[f"{model}_total_absolute_error_fraction"] = float(
                error_sum / max(totals[model], np.finfo(float).eps)
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        config.group_column, kind="mergesort"
    ).reset_index(drop=True)


def _top_share(frame: pd.DataFrame, model: str, count: int) -> float | None:
    column = f"{model}_absolute_error_sum"
    if column not in frame.columns or frame.empty:
        return None
    values = frame[column].to_numpy(dtype=float)
    total = float(np.sum(values))
    if total <= 0:
        return 0.0
    return float(np.sum(np.sort(values)[::-1][:count]) / total)


def _mean_median_ratio(predictions: pd.DataFrame, model: str) -> float | None:
    column = f"{model}_prediction"
    if column not in predictions.columns:
        return None
    errors = np.abs(
        predictions["actual"].to_numpy(dtype=float)
        - predictions[column].to_numpy(dtype=float)
    )
    return float(
        np.mean(errors) / max(float(np.median(errors)), np.finfo(float).eps)
    )


def build_target_comparability_audit(
    *,
    cycle_summary: pd.DataFrame,
    forecast_table: pd.DataFrame,
    predictions: pd.DataFrame,
    config: BatteryIntelligenceConfig,
) -> dict[str, Any]:
    """Build target/reference and pooled-error diagnostics without filtering."""
    target = _target_integrity(cycle_summary, forecast_table, config)
    errors = _error_concentration(predictions, config)

    persistence_top_three = _top_share(errors, "persistence", 3)
    ridge_top_three = _top_share(errors, "ridge", 3)
    persistence_ratio = _mean_median_ratio(predictions, "persistence")
    ridge_ratio = _mean_median_ratio(predictions, "ridge")
    unstable = bool(
        (
            persistence_top_three is not None
            and persistence_top_three > _TOP_THREE_ERROR_SHARE_THRESHOLD
        )
        or (
            ridge_top_three is not None
            and ridge_top_three > _TOP_THREE_ERROR_SHARE_THRESHOLD
        )
        or (
            persistence_ratio is not None
            and persistence_ratio > _MEAN_MEDIAN_ERROR_RATIO_THRESHOLD
        )
        or (
            ridge_ratio is not None
            and ridge_ratio > _MEAN_MEDIAN_ERROR_RATIO_THRESHOLD
        )
    )
    target_flag_count = int(target["target_comparability_flag"].sum())
    interpretation = (
        "diagnostic_only"
        if target_flag_count or unstable
        else "pooled_result_not_flagged_by_this_audit"
    )

    condition_ranges: dict[str, dict[str, float | None]] = {}
    for column in target.columns:
        if not column.startswith("median_observed_"):
            continue
        values = target[column].dropna().to_numpy(dtype=float)
        condition_ranges[column.removeprefix("median_observed_")] = {
            "battery_median_minimum": float(np.min(values)) if len(values) else None,
            "battery_median_maximum": float(np.max(values)) if len(values) else None,
        }

    summary = {
        "schema_version": "1.0",
        "battery_count": int(len(target)),
        "prediction_battery_count": int(errors[config.group_column].nunique()),
        "target_comparability_flag_battery_count": target_flag_count,
        "reference_consistency_flag_battery_count": int(
            target["reference_consistency_flag"].sum()
        ),
        "cycle_gap_battery_count": int((target["cycle_gap_count"] > 0).sum()),
        "large_adjacent_target_jump_battery_count": int(
            (
                target["maximum_absolute_adjacent_target_change_percent"]
                > _LARGE_TARGET_STEP_PERCENT
            ).sum()
        ),
        "outside_plausibility_target_count": int(
            target["outside_plausibility_count"].sum()
        ),
        "persistence_top_one_absolute_error_fraction": _top_share(
            errors, "persistence", 1
        ),
        "persistence_top_three_absolute_error_fraction": persistence_top_three,
        "ridge_top_one_absolute_error_fraction": _top_share(errors, "ridge", 1),
        "ridge_top_three_absolute_error_fraction": ridge_top_three,
        "persistence_mean_to_median_absolute_error_ratio": persistence_ratio,
        "ridge_mean_to_median_absolute_error_ratio": ridge_ratio,
        "pooled_error_stability_status": (
            "unstable_heavy_tail_or_concentrated" if unstable else "not_flagged"
        ),
        "pooled_cross_battery_interpretation": interpretation,
        "observed_condition_ranges": condition_ranges,
        "thresholds": {
            "first_target_deviation_percent": _FIRST_TARGET_TOLERANCE_PERCENT,
            "large_adjacent_target_change_percent": _LARGE_TARGET_STEP_PERCENT,
            "top_three_absolute_error_fraction": _TOP_THREE_ERROR_SHARE_THRESHOLD,
            "mean_to_median_absolute_error_ratio": _MEAN_MEDIAN_ERROR_RATIO_THRESHOLD,
            "reference_reconstruction_tolerance_percent": _REFERENCE_TOLERANCE_PERCENT,
        },
        "scientific_boundary": (
            "The audit identifies target/reference anomalies and error concentration. "
            "It does not infer protocol identity, degradation mechanism, causality, "
            "or justify removing flagged batteries."
        ),
    }
    return {
        "target_integrity_by_battery": target,
        "error_concentration_by_battery": errors,
        "summary": summary,
    }


def _markdown(summary: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Battery Target and Cross-Battery Comparability Audit",
            "",
            "This is a post-hoc diagnostic. No target, row, or battery was filtered, clipped, renormalized, interpolated, or assigned to an inferred protocol cohort.",
            "",
            "## Result",
            "",
            f"- Pooled cross-battery interpretation: `{summary['pooled_cross_battery_interpretation']}`",
            f"- Pooled error stability: `{summary['pooled_error_stability_status']}`",
            f"- Batteries with target-comparability flags: `{summary['target_comparability_flag_battery_count']}` / `{summary['battery_count']}`",
            f"- Batteries with cycle gaps: `{summary['cycle_gap_battery_count']}`",
            f"- Targets outside configured plausibility range: `{summary['outside_plausibility_target_count']}`",
            f"- Persistence top-three absolute-error share: `{summary['persistence_top_three_absolute_error_fraction']}`",
            f"- Ridge top-three absolute-error share: `{summary['ridge_top_three_absolute_error_fraction']}`",
            f"- Persistence mean/median absolute-error ratio: `{summary['persistence_mean_to_median_absolute_error_ratio']}`",
            f"- Ridge mean/median absolute-error ratio: `{summary['ridge_mean_to_median_absolute_error_ratio']}`",
            "",
            "## Interpretation Boundary",
            "",
            str(summary["scientific_boundary"]),
            "",
        ]
    )


def _update_closeout(output: Path, summary: Mapping[str, Any]) -> None:
    reports = output / "reports"
    json_path = reports / "scientific_closeout.json"
    markdown_path = reports / "scientific_closeout.md"
    diagnostic_only = summary["pooled_cross_battery_interpretation"] == "diagnostic_only"
    limitation = (
        "Pooled cross-battery metrics are diagnostic only when target/reference "
        "anomalies or battery-level heavy-tail error concentration are present; "
        "flagged batteries require source- and protocol-aware review rather than "
        "silent exclusion."
    )

    if json_path.is_file():
        closeout = json.loads(json_path.read_text(encoding="utf-8"))
        closeout.setdefault("component_statuses", {})[
            "target_and_cross_battery_comparability"
        ] = {
            "status": "Diagnostic" if diagnostic_only else "Supported",
            "scope": (
                "Target/reference integrity, cycle gaps, observed-condition ranges, "
                "and battery-level error concentration were audited without filtering."
            ),
        }
        closeout.setdefault("strongest_evidence", {})[
            "target_comparability_audit"
        ] = dict(summary)
        limitations = closeout.setdefault("limitations", [])
        if diagnostic_only and limitation not in limitations:
            limitations.append(limitation)
            closeout["primary_limitation"] = (
                limitation + " " + str(closeout.get("primary_limitation", ""))
            ).strip()
        json_path.write_text(canonical_json(closeout), encoding="utf-8")

    if markdown_path.is_file():
        start = "<!-- target-comparability-audit:start -->"
        end = "<!-- target-comparability-audit:end -->"
        current = markdown_path.read_text(encoding="utf-8")
        prefix = current.split(start, 1)[0].rstrip() if start in current else current.rstrip()
        section = (
            f"{start}\n\n## Target and Cross-Battery Comparability\n\n"
            + "\n".join(_markdown(summary).splitlines()[6:])
            + f"\n{end}\n"
        )
        markdown_path.write_text(prefix + "\n\n" + section, encoding="utf-8")


def _load_config(path: Path) -> BatteryIntelligenceConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = dict(payload["config"])
    values["lags"] = tuple(int(value) for value in values.get("lags", (1, 2, 3)))
    return BatteryIntelligenceConfig(**values)


def audit_battery_intelligence_run(output_dir: str | Path) -> dict[str, Any]:
    """Audit an existing Battery Intelligence output directory in place."""
    output = Path(output_dir)
    tables = output / "tables"
    reports = output / "reports"
    required = {
        "cycle": tables / "validated_cycle_summary.csv",
        "forecast": tables / "forecast_feature_table.csv",
        "predictions": tables / "validation_predictions.csv",
        "config": output / "config_snapshot.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "battery run is missing required audit artifacts: " + ", ".join(missing)
        )

    audit = build_target_comparability_audit(
        cycle_summary=pd.read_csv(required["cycle"]),
        forecast_table=pd.read_csv(required["forecast"]),
        predictions=pd.read_csv(required["predictions"]),
        config=_load_config(required["config"]),
    )
    target_path = tables / "target_integrity_by_battery.csv"
    error_path = tables / "error_concentration_by_battery.csv"
    report_path = reports / "target_comparability_audit.json"
    markdown_path = reports / "target_comparability_audit.md"
    audit["target_integrity_by_battery"].to_csv(target_path, index=False)
    audit["error_concentration_by_battery"].to_csv(error_path, index=False)
    report_path.write_text(canonical_json(audit["summary"]), encoding="utf-8")
    markdown_path.write_text(_markdown(audit["summary"]), encoding="utf-8")
    _update_closeout(output, audit["summary"])

    manifest_path = output / "run_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["target_comparability_audit"] = audit["summary"]
        paths = [
            target_path,
            error_path,
            report_path,
            markdown_path,
            reports / "scientific_closeout.json",
            reports / "scientific_closeout.md",
        ]
        relative_paths = [path.relative_to(output).as_posix() for path in paths]
        manifest["artifact_paths"] = sorted(
            set(manifest.get("artifact_paths", [])) | set(relative_paths)
        )
        checksums = dict(manifest.get("artifact_checksums", {}))
        for path, relative in zip(paths, relative_paths, strict=True):
            if path.is_file():
                checksums[relative] = file_sha256(path)
        manifest["artifact_checksums"] = checksums
        manifest_path.write_text(canonical_json(manifest), encoding="utf-8")

    return {
        "summary": audit["summary"],
        "outputs": {
            "target_integrity_by_battery": str(target_path),
            "error_concentration_by_battery": str(error_path),
            "target_comparability_audit": str(report_path),
            "target_comparability_markdown": str(markdown_path),
        },
    }
