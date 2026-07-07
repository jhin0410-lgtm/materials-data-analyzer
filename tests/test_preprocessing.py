"""Tests for preprocessing helpers."""

from __future__ import annotations

import pandas as pd

from preprocessing import clean_column_name, clean_data, standardize_column_names


def test_clean_column_name_converts_to_snake_case() -> None:
    assert clean_column_name("Process Temp C") == "process_temp_c"


def test_standardize_column_names_makes_duplicates_unique() -> None:
    df = pd.DataFrame([[700, 710]], columns=["Process Temp C", "Process-Temp-C"])

    result = standardize_column_names(df)

    assert result.columns.tolist() == ["process_temp_c", "process_temp_c_2"]


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
