"""Derived diagnostics added to a NASA PCoE full-audit staging directory."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .common import BatteryIntelligenceConfig, canonical_json
from .forecast_table import source_cohort_id_from_location
from .forecast_validation import evaluate_grouped_forecast


def _json(path: Path) -> dict[str, Any]:
    import json

    loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON object required: {path}")
    return loaded


def _load_config(staging: Path) -> BatteryIntelligenceConfig:
    values = dict(_json(staging / "config_snapshot.json").get("config") or {})
    if "lags" in values:
        values["lags"] = tuple(int(value) for value in values["lags"])
    config = BatteryIntelligenceConfig(**values)
    config.validate()
    return config


def _attach_source_cohort(
    forecast: pd.DataFrame,
    validated_cycles: pd.DataFrame,
    group_column: str,
) -> pd.DataFrame:
    if "source_mat_file" not in validated_cycles.columns:
        raise ValueError("validated cycle summary lacks source_mat_file lineage")
    mapping = (
        validated_cycles[[group_column, "source_mat_file"]]
        .drop_duplicates()
        .assign(
            source_cohort_id=lambda frame: frame["source_mat_file"].map(
                source_cohort_id_from_location
            )
        )
    )
    counts = mapping.groupby(group_column)["source_cohort_id"].nunique(dropna=False)
    ambiguous = counts[counts != 1]
    if not ambiguous.empty:
        raise ValueError(
            "battery-to-source-cohort mapping is not one-to-one: "
            + ", ".join(str(value) for value in ambiguous.index)
        )
    return forecast.drop(columns=["source_cohort_id"], errors="ignore").merge(
        mapping[[group_column, "source_cohort_id"]],
        on=group_column,
        how="left",
        validate="many_to_one",
    )


def write_source_cohort_validation(staging: Path) -> dict[str, Any]:
    required = [
        staging / "config_snapshot.json",
        staging / "tables" / "forecast_feature_table.csv",
        staging / "tables" / "validated_cycle_summary.csv",
        staging / "reports" / "validation_summary.json",
    ]
    missing = [path.relative_to(staging).as_posix() for path in required if not path.is_file()]
    if missing:
        return {"status": "not_available", "missing_artifacts": missing}
    config = _load_config(staging)
    tables = staging / "tables"
    reports = staging / "reports"
    forecast = _attach_source_cohort(
        pd.read_csv(tables / "forecast_feature_table.csv"),
        pd.read_csv(tables / "validated_cycle_summary.csv"),
        config.group_column,
    )
    feature_columns = list(
        _json(reports / "validation_summary.json")["summary"]["feature_columns"]
    )
    predictions, by_battery, validation = evaluate_grouped_forecast(
        forecast,
        feature_columns,
        config,
        split_group_column="source_cohort_id",
        leave_one_group_out=True,
    )
    assignments = (
        forecast[[config.group_column, "source_cohort_id"]]
        .drop_duplicates()
        .sort_values(["source_cohort_id", config.group_column], kind="mergesort")
    )
    assignments.to_csv(tables / "source_cohort_assignments.csv", index=False)
    predictions.to_csv(tables / "validation_predictions_source_cohort.csv", index=False)
    by_battery.to_csv(tables / "validation_by_battery_source_cohort.csv", index=False)
    pd.DataFrame(validation["source_cohort_metrics"]).to_csv(
        tables / "validation_by_source_cohort.csv", index=False
    )
    (reports / "validation_summary_source_cohort.json").write_text(
        canonical_json(validation), encoding="utf-8"
    )
    return validation["summary"]


def _coverage_row(group: pd.DataFrame) -> pd.Series:
    available = group["interval_contains_actual"].notna()
    width = group["prediction_interval_high"] - group["prediction_interval_low"]
    return pd.Series(
        {
            "prediction_count": int(len(group)),
            "interval_prediction_count": int(available.sum()),
            "observed_coverage": (
                float(group.loc[available, "interval_contains_actual"].astype(bool).mean())
                if available.any()
                else math.nan
            ),
            "mean_interval_width": float(width[available].mean()) if available.any() else math.nan,
            "ridge_mae": float(np.mean(np.abs(group["actual"] - group["ridge_prediction"]))),
        }
    )


def write_coverage_tables(staging: Path) -> dict[str, Any]:
    prediction_path = staging / "tables" / "validation_predictions.csv"
    assignment_path = staging / "tables" / "source_cohort_assignments.csv"
    if not prediction_path.is_file() or not assignment_path.is_file():
        return {"status": "not_available"}
    predictions = pd.read_csv(prediction_path)
    if "source_cohort_id" not in predictions.columns:
        predictions = predictions.merge(
            pd.read_csv(assignment_path),
            on="battery_id",
            how="left",
            validate="many_to_one",
        )
    outputs: dict[str, list[dict[str, Any]]] = {}
    for column, filename in (
        ("battery_id", "conformal_coverage_by_battery.csv"),
        ("fold", "conformal_coverage_by_fold.csv"),
        ("source_cohort_id", "conformal_coverage_by_source_cohort.csv"),
    ):
        table = (
            predictions.groupby(column, sort=True, dropna=False)
            .apply(_coverage_row, include_groups=False)
            .reset_index()
        )
        table.to_csv(staging / "tables" / filename, index=False)
        outputs[column] = table.to_dict(orient="records")
    available = predictions["interval_contains_actual"].notna()
    battery = pd.DataFrame(outputs["battery_id"])
    summary = {
        "target_coverage": float(
            _json(staging / "config_snapshot.json")["config"]["conformal_coverage"]
        ),
        "pooled_coverage": float(
            predictions.loc[available, "interval_contains_actual"].astype(bool).mean()
        ),
        "battery_macro_coverage": float(battery["observed_coverage"].mean()),
        "worst_battery": min(
            outputs["battery_id"], key=lambda row: row["observed_coverage"]
        ),
        "scientific_boundary": (
            "Pooled interval coverage is insufficient to establish stable calibration across batteries or source cohorts."
        ),
    }
    (staging / "reports" / "conformal_coverage_diagnostics.json").write_text(
        canonical_json(summary), encoding="utf-8"
    )
    return summary


def write_target_reference_sensitivity(staging: Path) -> dict[str, Any]:
    path = staging / "tables" / "validated_cycle_summary.csv"
    if not path.is_file():
        return {"status": "not_available"}
    table = pd.read_csv(path)
    required = {"battery_id", "cycle_index", "discharge_capacity_ah"}
    if not required.issubset(table.columns):
        return {"status": "not_available", "missing_columns": sorted(required - set(table.columns))}
    ordered = table.sort_values(["battery_id", "cycle_index"], kind="mergesort").copy()
    first = ordered.groupby("battery_id", sort=True)["discharge_capacity_ah"].transform("first")
    ordered["retention_first_valid_discharge_percent"] = 100.0 * ordered["discharge_capacity_ah"] / first
    rated = ordered.get(
        "capacity_retention_percent", 100.0 * ordered["discharge_capacity_ah"] / 2.0
    )
    ordered["retention_rated_2ah_percent"] = rated
    ordered["retention_definition_delta_percent"] = (
        ordered["retention_first_valid_discharge_percent"] - rated
    )
    columns = [
        "battery_id",
        "cycle_index",
        "discharge_capacity_ah",
        "retention_rated_2ah_percent",
        "retention_first_valid_discharge_percent",
        "retention_definition_delta_percent",
    ]
    ordered[columns].to_csv(
        staging / "tables" / "target_reference_sensitivity.csv", index=False
    )
    (
        ordered.groupby("battery_id", sort=True)["retention_definition_delta_percent"]
        .agg(["count", "mean", "median", "min", "max"])
        .reset_index()
        .to_csv(staging / "tables" / "target_reference_sensitivity_by_battery.csv", index=False)
    )
    summary = {
        "status": "diagnostic",
        "rated_reference_ah": 2.0,
        "alternative_reference": "first valid discharge capacity within each battery",
        "row_count": int(len(ordered)),
        "battery_count": int(ordered["battery_id"].nunique()),
        "absolute_delta_median_percent": float(
            ordered["retention_definition_delta_percent"].abs().median()
        ),
        "absolute_delta_p95_percent": float(
            ordered["retention_definition_delta_percent"].abs().quantile(0.95)
        ),
        "authoritative_protocol_reference_status": "not_available",
        "scientific_boundary": (
            "This sensitivity compares normalization definitions only and does not identify an authoritative physical reference for each cohort."
        ),
    }
    (staging / "reports" / "target_reference_sensitivity.json").write_text(
        canonical_json(summary), encoding="utf-8"
    )
    return summary


def repair_staged_charge_semantics(staging: Path) -> dict[str, Any]:
    path = staging / "tables" / "signal_features.csv"
    if not path.is_file():
        return {"status": "not_available"}
    table = pd.read_csv(path)
    columns = [
        column
        for column in (
            "charge_duration_s",
            "charge_cc_duration_s",
            "charge_cv_duration_s",
            "charge_throughput_ah",
            "charge_energy_wh",
            "coulombic_efficiency",
            "energy_efficiency",
            "cv_fraction_of_charge_time",
        )
        if column in table.columns
    ]
    evidence = [
        column for column in ("charge_throughput_ah", "charge_energy_wh") if column in table.columns
    ]
    observed = table[evidence].notna().any(axis=1) if evidence else pd.Series(False, index=table.index)
    changed = 0
    for column in columns:
        mask = ~observed & table[column].eq(0)
        changed += int(mask.sum())
        table.loc[mask, column] = np.nan
    table["charge_signal_available"] = observed.astype(bool)
    table["charge_feature_status"] = np.where(
        observed, "observed", "not_observed_in_raw_signal"
    )
    table.to_csv(path, index=False)
    summary = {
        "status": "completed",
        "changed_cell_count": changed,
        "affected_row_count": int((~observed).sum()),
        "policy": "unobserved charge-derived values are missing, never physical zero",
        "model_results_recomputed": False,
        "note": (
            "The staged copy was corrected for review. Rerun the pipeline with remediated code to recompute model outputs."
        ),
    }
    (staging / "reports" / "charge_feature_semantics_remediation.json").write_text(
        canonical_json(summary), encoding="utf-8"
    )
    return summary


def augment_audit_diagnostics(staging: Path) -> dict[str, Any]:
    charge = repair_staged_charge_semantics(staging)
    cohort = write_source_cohort_validation(staging)
    coverage = write_coverage_tables(staging)
    target = write_target_reference_sensitivity(staging)
    return {
        "charge_feature_semantics": charge,
        "source_cohort_validation": cohort,
        "coverage_diagnostics": coverage,
        "target_reference_sensitivity": target,
    }
