from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from platform_core.battery_intelligence import BatteryIntelligenceConfig
from platform_core.battery_intelligence.target_comparability import (
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
                    "ambient_temperature_c": 25.0 + battery * 10.0,
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
    assert summary["pooled_cross_battery_interpretation"] == "diagnostic_only"
    assert summary["pooled_error_stability_status"] == (
        "unstable_heavy_tail_or_concentrated"
    )
    assert summary["persistence_top_one_absolute_error_fraction"] > 0.9
    assert len(audit["error_concentration_by_battery"]) == 4


def test_existing_run_audit_writes_artifacts_and_updates_closeout(tmp_path: Path):
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
    (reports / "scientific_closeout.json").write_text(
        json.dumps(
            {
                "component_statuses": {},
                "strongest_evidence": {},
                "limitations": [],
                "primary_limitation": "Original limitation.",
            }
        ),
        encoding="utf-8",
    )
    (reports / "scientific_closeout.md").write_text(
        "# Scientific Closeout\n", encoding="utf-8"
    )
    (output / "run_manifest.json").write_text(
        json.dumps({"artifact_paths": [], "artifact_checksums": {}}),
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
