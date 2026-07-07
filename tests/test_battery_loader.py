"""Tests for battery aging loader helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from domain_constraints import validate_domain_constraints
from loaders.battery_loader import (
    BATTERY_SUMMARY_CONSTRAINTS,
    BATTERY_SUMMARY_COLUMNS,
    build_cycle_summary,
    extract_cycle_records,
    validate_battery_summary_schema,
)


class FakeMatStruct:
    """Small scipy mat_struct-like object for loader tests."""

    def __init__(self, **fields: object) -> None:
        self._fieldnames = list(fields.keys())
        for key, value in fields.items():
            setattr(self, key, value)


def make_valid_battery_summary() -> pd.DataFrame:
    """Create a minimal valid cycle-level battery summary."""
    return pd.DataFrame(
        {
            "battery_id": ["B0005", "B0005"],
            "cycle_index": [1, 2],
            "ambient_temperature_c": [24.0, 24.0],
            "discharge_capacity_ah": [2.0, 1.9],
            "capacity_retention_percent": [100.0, 95.0],
            "internal_resistance_ohm": [0.04, 0.05],
            "failed": [False, False],
        }
    )


def test_validate_battery_summary_schema_accepts_required_columns() -> None:
    summary_df = make_valid_battery_summary()

    violations = validate_battery_summary_schema(summary_df)

    assert list(summary_df.columns) == BATTERY_SUMMARY_COLUMNS
    assert violations.empty


def test_validate_battery_summary_schema_missing_column_raises_value_error() -> None:
    summary_df = make_valid_battery_summary().drop(columns=["battery_id"])

    with pytest.raises(ValueError):
        validate_battery_summary_schema(summary_df)


def test_capacity_retention_constraint_connects_to_domain_validation() -> None:
    summary_df = make_valid_battery_summary()
    summary_df.loc[1, "capacity_retention_percent"] = 130.0

    violations = validate_domain_constraints(
        summary_df,
        BATTERY_SUMMARY_CONSTRAINTS,
    )

    assert "capacity_retention_percent" in violations["column"].tolist()
    assert "max_value <= 120" in violations["rule"].tolist()


def test_build_cycle_summary_calculates_capacity_retention() -> None:
    records = [
        {
            "battery_id": "B0005",
            "cycle_index": 1,
            "ambient_temperature_c": 24.0,
            "discharge_capacity_ah": 2.0,
            "internal_resistance_ohm": 0.04,
        },
        {
            "battery_id": "B0005",
            "cycle_index": 2,
            "ambient_temperature_c": 24.0,
            "discharge_capacity_ah": 1.8,
            "internal_resistance_ohm": 0.05,
        },
    ]

    summary_df = build_cycle_summary(records)

    assert summary_df.loc[0, "capacity_retention_percent"] == 100.0
    assert summary_df.loc[1, "capacity_retention_percent"] == 90.0


def test_build_cycle_summary_sets_failed_from_capacity_retention() -> None:
    records = [
        {
            "battery_id": "B0005",
            "cycle_index": 1,
            "discharge_capacity_ah": 2.0,
        },
        {
            "battery_id": "B0005",
            "cycle_index": 2,
            "discharge_capacity_ah": 1.5,
        },
    ]

    summary_df = build_cycle_summary(records)

    assert summary_df.loc[0, "failed"] == 0
    assert summary_df.loc[1, "capacity_retention_percent"] == 75.0
    assert summary_df.loc[1, "failed"] == 1


def test_extract_cycle_records_handles_nasa_like_discharge_cycles() -> None:
    discharge_cycle = FakeMatStruct(
        type="discharge",
        ambient_temperature=24.0,
        data=FakeMatStruct(Capacity=1.85),
    )
    charge_cycle = FakeMatStruct(
        type="charge",
        ambient_temperature=24.0,
        data=FakeMatStruct(),
    )
    raw_obj = {"B0005": FakeMatStruct(cycle=[charge_cycle, discharge_cycle])}

    records = extract_cycle_records(raw_obj)

    assert len(records) == 1
    assert records[0]["battery_id"] == "B0005"
    assert records[0]["cycle_index"] == 1
    assert records[0]["raw_cycle_index"] == 2
    assert records[0]["ambient_temperature_c"] == 24.0
    assert records[0]["discharge_capacity_ah"] == 1.85
