"""Tests for real-data readiness helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from data_validation import build_data_validation_report
from domain_constraints import DomainConstraint, validate_domain_constraints
from schema_mapping import ColumnMapping, apply_schema_mapping


def test_schema_mapping_renames_original_columns_to_standard_names() -> None:
    df = pd.DataFrame(
        {
            "Process Temp (C)": [700, 750],
            "Yield (%)": [90, 95],
            "operator_note": ["demo", "demo"],
        }
    )
    mappings = [
        ColumnMapping(
            original_name="Process Temp (C)",
            standard_name="process_temp_c",
            unit="degC",
            role="feature",
        ),
        ColumnMapping(
            original_name="Yield (%)",
            standard_name="yield_percent",
            unit="percent",
            role="target",
        ),
    ]

    result = apply_schema_mapping(df, mappings)

    assert result.columns.tolist() == [
        "process_temp_c",
        "yield_percent",
        "operator_note",
    ]


def test_schema_mapping_duplicate_standard_name_raises_value_error() -> None:
    df = pd.DataFrame({"Temp A": [700], "Temp B": [710]})
    mappings = [
        ColumnMapping("Temp A", "process_temp_c", "degC", "feature"),
        ColumnMapping("Temp B", "process_temp_c", "degC", "feature"),
    ]

    with pytest.raises(ValueError):
        apply_schema_mapping(df, mappings)


def test_domain_constraint_violation_is_detected() -> None:
    df = pd.DataFrame({"yield_percent": [95.0, 101.0, -1.0]})
    constraints = [
        DomainConstraint(
            column="yield_percent",
            min_value=0.0,
            max_value=100.0,
            description="Yield should be a percentage.",
        )
    ]

    violations = validate_domain_constraints(df, constraints)

    assert set(violations["rule"]) == {"min_value >= 0.0", "max_value <= 100.0"}
    assert violations["violation_count"].sum() == 2


def test_data_validation_report_includes_duplicate_row_count() -> None:
    df = pd.DataFrame(
        {
            "sample_id": ["S1", "S1", "S2"],
            "yield_percent": [90.0, 90.0, None],
        }
    )

    report = build_data_validation_report(df)

    assert report["row_count"] == 3
    assert report["duplicate_row_count"] == 1
    assert "yield_percent" in report["numeric_columns"]
    assert "sample_id" in report["categorical_columns"]
