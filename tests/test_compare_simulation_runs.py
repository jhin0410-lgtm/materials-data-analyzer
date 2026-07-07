"""Tests for simulation run comparison utility."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.compare_simulation_runs import build_comparison_table, build_markdown_report


def write_run(root: Path, train_r2: float, test_r2: float) -> Path:
    """Create a minimal fake simulation run folder."""
    processed = root / "processed"
    processed.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        {
            "dataset": ["train", "test"],
            "validation_type": ["group_split_by_battery_id", "group_split_by_battery_id"],
            "row_count": [8, 2],
            "r2": [train_r2, test_r2],
            "mae": [1.0, 2.0],
            "rmse": [2.0, 5.0],
            "note": ["group split", "group split"],
        }
    ).to_csv(processed / "train_test_metrics.csv", index=False)

    pd.DataFrame(
        {
            "diagnostic": ["r2_gap", "rmse_ratio"],
            "train_value": [train_r2, 2.0],
            "test_value": [test_r2, 5.0],
            "gap": [train_r2 - test_r2, 2.5],
            "interpretation": [
                "no strong overfitting signal from R2 gap",
                "possible overfitting signal: test RMSE is much higher than train RMSE",
            ],
        }
    ).to_csv(processed / "overfitting_diagnostics.csv", index=False)

    pd.DataFrame(
        {
            "fold": [1, 2, 3],
            "validation_type": [
                "group_kfold_by_battery_id",
                "group_kfold_by_battery_id",
                "group_kfold_by_battery_id",
            ],
            "r2": [0.6, 0.7, 0.8],
            "mae": [2.0, 2.5, 3.0],
            "rmse": [4.0, 5.0, 6.0],
            "note": ["", "", ""],
        }
    ).to_csv(processed / "cross_validation_metrics.csv", index=False)

    pd.DataFrame(
        {
            "rank": [1, 2, 3],
            "feature": ["cycle_index", "voltage_mean_v", "temperature_mean_c"],
            "summary_type": ["random_forest_importance"] * 3,
            "importance": [0.5, 0.3, 0.2],
            "coefficient": [None, None, None],
            "abs_coefficient": [None, None, None],
        }
    ).to_csv(processed / "feature_importance.csv", index=False)
    return root


def test_build_comparison_table_summarizes_fake_runs() -> None:
    base = Path("outputs") / "_compare_simulation_runs_tests"
    run_a = write_run(base / "run_a", train_r2=0.9, test_r2=0.7)
    run_b = write_run(base / "run_b", train_r2=0.8, test_r2=0.6)

    comparison_df = build_comparison_table(
        [
            f"metadata_random={run_a}",
            f"feature_group={run_b}",
        ]
    )

    assert comparison_df["run_name"].tolist() == ["metadata_random", "feature_group"]
    assert comparison_df.loc[0, "validation_type"] == "group_split_by_battery_id"
    assert comparison_df.loc[0, "r2_gap"] == pytest.approx(0.2)
    assert comparison_df.loc[0, "train_mae"] == 1.0
    assert comparison_df.loc[0, "test_mae"] == 2.0
    assert comparison_df.loc[0, "rmse_ratio"] == 2.5
    assert comparison_df.loc[0, "cv_r2_mean"] == pytest.approx(0.7)
    assert comparison_df.loc[0, "cv_rmse_mean"] == pytest.approx(5.0)
    assert comparison_df.loc[0, "top_1_feature"] == "cycle_index"
    assert comparison_df.loc[0, "top_1_importance"] == 0.5
    assert comparison_df.loc[0, "top_3_features"] == (
        "cycle_index, voltage_mean_v, temperature_mean_c"
    )
    assert "possible overfitting signal" in comparison_df.loc[0, "overfitting_summary"]
    assert "Group-aware validation" in comparison_df.loc[0, "interpretation_note"]


def test_build_markdown_report_contains_required_sections() -> None:
    base = Path("outputs") / "_compare_simulation_runs_report_tests"
    run_a = write_run(base / "metadata_random", train_r2=0.9, test_r2=0.7)
    run_b = write_run(base / "feature_group", train_r2=0.8, test_r2=0.6)
    comparison_df = build_comparison_table(
        [
            f"metadata_random={run_a}",
            f"feature_group={run_b}",
        ]
    )

    report = build_markdown_report(comparison_df)

    assert "## Dataset and analysis-ready filtering summary" in report
    assert "## Model comparison table" in report
    assert "## Random split vs group split interpretation" in report
    assert "## Metadata-only vs feature-enriched interpretation" in report
    assert "## raw_sample_count exclusion result" in report
    assert "## Limitations" in report
    assert "## Next step: battery-level generalization and lagged forecasting" in report
