"""Tests for preprocessing helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from preprocessing import (
    clean_column_name,
    clean_data,
    preprocess_data,
    standardize_column_names,
)


def test_clean_column_name_converts_to_snake_case() -> None:
    assert clean_column_name("Process Temp C") == "process_temp_c"


def test_standardize_column_names_keeps_compatibility_suffix_behavior() -> None:
    df = pd.DataFrame([[700, 710]], columns=["Process Temp C", "Process-Temp-C"])

    result = standardize_column_names(df)

    assert result.columns.tolist() == ["process_temp_c", "process_temp_c_2"]


def test_standardize_column_names_can_fail_closed_on_collisions() -> None:
    df = pd.DataFrame([[700, 710]], columns=["Process Temp C", "Process-Temp-C"])

    with pytest.raises(ValueError, match="collide after normalization"):
        standardize_column_names(df, fail_on_collision=True)


def test_preprocess_data_records_numeric_coercion_and_missing_values() -> None:
    df = pd.DataFrame(
        {
            "Sample ID": ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"],
            "Measured Value": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "not-recorded"],
        }
    )

    result = preprocess_data(df)

    assert result.dataframe.columns.tolist() == ["sample_id", "measured_value"]
    assert pd.api.types.is_numeric_dtype(result.dataframe["measured_value"])
    assert pd.isna(result.dataframe.loc[9, "measured_value"])
    operation = next(
        row
        for row in result.audit["column_operations"]
        if row["column"] == "measured_value"
    )
    assert operation["numeric_conversion_applied"] is True
    assert operation["numeric_conversion_failures"] == 1
    assert operation["introduced_missing_count"] == 1
    assert result.audit["warning_count"] == 1


def test_preprocess_data_records_column_mapping_and_dropped_empty_rows() -> None:
    df = pd.DataFrame(
        {
            "Sample ID": ["S1", None],
            "Yield (%)": [90.0, None],
        }
    )

    result = preprocess_data(df)

    assert result.audit["dropped_all_empty_row_count"] == 1
    assert result.audit["column_name_policy"] == "fail_on_collision"
    assert result.audit["column_mappings"] == [
        {
            "column_position": 1,
            "original_name": "Sample ID",
            "normalized_base_name": "sample_id",
            "final_name": "sample_id",
            "collision_detected": False,
            "action": "normalized",
        },
        {
            "column_position": 2,
            "original_name": "Yield (%)",
            "normalized_base_name": "yield",
            "final_name": "yield",
            "collision_detected": False,
            "action": "normalized",
        },
    ]


def test_clean_data_converts_blank_strings_to_missing_values() -> None:
    df = pd.DataFrame({"material": ["Al2O3", "   ", "TiO2"]})

    result = clean_data(df)

    assert pd.isna(result.loc[1, "material"])


def test_clean_data_preserves_duplicate_rows() -> None:
    df = pd.DataFrame(
        {
            "sample_id": ["S1", "S1", "S2"],
            "yield_percent": [90.0, 90.0, 95.0],
        }
    )

    result = clean_data(df)

    assert len(result) == 3
    assert int(result.duplicated().sum()) == 1


def test_preprocess_data_preserves_identifier_like_strings_and_leading_zeroes() -> None:
    df = pd.DataFrame(
        {
            "Sample ID": ["001", "002", "A010"],
            "Measured Value": ["1.0", "2.0", "3.0"],
        }
    )

    result = preprocess_data(df)

    assert result.dataframe["sample_id"].astype(str).tolist() == ["001", "002", "A010"]
    assert result.dataframe["sample_id"].notna().all()
    operation = next(
        row for row in result.audit["column_operations"] if row["column"] == "sample_id"
    )
    assert operation["numeric_conversion_applied"] is False
    assert operation["numeric_conversion_skipped_reason"] == "protected_identifier_or_provenance_semantics"


def test_preprocess_data_records_exact_excluded_empty_source_rows() -> None:
    df = pd.DataFrame({"sample_id": ["S1", None, "S3"], "value": [1.0, None, 3.0]})

    result = preprocess_data(df)

    assert result.audit["dropped_all_empty_row_count"] == 1
    assert result.audit["excluded_rows"] == [
        {"source_row_number": 3, "reason": "all_values_missing"}
    ]
