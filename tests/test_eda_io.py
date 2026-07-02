"""Tests for CSV IO, EDA summaries, and simple process summaries."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from analyzers.eda import calculate_correlations, calculate_missing_summary
from analyzers.process import calculate_material_target_mean
from config import OutputPaths
from io_utils import load_data, save_dataframe

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "test_artifacts"


def _write_test_file(name: str, content: str) -> Path:
    TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = TEST_OUTPUT_DIR / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_data_reads_csv_file() -> None:
    csv_path = _write_test_file("demo_io.csv", "sample_id,value\nS1,1.5\nS2,2.5\n")

    result = load_data(csv_path)

    assert result.shape == (2, 2)
    assert result["value"].tolist() == [1.5, 2.5]


def test_calculate_missing_summary_reports_counts_and_percent() -> None:
    df = pd.DataFrame({"material": ["Al2O3", None, "TiO2"], "yield_percent": [91.0, 94.0, None]})

    summary = calculate_missing_summary(df)

    material_row = summary.loc[summary["column"] == "material"].iloc[0]
    yield_row = summary.loc[summary["column"] == "yield_percent"].iloc[0]
    assert material_row["missing_count"] == 1
    assert yield_row["missing_percent"] == pytest.approx(100 / 3)


def test_calculate_material_target_mean_groups_by_material() -> None:
    df = pd.DataFrame(
        {
            "material": ["Al2O3", "Al2O3", "TiO2"],
            "yield_percent": [90.0, 100.0, 80.0],
        }
    )

    summary = calculate_material_target_mean(df, "yield_percent")

    alumina = summary.loc[summary["material"] == "Al2O3"].iloc[0]
    assert alumina["sample_count"] == 2
    assert alumina["mean_yield_percent"] == 95.0


def test_calculate_correlations_returns_numeric_matrix() -> None:
    df = pd.DataFrame({"temperature_c": [700, 750, 800], "yield_percent": [80, 90, 100]})

    matrix = calculate_correlations(df, ["temperature_c", "yield_percent"])

    assert set(matrix.columns) == {"temperature_c", "yield_percent"}
    assert matrix.loc["temperature_c", "yield_percent"] == pytest.approx(1.0)


def test_save_dataframe_creates_output_file() -> None:
    output_paths = OutputPaths(
        root=TEST_OUTPUT_DIR,
        processed=TEST_OUTPUT_DIR / "processed",
        figures=TEST_OUTPUT_DIR / "figures",
        reports=TEST_OUTPUT_DIR / "reports",
    )
    output_file = output_paths.processed / "summary.csv"

    saved_path = save_dataframe(pd.DataFrame({"value": [1, 2]}), output_file)

    assert saved_path.exists()
    assert "value" in saved_path.read_text(encoding="utf-8-sig")