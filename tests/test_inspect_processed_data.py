"""Tests for processed CSV inspection utility."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.inspect_processed_data import inspect_processed_csv


def test_inspect_processed_csv_builds_summary_for_fake_csv() -> None:
    output_dir = Path("outputs") / "_inspect_processed_data_tests"
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "fake_processed.csv"
    pd.DataFrame(
        {
            "material_id": ["mp-1", "mp-2", "mp-2"],
            "band_gap_ev": [1.2, 2.1, 2.1],
            "formation_energy_ev_atom": [-0.5, None, None],
            "notes": ["demo", "demo", "demo"],
        }
    ).to_csv(csv_path, index=False)

    summary = inspect_processed_csv(csv_path)

    assert summary["row_count"] == 3
    assert summary["column_count"] == 4
    assert summary["columns"] == [
        "material_id",
        "band_gap_ev",
        "formation_energy_ev_atom",
        "notes",
    ]
    assert summary["numeric_columns"] == [
        "band_gap_ev",
        "formation_energy_ev_atom",
    ]
    assert summary["non_numeric_columns"] == ["material_id", "notes"]
    assert summary["missing_percent_by_column"]["formation_energy_ev_atom"] == 66.667
    assert summary["duplicate_row_count"] == 1
    assert summary["possible_target_columns"] == ["band_gap_ev"]
