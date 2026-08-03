"""Reliability analysis mode."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import OutputPaths
from io_utils import save_cleaned_data, save_dataframe, save_text_report
from reports import build_reliability_report
from visualization import create_reliability_figures
from analyzers.eda import detect_outliers_iqr


def add_summary_row(
    rows: list[dict[str, object]],
    section: str,
    group: object,
    metric: str,
    value: object,
) -> None:
    """Append one row to a long-format summary table.

    Long-format tables are easy to extend because each row stores one result.
    That is useful for reliability data where some columns may or may not exist.
    """
    rows.append(
        {
            "section": section,
            "group": "" if group is None else group,
            "metric": metric,
            "value": value,
        }
    )


def normalize_failed_series(series: pd.Series) -> pd.Series:
    """Convert common failed/pass labels into 1 and 0.

    The input CSV may store failure as 1/0, true/false, yes/no, or fail/pass.
    This helper keeps the analysis tolerant of those common formats.
    """

    def convert_one_value(value: object) -> float:
        if pd.isna(value):
            return np.nan

        text = str(value).strip().lower()
        if text in {"1", "true", "t", "yes", "y", "failed", "fail"}:
            return 1.0
        if text in {"0", "false", "f", "no", "n", "passed", "pass"}:
            return 0.0

        numeric_value = pd.to_numeric(value, errors="coerce")
        if pd.isna(numeric_value):
            return np.nan
        if float(numeric_value) == 1.0:
            return 1.0
        if float(numeric_value) == 0.0:
            return 0.0
        return np.nan

    return series.apply(convert_one_value)


def calculate_reliability_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate reliability metrics when the required columns exist."""
    rows: list[dict[str, object]] = []

    if "failed" in df.columns:
        failed_binary = normalize_failed_series(df["failed"])
        valid_failed = failed_binary.dropna()
        failed_count = int((valid_failed == 1).sum())
        passed_count = int((valid_failed == 0).sum())
        total_count = int(valid_failed.shape[0])
        invalid_count = int(df["failed"].notna().sum() - total_count)
        failure_rate = failed_count / total_count if total_count else np.nan

        add_summary_row(rows, "failure", "all", "failed_0_count", passed_count)
        add_summary_row(rows, "failure", "all", "failed_1_count", failed_count)
        add_summary_row(rows, "failure", "all", "valid_failed_count", total_count)
        add_summary_row(rows, "failure", "all", "invalid_failed_code_count", invalid_count)
        add_summary_row(rows, "failure", "all", "failure_rate", failure_rate)
        add_summary_row(
            rows,
            "failure",
            "all",
            "interpretation_boundary",
            "descriptive_only; exposure, censoring, and confidence intervals not modeled",
        )

    has_thermal_cycles = (
        "thermal_cycle_count" in df.columns
        and pd.api.types.is_numeric_dtype(df["thermal_cycle_count"])
    )

    if has_thermal_cycles and "chip_thickness_um" in df.columns:
        grouped = (
            df.dropna(subset=["chip_thickness_um", "thermal_cycle_count"])
            .groupby("chip_thickness_um", dropna=False)["thermal_cycle_count"]
            .agg(["count", "mean", "std", "min", "max"])
            .reset_index()
        )
        for _, row in grouped.iterrows():
            group_value = row["chip_thickness_um"]
            add_summary_row(
                rows,
                "chip_thickness_um",
                group_value,
                "sample_count",
                int(row["count"]),
            )
            add_summary_row(
                rows,
                "chip_thickness_um",
                group_value,
                "mean_thermal_cycle_count",
                row["mean"],
            )
            add_summary_row(
                rows,
                "chip_thickness_um",
                group_value,
                "std_thermal_cycle_count",
                row["std"],
            )
            add_summary_row(
                rows,
                "chip_thickness_um",
                group_value,
                "min_thermal_cycle_count",
                row["min"],
            )
            add_summary_row(
                rows,
                "chip_thickness_um",
                group_value,
                "max_thermal_cycle_count",
                row["max"],
            )

    if has_thermal_cycles and "substrate_thickness_um" in df.columns:
        grouped = (
            df.dropna(subset=["substrate_thickness_um", "thermal_cycle_count"])
            .groupby("substrate_thickness_um", dropna=False)["thermal_cycle_count"]
            .agg(["count", "mean", "std", "min", "max"])
            .reset_index()
        )
        for _, row in grouped.iterrows():
            group_value = row["substrate_thickness_um"]
            add_summary_row(
                rows,
                "substrate_thickness_um",
                group_value,
                "sample_count",
                int(row["count"]),
            )
            add_summary_row(
                rows,
                "substrate_thickness_um",
                group_value,
                "mean_thermal_cycle_count",
                row["mean"],
            )
            add_summary_row(
                rows,
                "substrate_thickness_um",
                group_value,
                "std_thermal_cycle_count",
                row["std"],
            )
            add_summary_row(
                rows,
                "substrate_thickness_um",
                group_value,
                "min_thermal_cycle_count",
                row["min"],
            )
            add_summary_row(
                rows,
                "substrate_thickness_um",
                group_value,
                "max_thermal_cycle_count",
                row["max"],
            )

    has_cte = "cte_substrate" in df.columns and pd.api.types.is_numeric_dtype(
        df["cte_substrate"]
    )
    if has_thermal_cycles and has_cte:
        correlation = df[["cte_substrate", "thermal_cycle_count"]].corr().iloc[0, 1]
        add_summary_row(
            rows,
            "correlation",
            "cte_substrate_vs_thermal_cycle_count",
            "pearson_correlation",
            correlation,
        )

    has_resistance_change = (
        "resistance_change_percent" in df.columns
        and pd.api.types.is_numeric_dtype(df["resistance_change_percent"])
    )
    if has_resistance_change:
        outliers = detect_outliers_iqr(df, ["resistance_change_percent"])
        if not outliers.empty:
            row = outliers.iloc[0]
            add_summary_row(
                rows,
                "resistance_change_percent",
                "iqr",
                "lower_bound",
                row["lower_bound"],
            )
            add_summary_row(
                rows,
                "resistance_change_percent",
                "iqr",
                "upper_bound",
                row["upper_bound"],
            )
            add_summary_row(
                rows,
                "resistance_change_percent",
                "iqr",
                "outlier_count",
                row["outlier_count"],
            )
            add_summary_row(
                rows,
                "resistance_change_percent",
                "iqr",
                "outlier_percent",
                row["outlier_percent"],
            )

    if not rows:
        add_summary_row(
            rows,
            "status",
            "all",
            "message",
            "No reliability-specific columns were found.",
        )

    return pd.DataFrame(rows)


def select_reliability_conditions(
    df: pd.DataFrame, ascending: bool
) -> pd.DataFrame:
    """Select the best or worst rows based on thermal_cycle_count."""
    if "thermal_cycle_count" not in df.columns:
        return df.head(0).copy()
    if not pd.api.types.is_numeric_dtype(df["thermal_cycle_count"]):
        return df.head(0).copy()

    return df.sort_values(
        "thermal_cycle_count", ascending=ascending, na_position="last"
    ).head(5)


def run_reliability_analysis(
    df: pd.DataFrame,
    input_path: Path,
    target: str | None,
    output_paths: OutputPaths,
) -> dict[str, Path]:
    """Run reliability analysis for thermal cycling and failure data."""
    del target

    cleaned_data_path = save_cleaned_data(df, output_paths)
    summary_df = calculate_reliability_summary(df)
    best_conditions = select_reliability_conditions(df, ascending=False)
    worst_conditions = select_reliability_conditions(df, ascending=True)
    figure_results = create_reliability_figures(df, output_paths)

    summary_path = save_dataframe(
        summary_df, output_paths.processed / "reliability_summary.csv"
    )
    best_conditions_path = save_dataframe(
        best_conditions, output_paths.processed / "reliability_best_conditions.csv"
    )
    worst_conditions_path = save_dataframe(
        worst_conditions, output_paths.processed / "reliability_worst_conditions.csv"
    )

    report_text = build_reliability_report(
        input_path=input_path,
        output_paths=output_paths,
        cleaned_data_path=cleaned_data_path,
        df=df,
        summary_path=summary_path,
        best_conditions_path=best_conditions_path,
        worst_conditions_path=worst_conditions_path,
        summary_df=summary_df,
        best_conditions=best_conditions,
        worst_conditions=worst_conditions,
        figure_results=figure_results,
    )
    report_path = save_text_report(
        report_text, output_paths.reports / "reliability_report.md"
    )
    return {"cleaned_data": cleaned_data_path, "report": report_path}
