"""Tests for Kaggle NASA battery metadata loader."""

from __future__ import annotations

import pandas as pd
import pytest

from loaders.kaggle_battery_metadata_loader import (
    build_analysis_ready_summary,
    build_battery_quality_summary,
    build_discharge_cycle_summary,
)


def make_fake_metadata() -> pd.DataFrame:
    """Create small mixed-type Kaggle-like battery metadata."""
    return pd.DataFrame(
        {
            "type": [
                "charge",
                " discharge ",
                "impedance",
                "DISCHARGE",
                "discharge",
                "discharge",
            ],
            "start_time": [
                "2020-01-01 00:00:00",
                "2020-01-02 00:00:00",
                "2020-01-01 00:30:00",
                "2020-01-01 00:00:00",
                "2020-01-01 00:00:00",
                "2020-01-02 00:00:00",
            ],
            "ambient_temperature": [25, 25, 25, 25, 30, 30],
            "battery_id": ["B1", "B1", "B1", "B1", "B2", "B2"],
            "test_id": [0, 2, 3, 1, 10, 11],
            "uid": [0, 2, 3, 1, 10, 11],
            "filename": [
                "charge.csv",
                "b1_cycle_2.csv",
                "impedance.csv",
                "b1_cycle_1.csv",
                "b2_cycle_1.csv",
                "b2_cycle_2.csv",
            ],
            "Capacity": [None, 1.5, None, 2.0, 1.0, 0.75],
        }
    )


def test_build_discharge_cycle_summary_filters_discharge_rows_only() -> None:
    summary_df = build_discharge_cycle_summary(make_fake_metadata())

    assert len(summary_df) == 4
    assert summary_df["source_filename"].tolist() == [
        "b1_cycle_1.csv",
        "b1_cycle_2.csv",
        "b2_cycle_1.csv",
        "b2_cycle_2.csv",
    ]


def test_cycle_index_starts_at_one_for_each_battery_id() -> None:
    summary_df = build_discharge_cycle_summary(make_fake_metadata())

    assert summary_df.loc[summary_df["battery_id"] == "B1", "cycle_index"].tolist() == [
        1,
        2,
    ]
    assert summary_df.loc[summary_df["battery_id"] == "B2", "cycle_index"].tolist() == [
        1,
        2,
    ]


def test_first_valid_reference_method_uses_first_capacity_per_battery() -> None:
    summary_df = build_discharge_cycle_summary(
        make_fake_metadata(),
        reference_capacity_method="first_valid",
    )

    b1_retention = summary_df.loc[
        summary_df["battery_id"] == "B1", "capacity_retention_percent"
    ].tolist()
    b2_retention = summary_df.loc[
        summary_df["battery_id"] == "B2", "capacity_retention_percent"
    ].tolist()

    assert b1_retention == [100.0, 75.0]
    assert b2_retention == [100.0, 75.0]
    assert summary_df["reference_capacity_method"].unique().tolist() == ["first_valid"]


def test_first_n_median_reference_method_uses_initial_valid_window() -> None:
    summary_df = build_discharge_cycle_summary(
        make_fake_metadata(),
        reference_capacity_method="first_n_median",
        reference_window=2,
    )

    b1_retention = summary_df.loc[
        summary_df["battery_id"] == "B1", "capacity_retention_percent"
    ].tolist()
    b2_retention = summary_df.loc[
        summary_df["battery_id"] == "B2", "capacity_retention_percent"
    ].tolist()

    assert b1_retention == pytest.approx([114.285714, 85.714286])
    assert b2_retention == pytest.approx([114.285714, 85.714286])
    assert summary_df["reference_capacity_ah"].tolist() == [1.75, 1.75, 0.875, 0.875]


def test_failed_label_is_one_when_retention_is_below_80() -> None:
    summary_df = build_discharge_cycle_summary(
        make_fake_metadata(),
        reference_capacity_method="first_valid",
    )

    assert summary_df["failed"].tolist() == [0, 1, 0, 1]


def test_lowercase_capacity_column_is_supported() -> None:
    metadata_df = make_fake_metadata().rename(columns={"Capacity": "capacity"})

    summary_df = build_discharge_cycle_summary(metadata_df)

    assert summary_df["discharge_capacity_ah"].tolist() == [2.0, 1.5, 1.0, 0.75]


def test_retention_quality_flag_detects_high_retention_warning() -> None:
    metadata_df = pd.DataFrame(
        {
            "type": ["discharge", "discharge"],
            "start_time": ["2020-01-01", "2020-01-02"],
            "ambient_temperature": [25, 25],
            "battery_id": ["B1", "B1"],
            "test_id": [1, 2],
            "uid": [1, 2],
            "filename": ["low_reference.csv", "high_capacity.csv"],
            "Capacity": [1.0, 1.5],
        }
    )

    summary_df = build_discharge_cycle_summary(
        metadata_df,
        reference_capacity_method="first_valid",
    )

    assert summary_df["capacity_retention_percent"].tolist() == [100.0, 150.0]
    assert summary_df["retention_quality_flag"].tolist() == [
        "normal",
        "high_retention_warning",
    ]


def test_invalid_capacity_rows_are_kept_and_flagged() -> None:
    metadata_df = pd.DataFrame(
        {
            "type": ["discharge", "discharge", "discharge"],
            "start_time": ["2020-01-01", "2020-01-02", "2020-01-03"],
            "ambient_temperature": [25, 25, 25],
            "battery_id": ["B1", "B1", "B1"],
            "test_id": [1, 2, 3],
            "uid": [1, 2, 3],
            "filename": ["zero.csv", "missing.csv", "valid.csv"],
            "Capacity": [0.0, None, 1.0],
        }
    )

    summary_df = build_discharge_cycle_summary(
        metadata_df,
        reference_capacity_method="first_valid",
    )

    assert len(summary_df) == 3
    assert summary_df["retention_quality_flag"].tolist() == [
        "invalid_capacity",
        "invalid_capacity",
        "normal",
    ]
    assert summary_df["source_filename"].tolist() == [
        "zero.csv",
        "missing.csv",
        "valid.csv",
    ]


def test_analysis_ready_summary_keeps_normal_rows_only() -> None:
    metadata_df = pd.DataFrame(
        {
            "type": ["discharge", "discharge"],
            "start_time": ["2020-01-01", "2020-01-02"],
            "ambient_temperature": [25, 25],
            "battery_id": ["B1", "B1"],
            "test_id": [1, 2],
            "uid": [1, 2],
            "filename": ["normal.csv", "warning.csv"],
            "Capacity": [1.0, 1.5],
        }
    )
    full_summary_df = build_discharge_cycle_summary(
        metadata_df,
        reference_capacity_method="first_valid",
    )

    analysis_ready_df = build_analysis_ready_summary(full_summary_df)

    assert len(full_summary_df) == 2
    assert len(analysis_ready_df) == 1
    assert analysis_ready_df["retention_quality_flag"].tolist() == ["normal"]
    assert analysis_ready_df["source_filename"].tolist() == ["normal.csv"]


def test_battery_quality_summary_counts_warnings_and_flags_battery() -> None:
    metadata_df = pd.DataFrame(
        {
            "type": [
                "discharge",
                "discharge",
                "discharge",
                "discharge",
                "discharge",
                "discharge",
            ],
            "start_time": [
                "2020-01-01",
                "2020-01-02",
                "2020-01-03",
                "2020-01-01",
                "2020-01-02",
                "2020-01-03",
            ],
            "ambient_temperature": [25, 25, 25, 30, 30, 30],
            "battery_id": ["B1", "B1", "B1", "B2", "B2", "B2"],
            "test_id": [1, 2, 3, 1, 2, 3],
            "uid": [1, 2, 3, 4, 5, 6],
            "filename": [
                "b1_1.csv",
                "b1_2.csv",
                "b1_3.csv",
                "b2_1.csv",
                "b2_2.csv",
                "b2_3.csv",
            ],
            "Capacity": [1.0, 1.5, 1.6, 0.0, 1.0, 0.9],
        }
    )
    summary_df = build_discharge_cycle_summary(
        metadata_df,
        reference_capacity_method="first_valid",
    )

    quality_summary_df = build_battery_quality_summary(summary_df)

    b1 = quality_summary_df.loc[quality_summary_df["battery_id"] == "B1"].iloc[0]
    b2 = quality_summary_df.loc[quality_summary_df["battery_id"] == "B2"].iloc[0]
    assert b1["row_count"] == 3
    assert b1["normal_count"] == 1
    assert b1["high_retention_warning_count"] == 2
    assert b1["warning_rate"] == pytest.approx(2 / 3)
    assert b1["battery_quality_flag"] == "high_warning_battery"
    assert b2["invalid_capacity_count"] == 1
    assert b2["battery_quality_flag"] == "has_invalid_capacity"


def test_full_summary_preserves_high_retention_warning_rows() -> None:
    metadata_df = pd.DataFrame(
        {
            "type": ["discharge", "discharge"],
            "start_time": ["2020-01-01", "2020-01-02"],
            "ambient_temperature": [25, 25],
            "battery_id": ["B1", "B1"],
            "test_id": [1, 2],
            "uid": [1, 2],
            "filename": ["low_reference.csv", "high_capacity.csv"],
            "Capacity": [1.0, 1.5],
        }
    )

    full_summary_df = build_discharge_cycle_summary(
        metadata_df,
        reference_capacity_method="first_valid",
    )

    assert len(full_summary_df) == 2
    assert "high_retention_warning" in full_summary_df[
        "retention_quality_flag"
    ].tolist()
    assert full_summary_df["capacity_retention_percent"].max() == 150.0
