"""Exploratory data analysis mode."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import OutputPaths
from io_utils import save_cleaned_data, save_dataframe, save_text_report
from preprocessing import (
    get_numeric_columns,
    is_protected_semantic_column,
    prepare_target_column,
)
from reports import build_eda_report
from visualization import plot_correlation_heatmap, plot_histograms


def count_missing_values(df: pd.DataFrame) -> pd.Series:
    """Count missing values for each column."""
    return df.isna().sum()


def calculate_missing_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate missing-value counts and ratios for every column.

    The ratio is useful because 10 missing values can mean different things in
    a 20-row dataset and a 10,000-row dataset.
    """
    missing_count = df.isna().sum()
    row_count = len(df)
    missing_ratio = missing_count / row_count if row_count else missing_count * 0

    return pd.DataFrame(
        {
            "column": df.columns,
            "missing_count": missing_count.to_list(),
            "missing_ratio": missing_ratio.to_list(),
            "missing_percent": (missing_ratio * 100).to_list(),
        }
    )


def calculate_numeric_summary(
    df: pd.DataFrame, numeric_columns: list[str]
) -> pd.DataFrame:
    """Calculate mean, standard deviation, minimum, and maximum."""
    if not numeric_columns:
        return pd.DataFrame(columns=["mean", "std", "min", "max"])

    return df[numeric_columns].agg(["mean", "std", "min", "max"]).T


def detect_outliers_iqr(df: pd.DataFrame, numeric_columns: list[str]) -> pd.DataFrame:
    """Detect possible outliers with the IQR rule.

    IQR means interquartile range, or Q3 - Q1. A common rule marks values below
    Q1 - 1.5 * IQR or above Q3 + 1.5 * IQR as possible outliers.
    """
    rows: list[dict[str, object]] = []

    for column in numeric_columns:
        series = df[column].dropna()
        if series.empty:
            rows.append(
                {
                    "column": column,
                    "lower_bound": np.nan,
                    "upper_bound": np.nan,
                    "outlier_count": 0,
                    "non_missing_count": 0,
                    "outlier_percent": 0.0,
                    "screening_status": "screening_only",
                }
            )
            continue

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        outlier_mask = (df[column] < lower_bound) | (df[column] > upper_bound)
        outlier_count = int(outlier_mask.sum())
        non_missing_count = int(series.shape[0])
        outlier_percent = (
            (outlier_count / non_missing_count) * 100 if non_missing_count else 0.0
        )

        rows.append(
            {
                "column": column,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "outlier_count": outlier_count,
                "non_missing_count": non_missing_count,
                "outlier_percent": outlier_percent,
                "screening_status": "screening_only",
            }
        )

    return pd.DataFrame(rows)


def calculate_correlations(df: pd.DataFrame, numeric_columns: list[str]) -> pd.DataFrame:
    """Calculate correlations among numeric columns."""
    if len(numeric_columns) < 2:
        return pd.DataFrame()

    return df[numeric_columns].corr()


def calculate_pairwise_counts(
    df: pd.DataFrame, numeric_columns: list[str]
) -> pd.DataFrame:
    """Return pairwise non-missing sample counts for correlation interpretation."""
    if len(numeric_columns) < 2:
        return pd.DataFrame()
    observed = df[numeric_columns].notna().astype(int)
    return observed.T.dot(observed)


def calculate_spearman_correlations(
    df: pd.DataFrame, numeric_columns: list[str]
) -> pd.DataFrame:
    """Return a robust rank-correlation companion to Pearson screening."""
    if len(numeric_columns) < 2:
        return pd.DataFrame()
    return df[numeric_columns].corr(method="spearman")


def rank_target_correlations(
    correlation_matrix: pd.DataFrame, target_column: str | None
) -> pd.Series:
    """Sort variables by absolute correlation with the target column."""
    if target_column is None or correlation_matrix.empty:
        return pd.Series(dtype=float)

    target_correlations = correlation_matrix[target_column].drop(labels=[target_column])
    return target_correlations.reindex(
        target_correlations.abs().sort_values(ascending=False).index
    )


def run_eda_analysis(
    df: pd.DataFrame,
    input_path: Path,
    target: str | None,
    output_paths: OutputPaths,
) -> dict[str, Path]:
    """Run exploratory data analysis.

    The earlier statistics, outlier detection, correlation analysis, plotting,
    and Markdown report features are grouped here. Other modes can now grow
    without changing the EDA workflow.
    """
    target_column = prepare_target_column(target, df) if target else None
    raw_numeric_columns = get_numeric_columns(df)
    numeric_columns = [
        column
        for column in raw_numeric_columns
        if not is_protected_semantic_column(column)
    ]
    missing_summary = calculate_missing_summary(df)
    numeric_summary = calculate_numeric_summary(df, numeric_columns)
    outliers = detect_outliers_iqr(df, numeric_columns)
    correlation_matrix = calculate_correlations(df, numeric_columns)
    pairwise_counts = calculate_pairwise_counts(df, numeric_columns)
    spearman_matrix = calculate_spearman_correlations(df, numeric_columns)
    target_correlations = (
        rank_target_correlations(correlation_matrix, target_column)
        if target_column
        else pd.Series(dtype=float)
    )

    print(f"Data shape: {df.shape[0]} rows x {df.shape[1]} columns")

    cleaned_data_path = save_cleaned_data(df, output_paths)
    missing_values_path = save_dataframe(
        missing_summary, output_paths.processed / "missing_values.csv"
    )
    numeric_summary_path = save_dataframe(
        numeric_summary.reset_index().rename(columns={"index": "column"}),
        output_paths.processed / "numeric_summary.csv",
    )
    outliers_path = save_dataframe(
        outliers, output_paths.processed / "outliers_iqr.csv"
    )
    correlation_matrix_path = save_dataframe(
        correlation_matrix.reset_index().rename(columns={"index": "column"}),
        output_paths.processed / "correlation_matrix.csv",
    )
    pairwise_counts_path = save_dataframe(
        pairwise_counts.reset_index().rename(columns={"index": "column"}),
        output_paths.processed / "correlation_pairwise_counts.csv",
    )
    spearman_path = save_dataframe(
        spearman_matrix.reset_index().rename(columns={"index": "column"}),
        output_paths.processed / "spearman_correlation_matrix.csv",
    )

    histogram_paths = plot_histograms(df, numeric_columns, output_paths)
    heatmap_path = plot_correlation_heatmap(correlation_matrix, output_paths)

    report_text = build_eda_report(
        input_path=input_path,
        output_paths=output_paths,
        cleaned_data_path=cleaned_data_path,
        missing_values_path=missing_values_path,
        numeric_summary_path=numeric_summary_path,
        outliers_path=outliers_path,
        correlation_matrix_path=correlation_matrix_path,
        histogram_paths=histogram_paths,
        heatmap_path=heatmap_path,
        df=df,
        numeric_columns=numeric_columns,
        missing_summary=missing_summary,
        numeric_summary=numeric_summary,
        outliers=outliers,
        correlation_matrix=correlation_matrix,
        target_column=target_column,
        target_correlations=target_correlations,
    )
    report_path = save_text_report(
        report_text, output_paths.reports / "eda_report.md"
    )

    return {
        "cleaned_data": cleaned_data_path,
        "report": report_path,
        "correlation_pairwise_counts": pairwise_counts_path,
        "spearman_correlation_matrix": spearman_path,
    }
