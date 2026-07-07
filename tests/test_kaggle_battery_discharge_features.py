"""Tests for Kaggle NASA raw discharge feature extraction."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from loaders.kaggle_battery_discharge_features import (
    build_discharge_feature_table,
    extract_discharge_features,
    merge_discharge_features,
)


def test_extract_discharge_features_from_fake_raw_csv() -> None:
    discharge_df = pd.DataFrame(
        {
            "Time": [0.0, 10.0, 20.0],
            "Voltage_measured": [4.2, 3.8, 3.4],
            "Current_measured": [-0.1, -2.0, -1.9],
            "Temperature_measured": [25.0, 27.0, 29.0],
        }
    )

    features = extract_discharge_features(discharge_df)

    assert features["feature_extraction_status"] == "ok"
    assert features["discharge_duration_s"] == 20.0
    assert features["voltage_mean_v"] == pytest.approx(3.8)
    assert features["voltage_min_v"] == 3.4
    assert features["voltage_max_v"] == 4.2
    assert features["current_mean_a"] == pytest.approx(-4.0 / 3.0)
    assert features["temperature_mean_c"] == 27.0
    assert features["temperature_rise_c"] == 4.0
    assert features["raw_sample_count"] == 3


def test_build_discharge_feature_table_marks_missing_source_file() -> None:
    summary_df = pd.DataFrame(
        {
            "battery_id": ["B1"],
            "cycle_index": [1],
            "source_filename": ["missing.csv"],
            "uid": [101],
            "test_id": [5],
        }
    )
    raw_root = Path("outputs") / "_kaggle_battery_feature_tests" / "raw_missing"
    raw_root.mkdir(parents=True, exist_ok=True)

    feature_df = build_discharge_feature_table(summary_df, raw_root)

    assert len(feature_df) == 1
    assert feature_df.loc[0, "source_filename"] == "missing.csv"
    assert feature_df.loc[0, "feature_extraction_status"] == "source_file_not_found"
    assert pd.isna(feature_df.loc[0, "voltage_mean_v"])


def test_merge_discharge_features_preserves_summary_row_count() -> None:
    raw_root = Path("outputs") / "_kaggle_battery_feature_tests" / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "time": [0, 5],
            "voltage": [4.0, 3.5],
            "current": [-1.0, -1.5],
            "temperature": [24.0, 26.0],
        }
    ).to_csv(raw_root / "one.csv", index=False)

    summary_df = pd.DataFrame(
        {
            "battery_id": ["B1", "B1"],
            "cycle_index": [1, 2],
            "source_filename": ["one.csv", "two.csv"],
            "uid": [1, 2],
            "test_id": [10, 11],
        }
    )
    feature_df = build_discharge_feature_table(summary_df, raw_root, limit=1)

    merged_df = merge_discharge_features(summary_df, feature_df)

    assert len(merged_df) == len(summary_df)
    assert merged_df.loc[0, "feature_extraction_status"] == "ok"
    assert pd.isna(merged_df.loc[1, "feature_extraction_status"])
    assert merged_df.loc[0, "discharge_duration_s"] == 5.0
