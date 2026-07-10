"""Tests for Battery Archive case-study group summaries and reports."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from loaders.battery_archive_case_study import (
    GROUP_SUMMARY_COLUMNS,
    REQUIRED_CASE_STUDY_SECTIONS,
    build_case_study_markdown,
    build_reliability_group_summary,
)


def _series_row(
    *,
    cycle_series_id: str,
    source: object = "SourceA",
    chemistry: object = "NMC",
    form_factor: object = "pouch",
    temperature_C: object = 25.0,
    soc_window: object = "0-100",
    charge_c_rate: object = 0.5,
    discharge_c_rate: object = 1.0,
    max_cycle_index: float = 100.0,
    final_retention_pct: float = 75.0,
    min_retention_pct: float = 70.0,
    reached_80pct_threshold: bool = True,
    reached_70pct_threshold: bool = False,
    observed_censored_80pct: bool = False,
    observed_censored_70pct: bool = True,
    persistent_cycle_below_80pct: float | None = 80.0,
    persistent_cycle_below_70pct: float | None = None,
    warning_rows: int = 0,
    invalid_rows: int = 0,
    data_quality_status: str = "analysis_candidate",
    has_duplicate_cycle_index: bool = False,
    has_nonmonotonic_cycle_index: bool = False,
) -> dict[str, object]:
    return {
        "cycle_series_id": cycle_series_id,
        "zip_file": "A.zip",
        "internal_csv_path": f"{cycle_series_id}_cycle_data.csv",
        "file_name": f"{cycle_series_id}_cycle_data.csv",
        "source": source,
        "cell_id": cycle_series_id,
        "chemistry": chemistry,
        "form_factor": form_factor,
        "temperature_C": temperature_C,
        "soc_window": soc_window,
        "charge_c_rate": charge_c_rate,
        "discharge_c_rate": discharge_c_rate,
        "capacity_unit": "Ah",
        "total_rows": 100,
        "valid_cycle_rows": 100 - warning_rows - invalid_rows,
        "warning_rows": warning_rows,
        "invalid_rows": invalid_rows,
        "min_cycle_index": 1,
        "max_cycle_index": max_cycle_index,
        "baseline_capacity": 1.0,
        "baseline_cycle_count": 5,
        "baseline_method": "first_5_valid_discharge_capacity_median_by_cycle_index",
        "baseline_status": "valid",
        "initial_retention_pct": 100.0,
        "final_retention_pct": final_retention_pct,
        "min_retention_pct": min_retention_pct,
        "first_cycle_below_80pct": 40.0 if reached_80pct_threshold else None,
        "persistent_cycle_below_80pct": persistent_cycle_below_80pct,
        "first_cycle_below_70pct": 90.0 if reached_70pct_threshold else None,
        "persistent_cycle_below_70pct": persistent_cycle_below_70pct,
        "reached_80pct_threshold": reached_80pct_threshold,
        "reached_70pct_threshold": reached_70pct_threshold,
        "observed_censored_80pct": observed_censored_80pct,
        "observed_censored_70pct": observed_censored_70pct,
        "has_duplicate_cycle_index": has_duplicate_cycle_index,
        "has_nonmonotonic_cycle_index": has_nonmonotonic_cycle_index,
        "mixed_capacity_unit": False,
        "data_quality_status": data_quality_status,
        "data_quality_message": "synthetic",
    }


def test_group_summary_calculates_threshold_rates_and_warning_rates() -> None:
    series_df = pd.DataFrame(
        [
            _series_row(cycle_series_id="s1", reached_70pct_threshold=True),
            _series_row(
                cycle_series_id="s2",
                reached_80pct_threshold=False,
                reached_70pct_threshold=False,
                observed_censored_80pct=True,
                observed_censored_70pct=True,
                warning_rows=2,
                data_quality_status="has_warnings",
            ),
            _series_row(
                cycle_series_id="s3",
                source="SourceB",
                chemistry="LFP",
                final_retention_pct=90.0,
                reached_80pct_threshold=False,
                observed_censored_80pct=True,
            ),
        ]
    )

    summary = build_reliability_group_summary(series_df)
    group = summary[summary["source"].eq("SourceA")].iloc[0]

    assert list(summary.columns) == GROUP_SUMMARY_COLUMNS
    assert group["series_count"] == 2
    assert group["reached_80pct_count"] == 1
    assert group["reached_80pct_rate"] == 50.0
    assert group["reached_70pct_count"] == 1
    assert group["observed_censored_80pct_count"] == 1
    assert group["warning_series_count"] == 1
    assert group["warning_series_rate"] == 50.0


def test_group_summary_preserves_missing_metadata_group_and_small_group_flag() -> None:
    series_df = pd.DataFrame(
        [
            _series_row(
                cycle_series_id="s1",
                source=None,
                chemistry=None,
                form_factor=None,
                temperature_C=None,
                warning_rows=1,
                data_quality_status="has_warnings",
            )
        ]
    )

    summary = build_reliability_group_summary(series_df)

    assert len(summary) == 1
    assert summary.loc[0, "source"] == "missing"
    assert summary.loc[0, "chemistry"] == "missing"
    assert bool(summary.loc[0, "small_group_flag"]) is True
    assert "small group" in summary.loc[0, "group_quality_message"]


def test_case_study_markdown_contains_required_sections_and_tracking_policy() -> None:
    series_df = pd.DataFrame(
        [
            _series_row(cycle_series_id="s1", has_duplicate_cycle_index=True),
            _series_row(
                cycle_series_id="s2",
                has_nonmonotonic_cycle_index=True,
                warning_rows=1,
                data_quality_status="has_warnings",
            ),
        ]
    )
    group_summary = build_reliability_group_summary(series_df)

    markdown = build_case_study_markdown(series_df, group_summary)

    for section in REQUIRED_CASE_STUDY_SECTIONS:
        assert f"## {section}" in markdown
    assert "not recommended for Git tracking" in markdown
    assert "Simulation was not run automatically" in markdown
    assert "Duplicate cycle-index" in markdown


def test_case_study_cli_creates_compact_outputs(tmp_path) -> None:
    series_path = tmp_path / "series.csv"
    group_output = tmp_path / "group.csv"
    report_output = tmp_path / "case_study.md"
    methodology_output = tmp_path / "methodology.md"
    pd.DataFrame(
        [
            _series_row(cycle_series_id="s1"),
            _series_row(
                cycle_series_id="s2",
                reached_80pct_threshold=False,
                observed_censored_80pct=True,
            ),
        ]
    ).to_csv(series_path, index=False)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_battery_archive_case_study.py",
            "--series-summary",
            str(series_path),
            "--group-summary-output",
            str(group_output),
            "--report-output",
            str(report_output),
            "--methodology-output",
            str(methodology_output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    assert len(pd.read_csv(group_output)) == 1
    assert "## Objective" in report_output.read_text(encoding="utf-8")
    assert "## Commands" in methodology_output.read_text(encoding="utf-8")
    assert "group count: 1" in result.stdout
