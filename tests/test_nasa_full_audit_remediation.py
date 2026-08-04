from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from platform_core.battery_intelligence import (
    BatteryIntelligenceConfig,
    build_forecast_table,
    evaluate_grouped_forecast,
    extract_signal_features,
)
from platform_core.battery_intelligence.forecast_table import (
    source_cohort_id_from_location,
)


def _cycle_summary() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    cohorts = ["cohort-a.zip", "cohort-b.zip", "cohort-c.zip"]
    for battery in range(6):
        battery_id = f"B{battery:04d}"
        cohort = cohorts[battery // 2]
        for cycle in range(1, 21):
            rows.append(
                {
                    "battery_id": battery_id,
                    "cycle_index": cycle,
                    "capacity_retention_percent": 100.0 - 0.2 * cycle - battery,
                    "source_mat_file": (
                        f"5_Battery_Data_Set.zip!{cohort}!{battery_id}.mat"
                    ),
                }
            )
    return pd.DataFrame(rows)


def test_source_cohort_uses_innermost_archive() -> None:
    location = (
        "5_Battery_Data_Set.zip!3. BatteryAgingARC_25-44.zip!B0041.mat"
    )
    assert source_cohort_id_from_location(location) == "3. BatteryAgingARC_25-44.zip"


def test_discharge_only_charge_features_are_missing_not_zero() -> None:
    raw = pd.DataFrame(
        {
            "battery_id": ["B1"] * 3,
            "cycle_index": [1] * 3,
            "step_id": ["discharge_1"] * 3,
            "step_type": ["discharge"] * 3,
            "elapsed_time_s": [0.0, 10.0, 20.0],
            "voltage_v": [4.1, 3.8, 3.5],
            "current_a": [-1.0, -1.0, -1.0],
            "capacity_ah": [0.0, 0.002, 0.004],
        }
    )
    features, flags = extract_signal_features(raw)
    row = features.iloc[0]
    assert bool(row["charge_signal_available"]) is False
    assert row["charge_feature_status"] == "not_observed_in_raw_signal"
    for column in (
        "charge_duration_s",
        "charge_cc_duration_s",
        "charge_cv_duration_s",
        "charge_throughput_ah",
        "charge_energy_wh",
        "coulombic_efficiency",
        "energy_efficiency",
        "cv_fraction_of_charge_time",
    ):
        assert pd.isna(row[column]), column
    assert row["discharge_duration_s"] == pytest.approx(20.0)
    assert "charge_signal_not_observed" in set(flags["code"])


def test_source_cohort_validation_is_disjoint_and_drops_fold_constants() -> None:
    config = BatteryIntelligenceConfig(n_splits=3, knee_bootstrap_samples=0)
    table, features, metadata = build_forecast_table(_cycle_summary(), config)
    assert metadata["source_cohort_count"] == 3
    table["constant_feature"] = 1.0
    table["duplicate_feature"] = table["origin_cycle_feature"]
    augmented = [*features, "constant_feature", "duplicate_feature"]

    predictions, by_battery, validation = evaluate_grouped_forecast(
        table,
        augmented,
        config,
        split_group_column="source_cohort_id",
        leave_one_group_out=True,
    )

    summary = validation["summary"]
    assert summary["source_cohort_disjoint"] is True
    assert summary["split_method"] == "leave_one_group_out"
    assert summary["split_count"] == 3
    assert len(predictions) == len(table)
    assert len(by_battery) == 6
    assert math.isfinite(summary["conformal_observed_coverage"])
    for fold in validation["folds"]:
        reasons = fold["dropped_feature_reasons"]
        assert reasons["constant_feature"] == "constant_in_training_fold"
        assert reasons["duplicate_feature"].startswith("exact_duplicate_of:")
        assert fold["model_pipeline"]["ridge_coefficients"]
        assert fold["train_test_group_overlap_count"] == 0


def test_battery_level_coverage_is_reported() -> None:
    config = BatteryIntelligenceConfig(n_splits=3, knee_bootstrap_samples=0)
    table, features, _ = build_forecast_table(_cycle_summary(), config)
    _, by_battery, validation = evaluate_grouped_forecast(table, features, config)
    assert by_battery["conformal_observed_coverage"].between(0.0, 1.0).all()
    assert validation["summary"]["conformal_worst_battery_id"] in set(
        by_battery["battery_id"]
    )
    assert np.isfinite(
        validation["summary"]["conformal_battery_macro_coverage"]
    )
