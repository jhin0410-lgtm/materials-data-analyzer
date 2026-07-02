from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

from data_io import (
    build_data_profile,
    detect_categorical_columns,
    detect_datetime_like_columns,
    detect_numeric_columns,
    load_engineering_csv,
    strip_column_whitespace,
    validate_groupby_columns,
    validate_target_column,
)
from io_utils import load_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "test_data_io"


@pytest.fixture
def test_work_dir() -> Iterator[Path]:
    path = TEST_OUTPUT_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        if path.exists():
            shutil.rmtree(path)


def _write_test_file(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_engineering_csv_reads_valid_csv(test_work_dir: Path) -> None:
    csv_path = _write_test_file(test_work_dir, "valid.csv", "sample_id,value\nS1,1.5\nS2,2.5\n")

    result = load_engineering_csv(csv_path)

    assert result.shape == (2, 2)
    assert result["value"].tolist() == [1.5, 2.5]


def test_load_engineering_csv_missing_file_raises_file_not_found(test_work_dir: Path) -> None:
    missing_path = test_work_dir / "missing.csv"

    with pytest.raises(FileNotFoundError, match="Input file was not found"):
        load_engineering_csv(missing_path)


def test_load_engineering_csv_unsupported_extension_raises_value_error(test_work_dir: Path) -> None:
    xlsx_path = _write_test_file(test_work_dir, "unsupported.xlsx", "not,a,real,xlsx\n")

    with pytest.raises(ValueError, match="Unsupported input file extension"):
        load_engineering_csv(xlsx_path)


def test_load_engineering_csv_empty_file_raises_value_error(test_work_dir: Path) -> None:
    empty_path = _write_test_file(test_work_dir, "empty.csv", "")

    with pytest.raises(ValueError, match="input file is empty"):
        load_engineering_csv(empty_path)


def test_load_engineering_csv_too_few_rows_raises_value_error(test_work_dir: Path) -> None:
    small_path = _write_test_file(test_work_dir, "too_small.csv", "sample_id,value\nS1,1.0\n")

    with pytest.raises(ValueError, match="too few rows"):
        load_engineering_csv(small_path)


def test_strip_column_whitespace_strips_headers() -> None:
    df = pd.DataFrame({" material ": ["Al2O3"], " yield_percent ": [91.0]})

    result = strip_column_whitespace(df)

    assert result.columns.tolist() == ["material", "yield_percent"]


def test_load_engineering_csv_detects_duplicate_columns_after_strip(test_work_dir: Path) -> None:
    duplicate_path = _write_test_file(
        test_work_dir, "duplicate_columns.csv", "sample_id, sample_id\nS1,1\nS2,2\n"
    )

    with pytest.raises(ValueError, match="Duplicate column"):
        load_engineering_csv(duplicate_path)


def test_build_data_profile_reports_missing_values() -> None:
    df = pd.DataFrame({"material": ["Al2O3", None, "TiO2"], "yield_percent": [91.0, None, 88.0]})

    profile = build_data_profile(df)
    missing_values = profile["missing_values"]

    material_row = missing_values.loc[missing_values["column"] == "material"].iloc[0]
    yield_row = missing_values.loc[missing_values["column"] == "yield_percent"].iloc[0]
    assert material_row["missing_count"] == 1
    assert yield_row["missing_percent"] == pytest.approx(33.33)


def test_detect_numeric_columns_uses_pandas_dtypes() -> None:
    df = pd.DataFrame({"temperature_c": [700.0, 710.0], "material": ["A", "B"]})

    assert detect_numeric_columns(df) == ["temperature_c"]


def test_detect_categorical_columns_returns_object_category_bool_candidates() -> None:
    df = pd.DataFrame(
        {
            "material": ["A", "B"],
            "passed": [True, False],
            "temperature_c": [700.0, 710.0],
        }
    )

    assert detect_categorical_columns(df) == ["material", "passed"]


def test_detect_datetime_like_columns_is_conservative() -> None:
    df = pd.DataFrame(
        {
            "run_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "material": ["2026-like", "Al2O3", "TiO2"],
        }
    )

    assert detect_datetime_like_columns(df) == ["run_date"]


def test_validate_target_column_accepts_existing_column_and_rejects_missing() -> None:
    df = pd.DataFrame({"yield_percent": [90.0, 92.0]})

    assert validate_target_column(df, " yield_percent ") == "yield_percent"
    assert validate_target_column(df, None) is None
    with pytest.raises(ValueError, match="Target column"):
        validate_target_column(df, "resistivity")


def test_validate_groupby_columns_accepts_existing_columns_and_rejects_missing() -> None:
    df = pd.DataFrame({"material": ["A", "B"], "batch": [1, 2]})

    assert validate_groupby_columns(df, [" material ", "batch"]) == ["material", "batch"]
    assert validate_groupby_columns(df, None) == []
    with pytest.raises(ValueError, match="Groupby column"):
        validate_groupby_columns(df, ["operator"])


def test_build_data_profile_contains_expected_keys() -> None:
    df = pd.DataFrame(
        {
            "run_date": ["2026-01-01", "2026-01-02"],
            "material": ["A", "B"],
            "yield_percent": [90.0, 92.0],
        }
    )

    profile = build_data_profile(df)

    assert set(profile) == {
        "row_count",
        "column_count",
        "numeric_columns",
        "categorical_columns",
        "datetime_like_columns",
        "duplicate_rows_count",
        "missing_values",
        "numeric_summary",
        "categorical_summary",
    }
    assert profile["row_count"] == 2
    assert profile["column_count"] == 3
    assert profile["numeric_columns"] == ["yield_percent"]
    assert profile["datetime_like_columns"] == ["run_date"]


def test_existing_demo_csv_loads_through_existing_load_data_wrapper() -> None:
    demo_path = PROJECT_ROOT / "data" / "sample" / "experiment_process.csv"

    result = load_data(demo_path)

    assert not result.empty
    assert "yield_percent" in result.columns


def test_existing_eda_cli_still_runs_with_demo_csv() -> None:
    run_name = f"test_data_io_cli_{uuid.uuid4().hex}"
    output_dir = PROJECT_ROOT / "outputs" / run_name
    command = [
        sys.executable,
        "src/process_data.py",
        "--mode",
        "eda",
        "--input",
        "data/sample/experiment_process.csv",
        "--run-name",
        run_name,
    ]

    try:
        result = subprocess.run(command, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True)

        assert result.returncode == 0, result.stderr
        assert (output_dir / "reports").exists()
    finally:
        if output_dir.exists():
            shutil.rmtree(output_dir)