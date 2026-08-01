from __future__ import annotations

import pandas as pd

from platform_core.battery_intelligence import (
    BatteryIntelligenceConfig,
    build_forecast_table,
    build_target_comparability_audit,
)


def _cycle_summary() -> pd.DataFrame:
    rows = []
    for battery in ("A", "B"):
        for cycle in range(1, 9):
            rows.append(
                {
                    "battery_id": battery,
                    "cycle_index": cycle,
                    "capacity_retention_percent": 101.0 - cycle,
                    "reference_capacity_ah": 2.0,
                    "reference_capacity_method": "source_rated_capacity_2_ah",
                    "discharge_capacity_ah": 2.0 * (101.0 - cycle) / 100.0,
                    "ambient_temperature_c": 25.0,
                }
            )
    return pd.DataFrame(rows)


def test_forecast_table_exposes_explicit_origin_target_without_duplicate_feature():
    config = BatteryIntelligenceConfig(
        n_splits=2,
        horizon=2,
        lags=(1, 2),
        rolling_window=3,
        knee_bootstrap_samples=0,
    )
    table, features, metadata = build_forecast_table(_cycle_summary(), config)

    assert "origin_target_percent" in table.columns
    assert "current_target" in table.columns
    assert table["origin_target_percent"].equals(table["current_target"])
    assert "origin_target_percent" in features
    assert "current_target" not in features
    assert "reference_capacity_ah" not in features
    assert metadata["legacy_current_target_alias_is_electrical_current"] is False


def test_comparability_audit_never_labels_origin_target_as_current_condition():
    cycles = _cycle_summary()
    forecast_rows = []
    prediction_rows = []
    for battery in ("A", "B"):
        for origin in (3, 4, 5):
            forecast_rows.append(
                {
                    "battery_id": battery,
                    "origin_cycle": origin,
                    "target_cycle": origin + 2,
                    "origin_target_percent": 101.0 - origin,
                    "current_target": 101.0 - origin,
                    "current_abs_max_a": 1.5 if battery == "A" else 2.0,
                    "future_target": 99.0 - origin,
                }
            )
            prediction_rows.append(
                {
                    "battery_id": battery,
                    "actual": 99.0 - origin,
                    "persistence_prediction": 100.0 - origin,
                    "ridge_prediction": 100.0 - origin,
                }
            )

    result = build_target_comparability_audit(
        cycle_summary=cycles,
        forecast_table=pd.DataFrame(forecast_rows),
        predictions=pd.DataFrame(prediction_rows),
        config=BatteryIntelligenceConfig(n_splits=2, knee_bootstrap_samples=0),
    )
    target = result["target_integrity_by_battery"]
    summary = result["summary"]

    assert "median_observed_current_target" not in target.columns
    assert "median_observed_current_abs_max_a" in target.columns
    assert summary["dimension_availability"]["observed_condition_columns"] == [
        "ambient_temperature_c",
        "current_abs_max_a",
    ]
    assert summary["condition_semantics"][
        "origin_target_is_electrical_current"
    ] is False
