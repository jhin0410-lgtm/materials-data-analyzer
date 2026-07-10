"""Tests for Battery Archive analysis-ready derived cycle tables."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from loaders.battery_archive_cycle_features import (
    BASELINE_METHOD,
    build_analysis_ready_tables,
    build_cycle_series_id,
)


def _row(
    *,
    zip_file: str = "A.zip",
    internal_csv_path: str = "folder/a_cycle_data.csv",
    file_name: str = "a_cycle_data.csv",
    source_row_number: int = 1,
    cycle_index: float | int | None = 1,
    discharge_capacity: float | int | None = 1.0,
    charge_capacity: float | int | None = 1.1,
    discharge_capacity_unit: str = "Ah",
    charge_capacity_unit: str = "Ah",
    discharge_energy: float | int | None = 3.8,
    charge_energy: float | int | None = 4.0,
    discharge_energy_unit: str = "Wh",
    charge_energy_unit: str = "Wh",
    source: str = "Synthetic",
) -> dict[str, object]:
    return {
        "zip_file": zip_file,
        "internal_csv_path": internal_csv_path,
        "file_name": file_name,
        "source": source,
        "cell_id": "CELL_A",
        "chemistry": "NMC",
        "form_factor": "pouch",
        "temperature_C": 25.0,
        "soc_min_pct": 0.0,
        "soc_max_pct": 100.0,
        "soc_window": "0-100",
        "charge_c_rate": 0.5,
        "discharge_c_rate": 1.0,
        "protocol_label": "NMC|pouch|25C|0-100|0.5-1C",
        "schema_fingerprint": "schema_test",
        "source_row_number": source_row_number,
        "cycle_index": cycle_index,
        "elapsed_time": 10.0,
        "elapsed_time_unit": "s",
        "min_current": -1.0,
        "min_current_unit": "A",
        "max_current": 1.0,
        "max_current_unit": "A",
        "min_voltage": 3.0,
        "min_voltage_unit": "V",
        "max_voltage": 4.2,
        "max_voltage_unit": "V",
        "charge_capacity": charge_capacity,
        "charge_capacity_unit": charge_capacity_unit,
        "discharge_capacity": discharge_capacity,
        "discharge_capacity_unit": discharge_capacity_unit,
        "charge_energy": charge_energy,
        "charge_energy_unit": charge_energy_unit,
        "discharge_energy": discharge_energy,
        "discharge_energy_unit": discharge_energy_unit,
        "date_or_timestamp": "2020-01-01",
        "start_time": "2020-01-01",
        "end_time": "2020-01-01",
    }


def test_cycle_series_id_is_deterministic_and_path_safe() -> None:
    first = build_cycle_series_id("A.zip", "folder/a_cycle_data.csv")
    second = build_cycle_series_id("A.zip", "folder/a_cycle_data.csv")
    other = build_cycle_series_id("A.zip", "folder/b_cycle_data.csv")

    assert first == second
    assert first != other
    assert first.startswith("ba_")
    assert "/" not in first
    assert "\\" not in first


def test_baseline_uses_first_five_valid_cycle_median_and_retention_is_not_clipped() -> None:
    capacities = [1.0, 1.1, 1.2, 1.3, 1.4, 2.0]
    df = pd.DataFrame(
        [
            _row(source_row_number=i + 1, cycle_index=i + 1, discharge_capacity=value)
            for i, value in enumerate(capacities)
        ]
    )

    analysis_ready, series_summary, _ = build_analysis_ready_tables(df)

    assert series_summary.loc[0, "baseline_capacity"] == 1.2
    assert series_summary.loc[0, "baseline_cycle_count"] == 5
    assert series_summary.loc[0, "baseline_method"] == BASELINE_METHOD
    assert series_summary.loc[0, "baseline_status"] == "valid"
    last_row = analysis_ready.sort_values("cycle_index").iloc[-1]
    assert round(last_row["capacity_retention_pct"], 2) == 166.67
    assert "high_capacity_retention_warning" in last_row["quality_issues"]


def test_invalid_zero_baseline_leaves_retention_missing() -> None:
    df = pd.DataFrame(
        [
            _row(source_row_number=1, cycle_index=1, discharge_capacity=0.0),
            _row(source_row_number=2, cycle_index=2, discharge_capacity=0.0),
        ]
    )

    analysis_ready, series_summary, _ = build_analysis_ready_tables(df)

    assert series_summary.loc[0, "baseline_status"] == "invalid_no_valid_capacity"
    assert analysis_ready["capacity_retention_pct"].isna().all()
    assert set(analysis_ready["quality_status"]) == {"warning"}
    assert analysis_ready["quality_issues"].str.contains("zero_discharge_capacity").all()


def test_mixed_capacity_unit_series_is_flagged_without_unit_conversion() -> None:
    df = pd.DataFrame(
        [
            _row(source_row_number=1, cycle_index=1, discharge_capacity=1.0),
            _row(
                source_row_number=2,
                cycle_index=2,
                discharge_capacity=1000.0,
                discharge_capacity_unit="mAh",
            ),
        ]
    )

    analysis_ready, series_summary, _ = build_analysis_ready_tables(df)

    assert series_summary.loc[0, "baseline_status"] == "invalid_mixed_capacity_unit"
    assert bool(series_summary.loc[0, "mixed_capacity_unit"]) is True
    unsupported = analysis_ready[
        analysis_ready["discharge_capacity_unit"].eq("mAh")
    ].iloc[0]
    assert unsupported["quality_status"] == "invalid"
    assert "unsupported_capacity_unit" in unsupported["quality_issues"]


def test_duplicate_and_nonmonotonic_cycle_index_are_preserved_as_quality_flags() -> None:
    cycles = [1, 2, 2, 1]
    df = pd.DataFrame(
        [
            _row(source_row_number=i + 1, cycle_index=cycle, discharge_capacity=1.0)
            for i, cycle in enumerate(cycles)
        ]
    )

    analysis_ready, series_summary, _ = build_analysis_ready_tables(df)

    assert bool(series_summary.loc[0, "has_duplicate_cycle_index"]) is True
    assert bool(series_summary.loc[0, "has_nonmonotonic_cycle_index"]) is True
    assert analysis_ready["quality_issues"].str.contains("duplicate_cycle_index").any()
    assert analysis_ready["quality_issues"].str.contains("nonmonotonic_cycle_index").any()


def test_threshold_crossing_and_censoring_summary() -> None:
    rows = []
    for i, capacity in enumerate([1, 1, 1, 1, 1, 0.79, 0.78, 0.77], start=1):
        rows.append(_row(source_row_number=i, cycle_index=i, discharge_capacity=capacity))
    for i, capacity in enumerate([1, 1, 1, 1, 1, 0.95], start=1):
        rows.append(
            _row(
                zip_file="B.zip",
                internal_csv_path="folder/b_cycle_data.csv",
                file_name="b_cycle_data.csv",
                source_row_number=i,
                cycle_index=i,
                discharge_capacity=capacity,
            )
        )
    df = pd.DataFrame(rows)

    _, series_summary, quality_summary = build_analysis_ready_tables(df)
    reached = series_summary[
        series_summary["internal_csv_path"].eq("folder/a_cycle_data.csv")
    ].iloc[0]
    censored = series_summary[
        series_summary["internal_csv_path"].eq("folder/b_cycle_data.csv")
    ].iloc[0]

    assert reached["first_cycle_below_80pct"] == 6
    assert reached["persistent_cycle_below_80pct"] == 6
    assert bool(reached["reached_80pct_threshold"]) is True
    assert bool(censored["reached_80pct_threshold"]) is False
    assert bool(censored["observed_censored_80pct"]) is True
    assert "series_reaching_80pct" in set(quality_summary["metric"])


def test_analysis_ready_outputs_preserve_row_count_and_quality_summary() -> None:
    df = pd.DataFrame(
        [
            _row(source_row_number=1, cycle_index=1, discharge_capacity=1.0),
            _row(source_row_number=2, cycle_index=2, discharge_capacity=None),
        ]
    )

    analysis_ready, series_summary, quality_summary = build_analysis_ready_tables(df)

    assert len(analysis_ready) == len(df)
    assert len(series_summary) == 1
    assert not quality_summary.empty
    assert analysis_ready.loc[1, "quality_status"] == "invalid"
    assert "missing_discharge_capacity" in analysis_ready.loc[1, "quality_issues"]


def test_analysis_ready_cli_creates_outputs(tmp_path) -> None:
    input_path = tmp_path / "normalized.csv"
    analysis_output = tmp_path / "analysis_ready.csv"
    series_output = tmp_path / "series_summary.csv"
    quality_output = tmp_path / "quality_summary.csv"
    pd.DataFrame(
        [
            _row(source_row_number=1, cycle_index=1, discharge_capacity=1.0),
            _row(source_row_number=2, cycle_index=2, discharge_capacity=0.9),
        ]
    ).to_csv(input_path, index=False)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_battery_archive_analysis_ready.py",
            "--input",
            str(input_path),
            "--analysis-ready-output",
            str(analysis_output),
            "--series-summary-output",
            str(series_output),
            "--quality-summary-output",
            str(quality_output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    assert len(pd.read_csv(analysis_output)) == 2
    assert len(pd.read_csv(series_output)) == 1
    assert not pd.read_csv(quality_output).empty
    assert "analysis-ready row count: 2" in result.stdout
