"""Markdown report builders."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import OutputPaths
from io_utils import display_path
from visualization import figure_results_to_markdown


def format_markdown_value(value: object, float_digits: int = 4) -> str:
    """Format one value so it looks nice inside a Markdown table."""
    if pd.isna(value):
        return ""
    if isinstance(value, (float, np.floating)):
        return f"{value:.{float_digits}f}"
    return str(value).replace("\n", " ").replace("|", r"\|")


def dataframe_to_markdown(df: pd.DataFrame, float_digits: int = 4) -> str:
    """Convert a DataFrame to Markdown without extra dependencies."""
    if df.empty:
        return "No data available.\n"

    headers = [str(column) for column in df.columns]
    rows = [
        [format_markdown_value(value, float_digits) for value in row]
        for row in df.to_numpy()
    ]

    table_lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    table_lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(table_lines)


def series_to_markdown(series: pd.Series) -> str:
    """Convert a Series to a small Markdown table."""
    if series.empty:
        return "No data available.\n"

    df = series.rename("correlation").reset_index()
    df.columns = ["column", "correlation"]
    return dataframe_to_markdown(df)


def build_eda_report(
    input_path: Path,
    output_paths: OutputPaths,
    cleaned_data_path: Path,
    missing_values_path: Path,
    numeric_summary_path: Path,
    outliers_path: Path,
    correlation_matrix_path: Path,
    histogram_paths: list[Path],
    heatmap_path: Path | None,
    df: pd.DataFrame,
    numeric_columns: list[str],
    missing_summary: pd.DataFrame,
    numeric_summary: pd.DataFrame,
    outliers: pd.DataFrame,
    correlation_matrix: pd.DataFrame,
    target_column: str | None,
    target_correlations: pd.Series,
) -> str:
    """Build the Markdown report used by EDA mode."""
    report = [
        "# EDA Report",
        "",
        "## Run",
        f"- Mode: `eda`",
        f"- Output folder: `{display_path(output_paths.root)}`",
        "",
        "## Input",
        f"- Source file: `{display_path(input_path)}`",
        f"- Rows: {df.shape[0]}",
        f"- Columns: {df.shape[1]}",
        f"- Cleaned data: `{display_path(cleaned_data_path)}`",
        f"- Missing values CSV: `{display_path(missing_values_path)}`",
        f"- Numeric summary CSV: `{display_path(numeric_summary_path)}`",
        f"- IQR outliers CSV: `{display_path(outliers_path)}`",
        f"- Correlation matrix CSV: `{display_path(correlation_matrix_path)}`",
        "",
        "## Numeric Columns",
        ", ".join(f"`{column}`" for column in numeric_columns)
        if numeric_columns
        else "No numeric columns were found.",
        "",
        "## Missing Values",
        dataframe_to_markdown(missing_summary),
        "",
        "## Numeric Summary",
        dataframe_to_markdown(
            numeric_summary.reset_index().rename(columns={"index": "column"})
        ),
        "",
        "## IQR Outlier Detection",
        dataframe_to_markdown(outliers),
        "",
        "## Correlation Matrix",
        dataframe_to_markdown(
            correlation_matrix.reset_index().rename(columns={"index": "column"})
        ),
        "",
    ]

    if target_column:
        report.extend(
            [
                f"## Variables Most Correlated With `{target_column}`",
                series_to_markdown(target_correlations),
                "",
            ]
        )

    report.extend(
        [
            "## Figures",
            "- Histograms:",
        ]
    )
    if histogram_paths:
        report.extend(f"  - `{display_path(path)}`" for path in histogram_paths)
    else:
        report.append(
            "  - Not created because no numeric columns were found or "
            "matplotlib is unavailable."
        )

    report.extend(
        [
            f"- Correlation heatmap: `{display_path(heatmap_path)}`"
            if heatmap_path
            else (
                "- Correlation heatmap: not created because fewer than two "
                "numeric columns were found or matplotlib is unavailable."
            ),
            "",
        ]
    )

    return "\n".join(report)


def build_mode_skeleton_report(
    mode: str,
    mode_title: str,
    future_work: list[str],
    input_path: Path,
    output_paths: OutputPaths,
    cleaned_data_path: Path,
    df: pd.DataFrame,
    numeric_columns: list[str],
) -> str:
    """Build a starter report for modes that will be expanded later."""
    columns_df = pd.DataFrame(
        {
            "column": df.columns,
            "dtype": [str(dtype) for dtype in df.dtypes],
            "missing_count": df.isna().sum().to_list(),
        }
    )

    report = [
        f"# {mode_title} Report",
        "",
        "## Run",
        f"- Mode: `{mode}`",
        f"- Output folder: `{display_path(output_paths.root)}`",
        "",
        "## Input",
        f"- Source file: `{display_path(input_path)}`",
        f"- Rows: {df.shape[0]}",
        f"- Columns: {df.shape[1]}",
        f"- Cleaned data: `{display_path(cleaned_data_path)}`",
        "",
        "## Numeric Columns",
        ", ".join(f"`{column}`" for column in numeric_columns)
        if numeric_columns
        else "No numeric columns were found.",
        "",
        "## Column Overview",
        dataframe_to_markdown(columns_df),
        "",
        "## Planned Analysis",
    ]

    report.extend(f"- {item}" for item in future_work)
    report.append("")
    return "\n".join(report)


def build_process_report(
    input_path: Path,
    output_paths: OutputPaths,
    cleaned_data_path: Path,
    target_column: str,
    goal: str,
    best_conditions_path: Path,
    worst_conditions_path: Path,
    ranking_path: Path,
    material_summary_path: Path | None,
    temperature_summary_path: Path | None,
    df: pd.DataFrame,
    best_conditions: pd.DataFrame,
    worst_conditions: pd.DataFrame,
    target_ranking: pd.DataFrame,
    material_summary: pd.DataFrame,
    temperature_summary: pd.DataFrame,
    figure_results: list[tuple[str, str]],
) -> str:
    """Build the Markdown report for process-condition analysis."""
    report = [
        "# Process Analysis Report",
        "",
        "## Run",
        "- Mode: `process`",
        f"- Output folder: `{display_path(output_paths.root)}`",
        "",
        "## Important Notes",
        "- 이 분석은 실제 최적화라기보다 실험 데이터 기반 최적 조건 후보 분석이다.",
        "- 상관관계는 인과관계를 의미하지 않는다.",
        "- 데이터 수가 적으면 결과 해석에 주의해야 한다.",
        "",
        "## Input",
        f"- Source file: `{display_path(input_path)}`",
        f"- Rows: {df.shape[0]}",
        f"- Columns: {df.shape[1]}",
        f"- Target column: `{target_column}`",
        f"- Goal: `{goal}`",
        f"- Cleaned data: `{display_path(cleaned_data_path)}`",
        "",
        "## Saved Files",
        f"- Best conditions: `{display_path(best_conditions_path)}`",
        f"- Worst conditions: `{display_path(worst_conditions_path)}`",
        f"- Target correlation ranking: `{display_path(ranking_path)}`",
    ]

    if material_summary_path:
        report.append(
            f"- Material target summary: `{display_path(material_summary_path)}`"
        )
    if temperature_summary_path:
        report.append(
            "- Temperature-bin target summary: "
            f"`{display_path(temperature_summary_path)}`"
        )

    report.extend(
        [
            "",
            f"## Best 5 Conditions by `{target_column}`",
            dataframe_to_markdown(best_conditions),
            "",
            f"## Worst 5 Conditions by `{target_column}`",
            dataframe_to_markdown(worst_conditions),
            "",
            f"## Correlation Ranking with `{target_column}`",
            dataframe_to_markdown(target_ranking),
            "",
            "## Material Summary",
            dataframe_to_markdown(material_summary)
            if not material_summary.empty
            else "No `material` column was found.",
            "",
            "## Temperature-Bin Summary",
            dataframe_to_markdown(temperature_summary)
            if not temperature_summary.empty
            else "No numeric `process_temp_c` column was found.",
            "",
            "## Figures",
            *figure_results_to_markdown(figure_results),
            "",
        ]
    )

    return "\n".join(report)


def build_multi_objective_process_report(
    input_path: Path,
    output_paths: OutputPaths,
    cleaned_data_path: Path,
    scores_path: Path,
    best_conditions_path: Path,
    worst_conditions_path: Path,
    target_columns: list[str],
    goals: list[str],
    score_columns: list[str],
    df: pd.DataFrame,
    best_conditions: pd.DataFrame,
    worst_conditions: pd.DataFrame,
    figure_results: list[tuple[str, str]],
) -> str:
    """Build the Markdown report for multi-objective process screening."""
    target_goal_lines = [
        f"- `{target_column}`: `{goal}`"
        for target_column, goal in zip(target_columns, goals)
    ]

    report = [
        "# Process Analysis Report",
        "",
        "## Run",
        "- Mode: `process`",
        "- Analysis type: `multi_objective_process_screening`",
        f"- Output folder: `{display_path(output_paths.root)}`",
        "",
        "## Input",
        f"- Source file: `{display_path(input_path)}`",
        f"- Rows: {df.shape[0]}",
        f"- Columns: {df.shape[1]}",
        f"- Cleaned data: `{display_path(cleaned_data_path)}`",
        "",
        "## Saved Files",
        f"- Multi-objective scores: `{display_path(scores_path)}`",
        f"- Best conditions: `{display_path(best_conditions_path)}`",
        f"- Worst conditions: `{display_path(worst_conditions_path)}`",
        "",
        "## Multi-Objective Process Screening",
        "",
        "### Targets and Goals",
        *target_goal_lines,
        "",
        "### Composite Score Method",
        (
            "- Each target is normalized to a 0-to-1 score with min-max "
            "normalization."
        ),
        (
            "- For `maximize`, larger raw values receive higher scores. "
            "For `minimize`, smaller raw values receive higher scores."
        ),
        (
            "- `composite_score` is the average of these target score columns: "
            f"{', '.join(f'`{column}`' for column in score_columns)}."
        ),
        "- 이 결과는 실제 최적화가 아니라 관측 데이터 기반 후보 스크리닝이다.",
        "",
        "### Top 5 Conditions by `composite_score`",
        dataframe_to_markdown(best_conditions),
        "",
        "### Bottom 5 Conditions by `composite_score`",
        dataframe_to_markdown(worst_conditions),
        "",
        "### Figures",
        *figure_results_to_markdown(figure_results),
        "",
    ]

    return "\n".join(report)


def build_reliability_report(
    input_path: Path,
    output_paths: OutputPaths,
    cleaned_data_path: Path,
    summary_path: Path,
    best_conditions_path: Path,
    worst_conditions_path: Path,
    df: pd.DataFrame,
    summary_df: pd.DataFrame,
    best_conditions: pd.DataFrame,
    worst_conditions: pd.DataFrame,
    figure_results: list[tuple[str, str]],
) -> str:
    """Build the Markdown report for reliability mode."""
    return "\n".join(
        [
            "# Reliability Analysis Report",
            "",
            "## Run",
            "- Mode: `reliability`",
            f"- Output folder: `{display_path(output_paths.root)}`",
            "",
            "## Important Notes",
            "- thermal_cycle_count가 높을수록 신뢰성이 높다고 해석할 수 있다.",
            "- resistance_change_percent가 클수록 접합부 열화 가능성이 높다고 볼 수 있다.",
            "- 단, 실제 failure mechanism 판단에는 단면 분석, 전기적 측정, 재료 분석이 추가로 필요하다.",
            "",
            "## Input",
            f"- Source file: `{display_path(input_path)}`",
            f"- Rows: {df.shape[0]}",
            f"- Columns: {df.shape[1]}",
            f"- Cleaned data: `{display_path(cleaned_data_path)}`",
            "",
            "## Saved Files",
            f"- Reliability summary: `{display_path(summary_path)}`",
            f"- Best conditions: `{display_path(best_conditions_path)}`",
            f"- Worst conditions: `{display_path(worst_conditions_path)}`",
            "",
            "## Reliability Summary",
            dataframe_to_markdown(summary_df),
            "",
            "## Top 5 Conditions by `thermal_cycle_count`",
            dataframe_to_markdown(best_conditions),
            "",
            "## Bottom 5 Conditions by `thermal_cycle_count`",
            dataframe_to_markdown(worst_conditions),
            "",
            "## Figures",
            *figure_results_to_markdown(figure_results),
            "",
        ]
    )


def build_smart_factory_report(
    input_path: Path,
    output_paths: OutputPaths,
    cleaned_data_path: Path,
    anomaly_log_path: Path,
    high_defect_path: Path,
    low_yield_path: Path,
    df: pd.DataFrame,
    numeric_summary: pd.DataFrame,
    anomaly_summary: pd.DataFrame,
    high_defect_points: pd.DataFrame,
    low_yield_points: pd.DataFrame,
    figure_results: list[tuple[str, str]],
) -> str:
    """Build the Markdown report for smart factory mode."""
    return "\n".join(
        [
            "# Smart Factory Analysis Report",
            "",
            "## Run",
            "- Mode: `smart_factory`",
            f"- Output folder: `{display_path(output_paths.root)}`",
            "",
            "## Important Notes",
            "- 이 분석은 제조 공정 데이터에서 비정상 구간 후보를 찾기 위한 기초 이상탐지이다.",
            "- 3-sigma 방식은 단순하고 직관적이지만, 실제 공정에서는 설비 상태, 센서 오류, 작업 조건 변화와 함께 해석해야 한다.",
            "",
            "## Input",
            f"- Source file: `{display_path(input_path)}`",
            f"- Rows: {df.shape[0]}",
            f"- Columns: {df.shape[1]}",
            f"- Cleaned data: `{display_path(cleaned_data_path)}`",
            "",
            "## Saved Files",
            f"- Anomaly log: `{display_path(anomaly_log_path)}`",
            f"- High defect points: `{display_path(high_defect_path)}`",
            f"- Low yield points: `{display_path(low_yield_path)}`",
            "",
            "## Numeric Mean and Standard Deviation",
            dataframe_to_markdown(numeric_summary),
            "",
            "## 3-Sigma Anomaly Summary",
            dataframe_to_markdown(anomaly_summary),
            "",
            "## Top 5 High `defect_rate` Points",
            dataframe_to_markdown(high_defect_points),
            "",
            "## Bottom 5 Low `yield_percent` Points",
            dataframe_to_markdown(low_yield_points),
            "",
            "## Figures",
            *figure_results_to_markdown(figure_results),
            "",
        ]
    )


def build_spc_report(
    input_path: Path,
    output_paths: OutputPaths,
    cleaned_data_path: Path,
    summary_path: Path,
    violations_path: Path,
    capability_path: Path,
    target_column: str,
    row_count: int,
    summary: dict[str, float],
    capability_df: pd.DataFrame,
    violation_count: int,
    figure_results: list[tuple[str, str]],
) -> str:
    """Build the Markdown report for SPC mode."""
    return "\n".join(
        [
            "# SPC Analysis Report",
            "",
            "## Run",
            "- Mode: `spc`",
            f"- Output folder: `{display_path(output_paths.root)}`",
            "",
            "## Important Notes",
            "- SPC 결과는 공정 안정성 후보 판단이며, 실제 공정 이상 원인은 설비 상태, 작업 조건, 센서 오류, 원재료 변화와 함께 확인해야 한다.",
            "",
            "## Input",
            f"- Source file: `{display_path(input_path)}`",
            f"- Target column: `{target_column}`",
            f"- Row count: {row_count}",
            f"- Cleaned data: `{display_path(cleaned_data_path)}`",
            "",
            "## Saved Files",
            f"- SPC summary: `{display_path(summary_path)}`",
            f"- Control violations: `{display_path(violations_path)}`",
            f"- Process capability: `{display_path(capability_path)}`",
            "",
            "## Control Limits",
            f"- Center line: {format_markdown_value(summary['center_line'])}",
            f"- Sigma estimate: {format_markdown_value(summary['sigma_estimate'])}",
            f"- I chart UCL: {format_markdown_value(summary['i_ucl'])}",
            f"- I chart LCL: {format_markdown_value(summary['i_lcl'])}",
            f"- MR chart UCL: {format_markdown_value(summary['mr_ucl'])}",
            f"- MR chart LCL: {format_markdown_value(summary['mr_lcl'])}",
            f"- Violation count: {violation_count}",
            "",
            "## Process Capability",
            dataframe_to_markdown(capability_df),
            "",
            "## Figures",
            *figure_results_to_markdown(figure_results),
            "",
        ]
    )


def build_simulation_report(
    input_path: Path,
    output_paths: OutputPaths,
    training_data_path: Path,
    predictions_path: Path,
    metrics_path: Path,
    feature_importance_path: Path,
    target_column: str,
    feature_columns: list[str],
    row_count: int,
    model_type: str,
    split_note: str,
    metrics_df: pd.DataFrame,
    feature_importance_df: pd.DataFrame,
    figure_results: list[tuple[str, str]],
    scenario_result: dict[str, object] | None = None,
) -> str:
    """Build the Markdown report for regression-based simulation mode."""
    report = [
        "# Simulation Report",
        "",
        "## Run",
        "- Mode: `simulation`",
        f"- Output folder: `{display_path(output_paths.root)}`",
        "",
        "## Important Notes",
        "- 이 모델은 관측 데이터 기반 예측 모델이며, 실제 공정 최적화를 의미하지 않는다. 데이터 수가 적거나 실험 설계가 불균형하면 예측 신뢰도가 낮아질 수 있다.",
        "",
        "## Input",
        f"- Source file: `{display_path(input_path)}`",
        f"- Target column: `{target_column}`",
        "- Feature columns: " + ", ".join(f"`{column}`" for column in feature_columns),
        f"- Row count used for modeling: {row_count}",
        "",
        "## Model",
        f"- Model type: {model_type}",
        f"- Train/test split: {split_note}",
        "",
        "## Saved Files",
        f"- Training data: `{display_path(training_data_path)}`",
        f"- Predictions: `{display_path(predictions_path)}`",
        f"- Model metrics: `{display_path(metrics_path)}`",
        f"- Feature importance: `{display_path(feature_importance_path)}`",
        "",
        "## Metrics",
        dataframe_to_markdown(metrics_df),
        "",
        "## Feature Importance",
        dataframe_to_markdown(feature_importance_df),
        "",
        "## Figures",
        *figure_results_to_markdown(figure_results),
        "",
    ]

    if scenario_result:
        scenario_figure_results = scenario_result["figure_results"]
        report.extend(
            [
                "## Scenario-Based What-if Prediction",
                "",
                "- Scenario prediction은 관측 데이터로 학습한 모델 기반 예측이며, 실제 실험 결과를 보장하지 않는다. 학습 데이터 범위를 벗어난 조건에 대한 예측은 신뢰도가 낮을 수 있다.",
                "",
                f"- Scenario input path: `{display_path(scenario_result['scenario_input_path'])}`",
                f"- Scenario row count: {scenario_result['scenario_row_count']}",
                f"- Valid prediction row count: {scenario_result['valid_prediction_row_count']}",
                f"- Excluded row count: {scenario_result['excluded_row_count']}",
                f"- Predicted target column: `{scenario_result['predicted_column']}`",
                f"- Goal: `{scenario_result['goal']}`",
                f"- Scenario predictions CSV: `{display_path(scenario_result['predictions_path'])}`",
                f"- Scenario ranking CSV: `{display_path(scenario_result['ranking_path'])}`",
                "",
                "### Top 5 Scenario Ranking",
                dataframe_to_markdown(scenario_result["top5_ranking"]),
                "",
                "### Scenario Figures",
                *figure_results_to_markdown(scenario_figure_results),
                "",
            ]
        )

    return "\n".join(report)
