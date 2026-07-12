"""Tests for generic reliability loader/schema reconnaissance helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from loaders.reliability import (
    build_backblaze_readiness_frame,
    build_leakage_schema_audit,
    build_reliability_config_from_frame,
    build_schema_inventory,
    infer_reliability_column_metadata,
    select_degradation_feature_columns,
)


def _backblaze_sample() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_member": ["day1.csv", "day2.csv", "day1.csv", "day2.csv"],
            "date": ["2020-01-01", "2020-01-02", "2020-01-01", "2020-01-02"],
            "serial_number": ["A", "A", "B", "B"],
            "model": ["M1", "M1", "M2", "M2"],
            "capacity_bytes": [100, 100, 200, 200],
            "failure": [0, 1, 0, 0],
            "smart_5_raw": [0, 10, 0, 0],
            "smart_187_normalized": [100, 95, 100, 100],
            "final_cycle_count": [2, 2, 2, 2],
        }
    )


def test_column_role_inference_flags_core_backblaze_columns() -> None:
    assert infer_reliability_column_metadata("serial_number")["normalized_role"] == "asset_id"
    assert infer_reliability_column_metadata("date")["normalized_role"] == "observation_timestamp"
    assert infer_reliability_column_metadata("failure")["normalized_role"] == "event_indicator"
    assert infer_reliability_column_metadata("smart_5_raw")["normalized_role"] == "degradation_feature"
    assert (
        infer_reliability_column_metadata("final_cycle_count")["leakage_status"]
        == "prohibited_feature"
    )


def test_schema_inventory_contains_required_roles_and_leakage_status() -> None:
    inventory = build_schema_inventory(
        _backblaze_sample(),
        dataset_id="backblaze_drive_stats",
        file_id="sample",
    )
    roles = dict(zip(inventory["source_column"], inventory["normalized_role"], strict=True))
    leakage = dict(zip(inventory["source_column"], inventory["leakage_status"], strict=True))

    assert roles["serial_number"] == "asset_id"
    assert roles["failure"] == "event_indicator"
    assert roles["smart_5_raw"] == "degradation_feature"
    assert leakage["final_cycle_count"] == "prohibited_feature"


def test_leakage_schema_audit_matches_actual_schema_patterns() -> None:
    leakage_map = pd.DataFrame(
        {
            "field_or_pattern": ["final_cycle_count", "future_degradation_windows"],
            "leakage_type": ["final cycle count", "future degradation windows"],
            "risk_level": ["high", "high"],
            "allowed_as_feature": [False, False],
            "allowed_as_metadata": [True, False],
            "mitigation": ["exclude", "past-only windows"],
        }
    )

    audit = build_leakage_schema_audit(
        _backblaze_sample().columns,
        leakage_map,
        dataset_id="backblaze_drive_stats",
    ).set_index("field_or_pattern")

    assert audit.loc["final_cycle_count", "observed_status"] == "observed"
    assert audit.loc["final_cycle_count", "schema_leakage_status"] == "prohibited_feature"
    assert audit.loc["future_degradation_windows", "observed_status"] == "not_observed"


def test_backblaze_readiness_frame_preserves_asset_time_event_mapping() -> None:
    frame = build_backblaze_readiness_frame(_backblaze_sample())

    assert frame["asset_id"].tolist() == ["A", "A", "B", "B"]
    assert frame["observation_cycle"].tolist() == [1, 2, 1, 2]
    assert frame.loc[1, "event_indicator"] == 1
    assert pd.notna(frame.loc[1, "event_timestamp"])
    assert pd.notna(frame.loc[0, "censoring_timestamp"])
    assert "smart_5_raw" in frame.columns


def test_backblaze_readiness_frame_rejects_invalid_event_values() -> None:
    sample = _backblaze_sample()
    sample.loc[0, "failure"] = 2

    with pytest.raises(ValueError, match="failure values must be limited"):
        build_backblaze_readiness_frame(sample)


def test_reliability_config_uses_smart_features_only() -> None:
    frame = build_backblaze_readiness_frame(_backblaze_sample())
    config = build_reliability_config_from_frame(frame)

    assert config.asset_id_column == "asset_id"
    assert config.event_indicator_column == "event_indicator"
    assert select_degradation_feature_columns(frame) == [
        "smart_187_normalized",
        "smart_5_raw",
    ]
