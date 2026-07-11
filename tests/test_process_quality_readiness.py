"""Tests for generic process-quality readiness checks."""

from __future__ import annotations

import pandas as pd

from analyzers.process_quality_readiness import (
    ProcessQualityReadinessConfig,
    build_process_quality_readiness_report,
    check_required_columns,
)


def _synthetic_process_quality_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unit_id": ["U001", "U001", "U003", "U004", "U005", "U006"],
            "timestamp": pd.date_range("2025-01-01 08:00:00", periods=6, freq="h"),
            "quality_timestamp": [
                "2025-01-01 09:00:00",
                "2025-01-01 07:30:00",
                "2025-01-01 11:00:00",
                "2025-01-01 12:00:00",
                "2025-01-01 13:00:00",
                "2025-01-01 14:00:00",
            ],
            "equipment_id": ["EQ1", "EQ1", "EQ2", "EQ2", "EQ3", "EQ3"],
            "lot_id": ["L1", "L1", "L2", "L2", "L3", "L3"],
            "batch_id": ["B1", "B1", "B2", "B2", "B3", "B3"],
            "product_id": ["P1", "P1", "P1", "P2", "P2", "P3"],
            "recipe_id": ["R1", "R1", "R1", "R2", "R2", "R3"],
            "temperature_c": [700.0, 701.5, 705.0, 710.0, 709.5, 711.0],
            "pressure_kpa": [98.0, 97.5, 99.0, 100.0, 99.5, 98.5],
            "defect_flag": [0, 0, 1, 0, 1, None],
            "lower_spec_limit": [690.0] * 6,
            "upper_spec_limit": [715.0] * 6,
            "final_disposition": ["pass", "pass", "scrap", "pass", "rework", "pending"],
        }
    )


def _config() -> ProcessQualityReadinessConfig:
    return ProcessQualityReadinessConfig(
        required_columns=[
            "unit_id",
            "timestamp",
            "equipment_id",
            "lot_id",
            "defect_flag",
        ],
        observation_timestamp_column="timestamp",
        quality_timestamp_column="quality_timestamp",
        group_columns=["lot_id", "equipment_id", "product_id"],
        target_columns=["defect_flag"],
        process_feature_columns=["temperature_c", "pressure_kpa"],
        specification_limit_columns=["lower_spec_limit", "upper_spec_limit"],
        forbidden_feature_columns=["final_disposition", "inspection_result"],
        duplicate_key_columns=["unit_id"],
        min_groups_for_group_split=3,
        min_rows_for_time_split=5,
    )


def test_required_column_checks_report_present_and_missing_columns() -> None:
    df = _synthetic_process_quality_df()

    result = check_required_columns(df, ["unit_id", "missing_process_column"])

    statuses = dict(zip(result["column"], result["status"], strict=True))
    assert statuses["unit_id"] == "present"
    assert statuses["missing_process_column"] == "missing"


def test_timestamp_parsing_time_order_and_delayed_target_checks() -> None:
    report = build_process_quality_readiness_report(
        _synthetic_process_quality_df(),
        _config(),
    )

    timestamps = report["timestamp_parseability"].set_index("column")
    assert timestamps.loc["timestamp", "status"] == "parseable"
    assert bool(timestamps.loc["timestamp", "monotonic_increasing"]) is True

    delayed = report["delayed_target"].iloc[0]
    assert delayed["status"] == "target_precedes_observation"
    assert delayed["violation_count"] == 1


def test_duplicate_handling_reports_key_duplicates_without_dropping_rows() -> None:
    df = _synthetic_process_quality_df()

    report = build_process_quality_readiness_report(df, _config())
    duplicates = report["duplicate_summary"].set_index("duplicate_type")

    assert duplicates.loc["key", "duplicate_count"] == 1
    assert len(df) == 6


def test_group_cardinality_and_validation_readiness_are_reported() -> None:
    report = build_process_quality_readiness_report(
        _synthetic_process_quality_df(),
        _config(),
    )

    cardinality = report["group_cardinality"].set_index("column")
    assert cardinality.loc["lot_id", "unique_count"] == 3
    assert cardinality.loc["lot_id", "status"] == "ready"

    validation = report["validation_readiness"].set_index("validation_type")
    assert bool(validation.loc["group_split_by_lot_id", "ready"]) is True
    assert bool(validation.loc["forward_time_split", "ready"]) is True


def test_target_availability_and_class_balance_are_reported() -> None:
    report = build_process_quality_readiness_report(
        _synthetic_process_quality_df(),
        _config(),
    )

    target = report["target_availability"].set_index("target_column")
    assert target.loc["defect_flag", "non_null_count"] == 5
    assert target.loc["defect_flag", "status"] == "available"

    class_values = set(report["class_balance"]["class_value"])
    assert {"0.0", "1.0"}.issubset(class_values)


def test_spec_limit_and_spc_readiness_are_reported() -> None:
    report = build_process_quality_readiness_report(
        _synthetic_process_quality_df(),
        _config(),
    )

    spec_limits = report["specification_limits"].iloc[0]
    assert spec_limits["status"] == "ready"

    spc = report["spc_readiness"].set_index("analysis")
    assert bool(spc.loc["individuals_moving_range", "ready"]) is True
    assert bool(spc.loc["xbar_r_or_xbar_s", "ready"]) is True
    assert bool(spc.loc["process_capability", "ready"]) is True


def test_forbidden_post_outcome_feature_is_flagged() -> None:
    report = build_process_quality_readiness_report(
        _synthetic_process_quality_df(),
        _config(),
    )

    forbidden = report["forbidden_features"].set_index("column")
    assert forbidden.loc["final_disposition", "risk"] == "forbidden_present"
    assert forbidden.loc["inspection_result", "risk"] == "not_present"
