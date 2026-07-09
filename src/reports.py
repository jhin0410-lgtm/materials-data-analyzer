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
        "- This analysis ranks observed rows in the provided dataset; it is not a validated process optimization result.",
        "- Correlation values describe association in this dataset and do not prove causation.",
        "- Interpret screening results with the experiment design, measurement method, and sample history.",
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
        "- These scores are screening aids based on observed rows, not proof of globally optimal process conditions.",
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
            "- Higher thermal cycle count is treated as a screening indicator, not a complete reliability conclusion.",
            "- Resistance change should be interpreted with failure criteria, measurement method, and sample context.",
            "- Confirming a failure mechanism requires additional physical, electrical, or materials analysis.",
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
            "- This analysis flags candidate unusual intervals in demo process-log data.",
            "- The 3-sigma rule is a simple first-pass method; review equipment state, sensor issues, and operating conditions before drawing conclusions.",
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
            "- SPC results are process-stability screening aids; actual root-cause review should include equipment state, operating conditions, sensor quality, and material changes.",
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
    feature_summary_path: Path | None = None,
    feature_ranges_path: Path | None = None,
    sensitivity_summary_path: Path | None = None,
    feature_ranges_df: pd.DataFrame | None = None,
    sensitivity_summary_df: pd.DataFrame | None = None,
    train_test_metrics_path: Path | None = None,
    overfitting_diagnostics_path: Path | None = None,
    cross_validation_metrics_path: Path | None = None,
    train_test_metrics_df: pd.DataFrame | None = None,
    overfitting_diagnostics_df: pd.DataFrame | None = None,
    cross_validation_metrics_df: pd.DataFrame | None = None,
    virtual_experiment_result: dict[str, object] | None = None,
    scenario_result: dict[str, object] | None = None,
    group_column: str | None = None,
    validation_type: str | None = None,
    train_test_group_overlap_count: int | None = None,
) -> str:
    """Build the Markdown report for virtual experiment screening."""
    report = [
        "# Simulation Report",
        "",
        "## Run",
        "- Mode: `simulation`",
        "- Analysis type: `data-driven virtual experiment screening`",
        f"- Output folder: `{display_path(output_paths.root)}`",
        "",
        "## Important Notes",
        "- This mode uses a baseline surrogate model trained on observed tabular engineering data.",
        "- This is not physics simulation, automatic optimization, or a replacement for real experiments.",
        "- Predicted values and rankings are candidate condition screening aids only.",
        "- Generated virtual designs stay within the observed feature min/max ranges from the modeling data.",
        "- Model metrics and predictions may not transfer outside the data quality, range, and assumptions of the input dataset.",
        "- Domain knowledge and validation experiments are still required before using any condition in practice.",
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
    ]

    if feature_summary_path:
        report.append(f"- Feature summary: `{display_path(feature_summary_path)}`")
    if feature_ranges_path:
        report.append(f"- Feature ranges: `{display_path(feature_ranges_path)}`")
    if sensitivity_summary_path:
        report.append(
            f"- Sensitivity summary: `{display_path(sensitivity_summary_path)}`"
        )
    if train_test_metrics_path:
        report.append(
            f"- Train/test metrics: `{display_path(train_test_metrics_path)}`"
        )
    if overfitting_diagnostics_path:
        report.append(
            "- Overfitting diagnostics: "
            f"`{display_path(overfitting_diagnostics_path)}`"
        )
    if cross_validation_metrics_path:
        report.append(
            "- Cross-validation metrics: "
            f"`{display_path(cross_validation_metrics_path)}`"
        )

    validation_context_lines = []
    if group_column:
        validation_context_lines.append(
            f"- Group-aware split was used with group_column=`{group_column}`."
        )
        if train_test_group_overlap_count == 0:
            validation_context_lines.append("- Train/test groups do not overlap.")
        elif train_test_group_overlap_count is not None:
            validation_context_lines.append(
                "- Train/test group overlap count: "
                f"{train_test_group_overlap_count}."
            )
        else:
            validation_context_lines.append(
                "- Train/test group overlap was not assessed because no test "
                "split was available."
            )
    else:
        validation_context_lines.append(
            "- Random split was used; no group column was provided."
        )
    if validation_type:
        validation_context_lines.append(f"- Validation type: `{validation_type}`.")

    report.extend(
        [
            "",
            "## Model Metrics",
            dataframe_to_markdown(metrics_df),
            "",
            "## Observed Feature Ranges",
            dataframe_to_markdown(feature_ranges_df)
            if feature_ranges_df is not None
            else "No feature range summary was provided.",
            "",
            "## Feature Summary",
            dataframe_to_markdown(feature_importance_df),
            "",
            "## Sensitivity Summary",
            dataframe_to_markdown(sensitivity_summary_df)
            if sensitivity_summary_df is not None
            else "No sensitivity summary was provided.",
            "",
            "## Model Figures",
            *figure_results_to_markdown(figure_results),
            "",
            "## Model Validation",
            "- These diagnostics indicate possible overfitting signals only; they do not prove model failure.",
            *validation_context_lines,
            f"- Train/test metrics CSV: `{display_path(train_test_metrics_path)}`"
            if train_test_metrics_path
            else "- Train/test metrics CSV: not saved.",
            "- Overfitting diagnostics CSV: "
            f"`{display_path(overfitting_diagnostics_path)}`"
            if overfitting_diagnostics_path
            else "- Overfitting diagnostics CSV: not saved.",
            "- Cross-validation metrics CSV: "
            f"`{display_path(cross_validation_metrics_path)}`"
            if cross_validation_metrics_path
            else "- Cross-validation metrics CSV: not saved.",
            "",
            "### Train/Test Metrics",
            dataframe_to_markdown(train_test_metrics_df)
            if train_test_metrics_df is not None
            else "No train/test metrics were provided.",
            "",
            "### Overfitting Diagnostics",
            dataframe_to_markdown(overfitting_diagnostics_df)
            if overfitting_diagnostics_df is not None
            else "No overfitting diagnostics were provided.",
            "",
            "### Cross-Validation Metrics",
            dataframe_to_markdown(cross_validation_metrics_df)
            if cross_validation_metrics_df is not None
            and not cross_validation_metrics_df.empty
            else "Cross-validation was skipped because there were too few rows.",
            "",
            "### Residual Figures",
            *[
                line
                for line in figure_results_to_markdown(figure_results)
                if "Residual" in line
            ],
            "",
        ]
    )

    screening_result = virtual_experiment_result or scenario_result
    if screening_result:
        scenario_figure_results = screening_result["figure_results"]
        scenario_input_path = screening_result.get("scenario_input_path")
        scenario_input_line = (
            f"- Scenario input path: `{display_path(scenario_input_path)}`"
            if scenario_input_path
            else "- Scenario input path: not provided; generated virtual design was used."
        )
        candidate_count = screening_result.get(
            "candidate_row_count", screening_result.get("scenario_row_count")
        )
        candidate_validation_summary = screening_result.get(
            "candidate_validation_summary"
        )
        top_candidate_predictions = screening_result.get("top5_candidate_predictions")
        top_candidate_ranking = screening_result.get("top5_candidate_ranking")
        top_warning_features = screening_result.get("top_warning_features")
        report.extend(
            [
                "## Candidate Prediction Summary",
                "",
                scenario_input_line,
                f"- Candidate count: {candidate_count}",
                f"- Valid candidate count: {screening_result['valid_prediction_row_count']}",
                f"- Invalid candidate count: {screening_result['excluded_row_count']}",
                f"- Target name: `{screening_result.get('target_name', target_column)}`",
                f"- Candidate predictions CSV: `{display_path(screening_result.get('candidate_predictions_path'))}`"
                if screening_result.get("candidate_predictions_path")
                else "- Candidate predictions CSV: not saved.",
                "",
                "### Top Predicted Candidates",
                dataframe_to_markdown(top_candidate_predictions)
                if isinstance(top_candidate_predictions, pd.DataFrame)
                and not top_candidate_predictions.empty
                else "No valid candidate predictions were available.",
                "",
                "### Validation Issue Summary",
                dataframe_to_markdown(candidate_validation_summary)
                if isinstance(candidate_validation_summary, pd.DataFrame)
                and not candidate_validation_summary.empty
                else "No candidate validation summary was available.",
                "",
                "### Domain Warning Summary",
                f"- Candidates with domain warning: {screening_result.get('candidates_with_domain_warning', 0)}",
                f"- Total domain warning count: {screening_result.get('domain_warning_count', 0)}",
                f"- Candidate domain warnings CSV: `{display_path(screening_result.get('candidate_domain_warnings_path'))}`"
                if screening_result.get("candidate_domain_warnings_path")
                else "- Candidate domain warnings CSV: not saved.",
                "",
                "#### Top Warning Features",
                dataframe_to_markdown(top_warning_features)
                if isinstance(top_warning_features, pd.DataFrame)
                and not top_warning_features.empty
                else "No domain warnings were generated.",
                "",
                "Domain warnings are based on training feature min/max ranges and should be interpreted as screening flags, not hard physical limits.",
                "",
                "## Candidate Ranking Summary",
                "",
                f"- Goal: `{screening_result['goal']}`",
                f"- Ranked candidate count: {screening_result.get('ranked_candidate_count', screening_result['valid_prediction_row_count'])}",
                f"- Invalid candidate count: {screening_result.get('invalid_candidate_count', screening_result['excluded_row_count'])}",
                f"- Candidates with domain warning: {screening_result.get('candidates_with_domain_warning', 0)}",
                f"- Candidate ranking CSV: `{display_path(screening_result.get('candidate_ranking_path'))}`"
                if screening_result.get("candidate_ranking_path")
                else "- Candidate ranking CSV: not saved.",
                "",
                "### Top 5 Ranked Candidates",
                dataframe_to_markdown(top_candidate_ranking)
                if isinstance(top_candidate_ranking, pd.DataFrame)
                and not top_candidate_ranking.empty
                else "No ranked candidates were available.",
                "",
                "Ranking is based on model predictions and simple domain warnings. It should be used for screening, not automatic process decisions.",
                "",
                "## Virtual Experiment Screening",
                "",
                "- Candidate rows are predicted with the baseline surrogate model and ranked as screening aids.",
                "- The ranking should not be read as a confirmed best condition or validated process recipe.",
                "",
                f"- Candidate source: `{screening_result.get('candidate_source', 'scenario_input')}`",
                scenario_input_line,
                f"- Design method: `{screening_result.get('design_method', 'scenario_input')}`",
                f"- Candidate row count: {candidate_count}",
                f"- Valid prediction row count: {screening_result['valid_prediction_row_count']}",
                f"- Excluded row count: {screening_result['excluded_row_count']}",
                f"- Predicted target column: `{screening_result['predicted_column']}`",
                f"- Goal: `{screening_result['goal']}`",
                f"- Candidate conditions CSV: `{display_path(screening_result.get('candidate_conditions_path'))}`"
                if screening_result.get("candidate_conditions_path")
                else "- Candidate conditions CSV: not saved.",
                f"- Candidate predictions CSV: `{display_path(screening_result.get('candidate_predictions_path'))}`"
                if screening_result.get("candidate_predictions_path")
                else "- Candidate predictions CSV: not saved.",
                f"- Candidate domain warnings CSV: `{display_path(screening_result.get('candidate_domain_warnings_path'))}`"
                if screening_result.get("candidate_domain_warnings_path")
                else "- Candidate domain warnings CSV: not saved.",
                f"- Candidate ranking CSV: `{display_path(screening_result.get('candidate_ranking_path'))}`"
                if screening_result.get("candidate_ranking_path")
                else "- Candidate ranking CSV: not saved.",
                f"- Virtual experiment design CSV: `{display_path(screening_result.get('design_path'))}`"
                if screening_result.get("design_path")
                else "- Virtual experiment design CSV: not saved.",
                f"- Virtual experiment predictions CSV: `{display_path(screening_result.get('virtual_predictions_path'))}`"
                if screening_result.get("virtual_predictions_path")
                else f"- Scenario predictions CSV: `{display_path(screening_result['predictions_path'])}`",
                f"- Scenario-compatible predictions CSV: `{display_path(screening_result.get('scenario_predictions_path'))}`"
                if screening_result.get("scenario_predictions_path")
                else "",
                f"- Scenario ranking CSV: `{display_path(screening_result['ranking_path'])}`",
                "",
                "### Top 5 Candidate Screening Ranking",
                dataframe_to_markdown(screening_result["top5_ranking"]),
                "",
                "### Virtual Experiment Figures",
                *figure_results_to_markdown(scenario_figure_results),
                "",
            ]
        )

    return "\n".join(report)
