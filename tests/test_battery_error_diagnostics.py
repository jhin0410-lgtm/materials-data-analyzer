from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from platform_core.battery_intelligence import (
    BatteryIntelligenceConfig,
    audit_raw_signal_admission,
    build_baseline_predictions,
    build_error_diagnostics,
    build_forecast_table,
    evaluate_grouped_forecast,
    run_battery_intelligence,
    validate_cycle_summary,
)
from platform_core.battery_intelligence.common import file_sha256
from platform_core.battery_intelligence.degradation import analyze_trajectories


def _cycle_summary(batteries: int = 6, cycles: int = 30) -> pd.DataFrame:
    rows = []
    for battery in range(batteries):
        for cycle in range(1, cycles + 1):
            slope = 0.04 + 0.01 * battery
            acceleration = max(cycle - 18, 0) * (0.02 + 0.001 * battery)
            rows.append(
                {
                    "battery_id": f"B{battery:02d}",
                    "cycle_index": cycle,
                    "capacity_retention_percent": 100.0 - slope * cycle - acceleration,
                    "ambient_temperature_c": 24.0 + battery,
                    "discharge_capacity_ah": 2.0 - 0.002 * cycle,
                    "reference_capacity_ah": 2.0,
                }
            )
    return pd.DataFrame(rows)


def _validated_forecast():
    config = BatteryIntelligenceConfig(n_splits=3, knee_bootstrap_samples=0)
    validated, _, _ = validate_cycle_summary(_cycle_summary(), config)
    forecast, features, _ = build_forecast_table(validated, config)
    predictions, per_group, validation = evaluate_grouped_forecast(
        forecast, features, config
    )
    trajectories, _ = analyze_trajectories(validated, config)
    return config, validated, forecast, predictions, per_group, validation, trajectories


def test_origin_only_baselines_are_present_and_finite():
    config, _, forecast, *_ = _validated_forecast()
    baselines, metadata = build_baseline_predictions(
        forecast, horizon=config.horizon, lags=config.lags
    )
    assert set(metadata["baseline_names"]) == {
        "persistence",
        "trailing_mean",
        "local_linear",
        "damped_trend",
        "robust_trend",
        "ewma_trend",
    }
    assert metadata["origin_only"] is True
    assert metadata["full_trajectory_knee_used"] is False
    assert np.isfinite(baselines.to_numpy(dtype=float)).all()
    assert np.allclose(
        baselines["persistence_prediction"], forecast["current_target"]
    )


def test_grouped_validation_ranks_all_predeclared_models():
    _, _, _, predictions, per_group, validation, _ = _validated_forecast()
    summary = validation["summary"]
    assert summary["train_test_group_overlap_count"] == 0
    assert summary["best_baseline_name"] in summary["baseline_metadata"][
        "baseline_names"
    ]
    assert "ridge_improvement_percent_vs_best_baseline" in summary
    assert set(summary["model_metrics"]) == {
        "persistence",
        "trailing_mean",
        "local_linear",
        "damped_trend",
        "robust_trend",
        "ewma_trend",
        "ridge",
    }
    for model in summary["model_metrics"]:
        assert f"{model}_prediction" in predictions.columns
    assert "ridge_improved_vs_best_baseline" in per_group.columns


def test_error_diagnostics_split_lifecycle_domain_knee_and_regime():
    config, _, forecast, predictions, per_group, validation, trajectories = (
        _validated_forecast()
    )
    diagnostics = build_error_diagnostics(
        predictions=predictions,
        forecast_table=forecast,
        per_group=per_group,
        trajectory_diagnostics=trajectories,
        validation=validation,
        config=config,
    )
    row_level = diagnostics["row_level"]
    assert {
        "lifecycle_segment",
        "knee_phase",
        "domain_status",
        "degradation_rate_bin",
        "ridge_minus_best_baseline_absolute_error",
    }.issubset(row_level.columns)
    assert not diagnostics["model_comparison"].empty
    assert not diagnostics["by_battery"].empty
    assert diagnostics["summary"]["causal_interpretation_supported"] is False
    assert diagnostics["summary"]["best_baseline_by_mae"] != "ridge"


def test_raw_signal_admission_fails_closed_without_provenance():
    cycle = _cycle_summary(batteries=5, cycles=5)
    raw = pd.DataFrame(
        {
            "battery_id": ["B00", "B00"],
            "cycle_index": [1, 1],
            "step_type": ["discharge", "discharge"],
            "elapsed_time_s": [0.0, 10.0],
            "voltage_v": [4.0, 3.8],
            "current_a": [-1.0, -1.0],
        }
    )
    report = audit_raw_signal_admission(
        cycle_summary=cycle,
        raw_signal=raw,
        provenance=None,
        raw_sha256="a" * 64,
        group_column="battery_id",
        cycle_column="cycle_index",
    )
    assert report["status"] == "not_admitted_missing_provenance"
    assert report["admitted_for_predictive_comparison"] is False


def _raw_signals(cycle: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, item in cycle[["battery_id", "cycle_index"]].iterrows():
        for step_id, step_type, current, voltage in (
            ("charge", "charge_cc", 1.0, 4.0),
            ("discharge", "discharge", -0.9, 3.6),
        ):
            rows.extend(
                [
                    {
                        "battery_id": item["battery_id"],
                        "cycle_index": item["cycle_index"],
                        "step_id": step_id,
                        "step_type": step_type,
                        "elapsed_time_s": 0.0,
                        "voltage_v": voltage,
                        "current_a": current,
                    },
                    {
                        "battery_id": item["battery_id"],
                        "cycle_index": item["cycle_index"],
                        "step_id": step_id,
                        "step_type": step_type,
                        "elapsed_time_s": 60.0,
                        "voltage_v": voltage - (0.1 if step_type == "discharge" else 0.0),
                        "current_a": current,
                    },
                ]
            )
    return pd.DataFrame(rows)


def test_workflow_writes_diagnostics_and_admits_verified_raw_signals(tmp_path: Path):
    cycle = _cycle_summary(batteries=6, cycles=20)
    raw = _raw_signals(cycle)
    cycle_path = tmp_path / "cycle.csv"
    raw_path = tmp_path / "raw.csv"
    provenance_path = tmp_path / "raw.provenance.json"
    cycle.to_csv(cycle_path, index=False)
    raw.to_csv(raw_path, index=False)
    provenance = {
        "source_name": "controlled-test-source",
        "source_identifier": "test://battery-signals/v1",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "source_sha256": file_sha256(raw_path),
        "license_or_terms": "test fixture only",
        "battery_id_mapping_method": "exact stable battery_id",
        "cycle_mapping_method": "exact numeric cycle_index",
        "unit_declarations": {
            "elapsed_time_s": "s",
            "voltage_v": "V",
            "current_a": "A",
        },
    }
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    output = tmp_path / "output"
    manifest = run_battery_intelligence(
        cycle_summary_path=cycle_path,
        raw_signal_path=raw_path,
        raw_signal_provenance_path=provenance_path,
        output_dir=output,
        config=BatteryIntelligenceConfig(
            n_splits=3, knee_bootstrap_samples=0
        ),
    )
    assert manifest["raw_signal_admission"][
        "admitted_for_predictive_comparison"
    ] is True
    assert manifest["signal_feature_comparison"] is not None
    assert (output / "tables" / "model_comparison.csv").is_file()
    assert (output / "tables" / "forecast_error_diagnostics.csv").is_file()
    assert (output / "tables" / "high_error_predictions.csv").is_file()
    assert (output / "reports" / "error_diagnostics_summary.json").is_file()
    assert (output / "reports" / "raw_signal_admission.json").is_file()
    assert (output / "figures" / "model_mae_comparison.png").is_file()
    statuses = manifest["scientific_closeout"]["component_statuses"]
    assert statuses["runtime_execution"]["status"] == "Supported"
    assert statuses["raw_signal_provenance_admission"]["status"] == "Supported"


def test_unverified_raw_signals_do_not_enter_forecast_features(tmp_path: Path):
    cycle = _cycle_summary(batteries=6, cycles=20)
    raw = _raw_signals(cycle)
    cycle_path = tmp_path / "cycle.csv"
    raw_path = tmp_path / "raw.csv"
    cycle.to_csv(cycle_path, index=False)
    raw.to_csv(raw_path, index=False)
    output = tmp_path / "output"
    manifest = run_battery_intelligence(
        cycle_summary_path=cycle_path,
        raw_signal_path=raw_path,
        output_dir=output,
        config=BatteryIntelligenceConfig(
            n_splits=3, knee_bootstrap_samples=0
        ),
    )
    assert manifest["raw_signal_admission"][
        "admitted_for_predictive_comparison"
    ] is False
    assert manifest["signal_feature_comparison"] is None
    features = manifest["validation_summary"]["feature_columns"]
    assert "charge_throughput_ah" not in features
    assert manifest["scientific_closeout"]["component_statuses"][
        "raw_signal_provenance_admission"
    ]["status"] == "Unsupported"
