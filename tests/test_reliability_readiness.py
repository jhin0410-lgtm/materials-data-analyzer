"""Tests for generic reliability readiness checks."""

from __future__ import annotations

import pandas as pd

from analyzers.reliability_readiness import (
    ReliabilityReadinessConfig,
    build_reliability_readiness_report,
    check_required_columns,
)


def _reliability_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset_id": ["A", "A", "A", "B", "B", "B", "C", "C", "C", "D", "D", "D"],
            "component_id": ["bearing"] * 12,
            "fleet_id": ["F1"] * 6 + ["F2"] * 6,
            "observation_timestamp": pd.to_datetime(
                [
                    "2025-01-01",
                    "2025-01-02",
                    "2025-01-03",
                    "2025-01-01",
                    "2025-01-02",
                    "2025-01-03",
                    "2025-01-01",
                    "2025-01-02",
                    "2025-01-03",
                    "2025-01-01",
                    "2025-01-02",
                    "2025-01-03",
                ]
            ),
            "observation_cycle": [1, 2, 3] * 4,
            "prediction_origin": pd.to_datetime(
                [
                    "2025-01-01",
                    "2025-01-02",
                    "2025-01-03",
                    "2025-01-01",
                    "2025-01-02",
                    "2025-01-03",
                    "2025-01-01",
                    "2025-01-02",
                    "2025-01-03",
                    "2025-01-01",
                    "2025-01-02",
                    "2025-01-03",
                ]
            ),
            "event_indicator": [0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 1],
            "event_timestamp": [
                None,
                None,
                "2025-01-03",
                None,
                None,
                None,
                None,
                "2025-01-02",
                "2025-01-03",
                None,
                None,
                "2025-01-03",
            ],
            "censoring_timestamp": [
                "2025-01-03",
                "2025-01-03",
                None,
                "2025-01-03",
                "2025-01-03",
                "2025-01-03",
                "2025-01-03",
                None,
                None,
                "2025-01-03",
                "2025-01-03",
                None,
            ],
            "maintenance_timestamp": [
                None,
                None,
                "2025-01-04",
                None,
                None,
                None,
                None,
                "2025-01-03",
                "2025-01-04",
                None,
                None,
                "2025-01-04",
            ],
            "maintenance_type": [
                None,
                None,
                "replace",
                None,
                None,
                None,
                None,
                "repair",
                "repair",
                None,
                None,
                "replace",
            ],
            "vibration_rms": [0.1, 0.2, 0.9, 0.1, 0.2, 0.3, 0.2, 0.8, 1.1, 0.1, 0.4, 0.7],
            "temperature_c": [30, 31, 35, 29, 29, 30, 32, 37, 39, 28, 31, 33],
            "future_window_mean": [0.2] * 12,
            "final_cycle_count": [3] * 12,
            "rul": [2, 1, 0, None, None, None, 2, 1, 0, 2, 1, 0],
        }
    )


def _config() -> ReliabilityReadinessConfig:
    return ReliabilityReadinessConfig(
        required_columns=[
            "asset_id",
            "observation_timestamp",
            "prediction_origin",
            "event_indicator",
        ],
        asset_id_column="asset_id",
        component_id_column="component_id",
        fleet_id_column="fleet_id",
        observation_timestamp_column="observation_timestamp",
        observation_cycle_column="observation_cycle",
        prediction_origin_column="prediction_origin",
        event_indicator_column="event_indicator",
        event_timestamp_column="event_timestamp",
        censoring_timestamp_column="censoring_timestamp",
        maintenance_timestamp_column="maintenance_timestamp",
        maintenance_type_column="maintenance_type",
        degradation_feature_columns=["vibration_rms", "temperature_c", "missing_sensor"],
        min_assets_for_asset_split=3,
        min_observations_per_asset=2,
        min_events_for_event_model=3,
        min_rows_for_temporal_split=10,
    )


def test_required_asset_id_column_is_reported_when_missing() -> None:
    df = _reliability_df().drop(columns=["asset_id"])

    required = check_required_columns(df, ["asset_id", "event_indicator"])
    statuses = dict(zip(required["column"], required["status"], strict=True))

    assert statuses["asset_id"] == "missing"
    assert statuses["event_indicator"] == "present"


def test_asset_cardinality_and_trajectory_lengths_are_reported() -> None:
    report = build_reliability_readiness_report(_reliability_df(), _config())

    asset = report["asset_summary"].iloc[0]
    trajectory = report["trajectory_length"].iloc[0]

    assert asset["asset_count"] == 4
    assert asset["status"] == "asset_longitudinal_ready"
    assert trajectory["min_length"] == 3
    assert trajectory["status"] == "longitudinal"


def test_timestamp_and_cycle_order_are_checked_per_asset() -> None:
    report = build_reliability_readiness_report(_reliability_df(), _config())
    order = report["temporal_order"].set_index("order_type")

    assert order.loc["timestamp", "status"] == "ordered"
    assert order.loc["timestamp", "nonmonotonic_asset_count"] == 0
    assert order.loc["cycle", "status"] == "ordered"


def test_event_indicator_values_and_recurrent_events_are_reported() -> None:
    report = build_reliability_readiness_report(_reliability_df(), _config())

    event = report["event_indicator"].iloc[0]
    recurrent = report["recurrent_events"].iloc[0]

    assert bool(event["valid_values"]) is True
    assert event["event_count"] == 4
    assert recurrent["recurrent_asset_count"] == 1
    assert recurrent["status"] == "recurrent_events_present"


def test_invalid_event_indicator_values_are_flagged() -> None:
    df = _reliability_df()
    df.loc[0, "event_indicator"] = 2

    report = build_reliability_readiness_report(df, _config())
    event = report["event_indicator"].iloc[0]

    assert event["status"] == "invalid_event_values"
    assert event["invalid_value_count"] == 1


def test_event_and_censoring_timestamp_consistency_are_checked() -> None:
    report = build_reliability_readiness_report(_reliability_df(), _config())
    consistency = report["event_censoring"].set_index("check")

    assert consistency.loc["event_timestamp_after_observation", "status"] == "valid"
    assert consistency.loc["event_timestamp_after_prediction_origin", "status"] == "valid"
    assert consistency.loc["censoring_timestamp_after_observation", "status"] == "valid"


def test_event_timestamp_before_observation_is_flagged() -> None:
    df = _reliability_df()
    df.loc[2, "event_timestamp"] = "2024-12-31"

    report = build_reliability_readiness_report(df, _config())
    consistency = report["event_censoring"].set_index("check")

    assert consistency.loc["event_timestamp_after_observation", "status"] == "event_precedes_observation"
    assert consistency.loc["event_timestamp_after_observation", "violation_count"] == 1


def test_validation_readiness_reports_asset_time_and_combined_splits() -> None:
    report = build_reliability_readiness_report(_reliability_df(), _config())
    validation = report["validation_readiness"].set_index("validation_type")

    assert bool(validation.loc["asset_disjoint_split", "ready"]) is True
    assert bool(validation.loc["forward_time_split", "ready"]) is True
    assert bool(validation.loc["combined_asset_time_split", "ready"]) is True


def test_leakage_patterns_flag_post_event_and_future_features() -> None:
    report = build_reliability_readiness_report(_reliability_df(), _config())
    leakage = report["leakage_risks"].set_index("field_or_pattern")

    assert leakage.loc["future_window", "status"] == "prohibited_feature_present"
    assert leakage.loc["final_cycle", "status"] == "prohibited_feature_present"
    assert leakage.loc["rul", "status"] == "prohibited_feature_present"
    assert bool(leakage.loc["rul", "allowed_as_feature"]) is False


def test_degradation_feature_availability_is_summarized() -> None:
    report = build_reliability_readiness_report(_reliability_df(), _config())
    features = report["feature_availability"].set_index("feature")

    assert features.loc["vibration_rms", "status"] == "available"
    assert bool(features.loc["vibration_rms", "numeric"]) is True
    assert features.loc["missing_sensor", "status"] == "missing"


def test_readiness_module_is_deterministic() -> None:
    first = build_reliability_readiness_report(_reliability_df(), _config())
    second = build_reliability_readiness_report(_reliability_df(), _config())

    for key in first:
        pd.testing.assert_frame_equal(first[key], second[key])
