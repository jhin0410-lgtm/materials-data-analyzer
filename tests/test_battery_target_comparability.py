from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from platform_core.battery_intelligence import (
    BatteryIntelligenceConfig,
    audit_battery_intelligence_run,
    build_target_comparability_audit,
)


def _audit_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cycle_rows = []
    forecast_rows = []
    prediction_rows = []
    for battery in range(4):
        battery_id = f"B{battery}"
        cycles = [1, 2, 3, 4, 5, 6]
        if battery == 3:
            cycles = [1, 2, 4, 5, 6, 7]
        targets = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0]
        if battery == 3:
            targets = [100.0, 99.0, 420.0, 96.0, 95.0, 94.0]
        for cycle, target in zip(cycles, targets, strict=True):
            reference = 2.0 if not (battery == 2 and cycle == 6) else 2.1
            discharge = reference * target / 100.0
            cycle_rows.append(
                {
                    "battery_id": battery_id,
                    "cycle_index": cycle,
                    "capacity_retention_percent": target,
                    "reference_capacity_ah": reference,
                    "discharge_capacity_ah": discharge,
                    "ambient_temperature_c": 25.0 + battery * 10.0,
                }
            )
        for origin in (1, 2, 3):
            forecast_rows.append(
                {
                    "battery_id": battery_id,
                    "origin_cycle": origin,
                    "target_cycle": origin + 2,
                    "future_target": 98.0 - origin,
                    "current_target": 100.0 - origin,
                }
            )
            actual = 98.0 - origin
            persistence_error = 1.0 if battery < 3 else 100.0
            ridge_error = 2.0 if battery < 3 else 150.0
            prediction_rows.append(
                {
                    "battery_id": battery_id,
                    "origin_cycle": origin,
                    "target_cycle": origin + 2,
                    "actual": actual,
                    "persistence_prediction": actual + persistence_error,
                    "ridge_prediction": actual + ridge_error,
                }
            )
    return (
        pd.DataFrame(cycle_rows),
        pd.DataFrame(forecast_rows),
        pd.DataFrame(prediction_rows),
    )


def _clean_frames(
    battery_count: int = 4,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cycles = []
    forecast = []
    predictions = []
    for battery in range(battery_count):
        battery_id = f"C{battery}"
        for cycle in range(1, 7):
            target = 101.0 - cycle
            cycles.append(
                {
                    "battery_id": battery_id,
                    "cycle_index": cycle,
                    "capacity_retention_percent": target,
                    "reference_capacity_ah": 2.0,
                    "discharge_capacity_ah": 2.0 * target / 100.0,
                    "ambient_temperature_c": 25.0 + battery,
                }
            )
        for origin in (1, 2, 3):
            actual = 99.0 - origin
            forecast.append(
                {
                    "battery_id": battery_id,
                    "origin_cycle": origin,
                    "target_cycle": origin + 2,
                    "future_target": actual,
                    "current_target": actual + 2.0,
                }
            )
            predictions.append(
                {
                    "battery_id": battery_id,
                    "actual": actual,
                    "persistence_prediction": actual + 1.0,
                    "ridge_prediction": actual + 1.0,
                }
            )
    return pd.DataFrame(cycles), pd.DataFrame(forecast), pd.DataFrame(predictions)


def test_target_comparability_audit_detects_flags_without_filtering():
    cycles, forecast, predictions = _audit_frames()
    config = BatteryIntelligenceConfig(n_splits=2, knee_bootstrap_samples=0)
    audit = build_target_comparability_audit(
        cycle_summary=cycles,
        forecast_table=forecast,
        predictions=predictions,
        config=config,
    )
    target = audit["target_integrity_by_battery"].set_index("battery_id")
    summary = audit["summary"]

    assert len(target) == 4
    assert int(target.loc["B3", "outside_plausibility_count"]) == 1
    assert int(target.loc["B3", "cycle_gap_count"]) == 1
    assert bool(target.loc["B2", "reference_consistency_flag"])
    assert target.loc["B0", "median_observed_ambient_temperature_c"] == 25.0
    assert summary["pooled_cross_battery_interpretation"] == "diagnostic_only"
    assert summary["component_status"] == "Diagnostic"
    assert summary["pooled_error_stability_status"] == (
        "unstable_heavy_tail_or_concentrated"
    )
    assert summary["persistence_top_one_absolute_error_fraction"] > 0.9
    assert len(audit["error_concentration_by_battery"]) == 4


def test_balanced_small_cohort_is_not_automatically_concentrated():
    cycles, forecast, predictions = _clean_frames(battery_count=4)
    audit = build_target_comparability_audit(
        cycle_summary=cycles,
        forecast_table=forecast,
        predictions=predictions,
        config=BatteryIntelligenceConfig(n_splits=2, knee_bootstrap_samples=0),
    )
    summary = audit["summary"]

    assert summary["persistence_top_three_absolute_error_fraction"] == 0.75
    assert summary["persistence_top_three_concentration_excess_ratio"] == 1.0
    assert summary["pooled_error_stability_status"] == "not_flagged"
    assert summary["pooled_cross_battery_interpretation"] == (
        "pooled_result_not_flagged_by_this_audit"
    )
    assert summary["component_status"] == "Supported"


def test_reference_only_fields_are_audited_and_conditions_use_cycle_summary():
    cycles, forecast, predictions = _clean_frames()
    cycles = cycles.drop(columns=["discharge_capacity_ah"])
    cycles.loc[
        (cycles["battery_id"] == "C0") & (cycles["cycle_index"] == 6),
        "reference_capacity_ah",
    ] = -1.0
    forecast = forecast.drop(columns=["current_target"])
    audit = build_target_comparability_audit(
        cycle_summary=cycles,
        forecast_table=forecast,
        predictions=predictions,
        config=BatteryIntelligenceConfig(n_splits=2, knee_bootstrap_samples=0),
    )
    target = audit["target_integrity_by_battery"].set_index("battery_id")
    summary = audit["summary"]

    assert bool(target.loc["C0", "reference_consistency_flag"])
    assert int(target.loc["C0", "invalid_reference_capacity_count"]) == 1
    assert target.loc["C3", "median_observed_ambient_temperature_c"] == 28.0
    assert summary["dimension_availability"]["reference_capacity"] is True
    assert (
        summary["dimension_availability"]["reference_target_reconstruction"]
        is False
    )
    assert summary["dimension_availability"]["observed_condition_columns"] == [
        "ambient_temperature_c"
    ]


def test_missing_reference_and_condition_dimensions_remain_inconclusive():
    cycles, forecast, predictions = _clean_frames()
    cycles = cycles[
        ["battery_id", "cycle_index", "capacity_retention_percent"]
    ]
    forecast = forecast[
        ["battery_id", "origin_cycle", "target_cycle", "future_target"]
    ]
    audit = build_target_comparability_audit(
        cycle_summary=cycles,
        forecast_table=forecast,
        predictions=predictions,
        config=BatteryIntelligenceConfig(n_splits=2, knee_bootstrap_samples=0),
    )
    summary = audit["summary"]

    assert summary["pooled_error_stability_status"] == "not_flagged"
    assert summary["pooled_cross_battery_interpretation"] == (
        "not_flagged_but_partial"
    )
    assert summary["component_status"] == "Inconclusive"
    assert summary["dimension_availability"]["reference_capacity"] is False
    assert summary["dimension_availability"]["observed_condition_columns"] == []


def test_existing_run_audit_writes_artifacts_and_synchronizes_manifest(
    tmp_path: Path,
):
    cycles, forecast, predictions = _audit_frames()
    output = tmp_path / "run"
    tables = output / "tables"
    reports = output / "reports"
    tables.mkdir(parents=True)
    reports.mkdir(parents=True)

    cycles.to_csv(tables / "validated_cycle_summary.csv", index=False)
    forecast.to_csv(tables / "forecast_feature_table.csv", index=False)
    predictions.to_csv(tables / "validation_predictions.csv", index=False)
    config = BatteryIntelligenceConfig(n_splits=2, knee_bootstrap_samples=0)
    (output / "config_snapshot.json").write_text(
        json.dumps({"config": config.to_dict()}), encoding="utf-8"
    )
    original_closeout = {
        "evidence_level": "Unsupported",
        "component_statuses": {},
        "strongest_evidence": {},
        "limitations": [],
        "primary_limitation": "Original limitation.",
    }
    (reports / "scientific_closeout.json").write_text(
        json.dumps(original_closeout), encoding="utf-8"
    )
    (reports / "scientific_closeout.md").write_text(
        "# Scientific Closeout\n", encoding="utf-8"
    )
    (output / "run_manifest.json").write_text(
        json.dumps(
            {
                "artifact_paths": [],
                "artifact_checksums": {},
                "scientific_closeout": original_closeout,
                "scientific_validation": "Unsupported",
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )

    result = audit_battery_intelligence_run(output)

    assert result["summary"]["pooled_cross_battery_interpretation"] == (
        "diagnostic_only"
    )
    assert (tables / "target_integrity_by_battery.csv").is_file()
    assert (tables / "error_concentration_by_battery.csv").is_file()
    assert (reports / "target_comparability_audit.json").is_file()
    assert (reports / "target_comparability_audit.md").is_file()

    closeout = json.loads(
        (reports / "scientific_closeout.json").read_text(encoding="utf-8")
    )
    assert (
        closeout["component_statuses"][
            "target_and_cross_battery_comparability"
        ]["status"]
        == "Diagnostic"
    )
    assert "target_comparability_audit" in closeout["strongest_evidence"]

    manifest = json.loads(
        (output / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert "target_comparability_audit" in manifest
    assert "reports/target_comparability_audit.json" in manifest["artifact_paths"]
    assert manifest["scientific_closeout"] == closeout
    assert manifest["limitations"] == closeout["limitations"]
    assert manifest["scientific_validation"] == closeout["evidence_level"]
