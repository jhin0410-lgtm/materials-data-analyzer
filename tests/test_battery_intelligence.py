from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from platform_core.battery_intelligence import (
    BatteryIntelligenceConfig,
    build_forecast_table,
    detect_knee_point,
    evaluate_grouped_forecast,
    extract_signal_features,
    run_battery_intelligence,
    validate_cycle_summary,
)


def _cycle_summary(batteries: int = 6, cycles: int = 40) -> pd.DataFrame:
    rows = []
    for battery in range(batteries):
        battery_id = f"B{battery:03d}"
        for cycle in range(1, cycles + 1):
            slope = 0.05 + 0.01 * battery
            acceleration = max(cycle - 22, 0) * (0.03 + 0.002 * battery)
            retention = 101.0 - slope * cycle - acceleration
            rows.append(
                {
                    "battery_id": battery_id,
                    "cycle_index": cycle,
                    "capacity_retention_percent": retention,
                    "ambient_temperature_c": 25.0 + battery,
                    "internal_resistance_ohm": 0.05 + 0.0005 * cycle,
                }
            )
    return pd.DataFrame(rows)


def test_cycle_summary_rejects_duplicate_battery_cycle():
    frame = _cycle_summary(batteries=2, cycles=12)
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate battery-cycle"):
        validate_cycle_summary(frame, BatteryIntelligenceConfig())


def test_signal_feature_integration_and_efficiency():
    raw = pd.DataFrame(
        {
            "battery_id": ["B1"] * 6,
            "cycle_index": [1] * 6,
            "step_type": ["charge_cc"] * 3 + ["discharge"] * 3,
            "elapsed_time_s": [0, 1800, 3600, 0, 1800, 3600],
            "voltage_v": [4.0, 4.0, 4.0, 3.5, 3.5, 3.5],
            "current_a": [1.0, 1.0, 1.0, -0.9, -0.9, -0.9],
            "temperature_c": [25.0, 26.0, 27.0, 27.0, 28.0, 29.0],
            "global_time_s": [0, 1800, 3600, 3601, 5401, 7201],
        }
    )
    features, flags = extract_signal_features(raw)
    row = features.iloc[0]
    assert row["charge_throughput_ah"] == pytest.approx(1.0)
    assert row["discharge_throughput_ah"] == pytest.approx(0.9)
    assert row["charge_energy_wh"] == pytest.approx(4.0)
    assert row["discharge_energy_wh"] == pytest.approx(3.15)
    assert row["coulombic_efficiency"] == pytest.approx(0.9)
    assert row["energy_efficiency"] == pytest.approx(3.15 / 4.0)
    assert row["temperature_rise_c"] == pytest.approx(4.0)
    assert row["resistance_transition_proxy_ohm"] == pytest.approx(0.5 / 1.9)
    assert "capacity_signal_unavailable" in set(flags["code"])


def test_signal_contract_supports_repeated_step_types_with_step_id():
    raw = pd.DataFrame(
        {
            "battery_id": ["B1"] * 4,
            "cycle_index": [1] * 4,
            "step_id": ["rest_before", "rest_before", "rest_after", "rest_after"],
            "step_type": ["rest"] * 4,
            "elapsed_time_s": [0, 10, 0, 20],
            "voltage_v": [4.1, 4.1, 3.8, 3.8],
            "current_a": [0.0, 0.0, 0.0, 0.0],
        }
    )
    features, flags = extract_signal_features(raw)
    row = features.iloc[0]
    assert row["signal_step_count"] == 2
    assert row["signal_duration_s"] == pytest.approx(30.0)
    assert pd.isna(row["resistance_transition_proxy_ohm"])
    assert "resistance_proxy_requires_global_time" in set(flags["code"])


def test_incremental_capacity_rejects_multiple_discharge_segments():
    raw = pd.DataFrame(
        {
            "battery_id": ["B1"] * 6,
            "cycle_index": [1] * 6,
            "step_id": ["d1", "d1", "d1", "d2", "d2", "d2"],
            "step_type": ["discharge"] * 6,
            "elapsed_time_s": [0, 1, 2, 0, 1, 2],
            "voltage_v": [4.2, 4.0, 3.8, 3.7, 3.5, 3.3],
            "current_a": [-1.0] * 6,
            "capacity_ah": [0.0, 0.1, 0.2, 0.0, 0.1, 0.2],
        }
    )
    features, flags = extract_signal_features(raw)
    assert pd.isna(features.iloc[0]["dqdv_peak_voltage_v"])
    assert "incremental_capacity_requires_single_discharge_segment" in set(
        flags["code"]
    )


def test_knee_detection_identifies_acceleration_region():
    cycles = np.arange(1, 61, dtype=float)
    target = 100.0 - 0.03 * cycles - 0.18 * np.maximum(cycles - 32, 0)
    result = detect_knee_point(
        cycles,
        target,
        min_segment=8,
        bootstrap_samples=40,
        random_seed=7,
    )
    assert result["status"] == "candidate"
    assert 28 <= result["knee_cycle"] <= 37
    assert (
        result["slope_after_percent_per_cycle"]
        < result["slope_before_percent_per_cycle"]
    )
    assert result["bootstrap_success_count"] == 40


def test_forecast_table_uses_only_origin_and_prior_information():
    config = BatteryIntelligenceConfig(n_splits=3, knee_bootstrap_samples=0)
    validated, _, _ = validate_cycle_summary(_cycle_summary(), config)
    table, features, metadata = build_forecast_table(validated, config)
    assert "origin_cycle_feature" in features
    assert "target_cycle" not in features
    assert "future_target" not in features
    assert "cycle_index" not in features
    assert metadata["exact_horizon_only"] is True
    first = table.sort_values(["battery_id", "origin_cycle"]).iloc[0]
    assert first["origin_cycle"] == 5
    assert first["target_cycle"] == 10


def test_grouped_forecast_has_no_battery_overlap_and_reports_ood():
    config = BatteryIntelligenceConfig(n_splits=3, knee_bootstrap_samples=0)
    validated, _, _ = validate_cycle_summary(_cycle_summary(), config)
    table, features, _ = build_forecast_table(validated, config)
    predictions, per_group, validation = evaluate_grouped_forecast(
        table, features, config
    )
    summary = validation["summary"]
    assert summary["train_test_group_overlap_count"] == 0
    assert summary["evaluated_battery_count"] == 6
    assert len(predictions) == len(table)
    assert len(per_group) == 6
    assert predictions["outside_training_range_feature_count"].ge(0).all()
    assert summary["interval_prediction_count"] > 0
    assert all(
        fold["train_test_group_overlap_count"] == 0
        for fold in validation["folds"]
    )


def test_end_to_end_run_writes_auditable_outputs(tmp_path: Path):
    source = tmp_path / "cycle_summary.csv"
    _cycle_summary().to_csv(source, index=False)
    output = tmp_path / "run"
    config = BatteryIntelligenceConfig(n_splits=3, knee_bootstrap_samples=10)
    manifest = run_battery_intelligence(
        cycle_summary_path=source,
        output_dir=output,
        config=config,
    )
    assert manifest["artifact_kind"] == "battery_degradation_intelligence"
    assert manifest["validation_summary"]["train_test_group_overlap_count"] == 0
    assert (output / "tables" / "trajectory_diagnostics.csv").is_file()
    assert (output / "tables" / "validation_predictions.csv").is_file()
    assert (output / "reports" / "scientific_closeout.md").is_file()
    assert (output / "figures" / "capacity_trajectories.png").is_file()
    assert (output / "run_manifest.json").is_file()
    with pytest.raises(FileExistsError, match="non-empty"):
        run_battery_intelligence(
            cycle_summary_path=source,
            output_dir=output,
            config=config,
        )


def test_module_has_no_network_dynamic_execution_or_pickle():
    package = Path("src/platform_core/battery_intelligence")
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(package.glob("*.py"))
    )
    assert "import requests" not in text
    assert "import urllib" not in text
    assert "eval(" not in text
    assert "exec(" not in text
    assert "pickle" not in text
