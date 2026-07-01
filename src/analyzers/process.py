"""Process-condition analysis mode."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import DEFAULT_PROCESS_TARGET, OutputPaths
from io_utils import save_cleaned_data, save_dataframe, save_text_report
from preprocessing import clean_column_name, get_numeric_columns, prepare_target_column
from reports import build_multi_objective_process_report, build_process_report
from visualization import create_multi_objective_figures, create_process_figures


def build_target_correlation_ranking(
    df: pd.DataFrame, numeric_columns: list[str], target_column: str
) -> pd.DataFrame:
    """Rank numeric variables by their correlation with the target column."""
    if target_column not in numeric_columns or len(numeric_columns) < 2:
        return pd.DataFrame(columns=["column", "correlation", "abs_correlation"])

    correlations = df[numeric_columns].corr()[target_column]
    correlations = correlations.drop(labels=[target_column], errors="ignore")

    ranking = correlations.rename("correlation").reset_index()
    ranking.columns = ["column", "correlation"]
    ranking["abs_correlation"] = ranking["correlation"].abs()
    return ranking.sort_values("abs_correlation", ascending=False).reset_index(drop=True)


def calculate_material_target_mean(
    df: pd.DataFrame, target_column: str
) -> pd.DataFrame:
    """Calculate target averages for each material when a material column exists."""
    if "material" not in df.columns:
        return pd.DataFrame()

    # dropna=False keeps rows where the material name is missing, which can be
    # helpful when checking data quality.
    return (
        df.groupby("material", dropna=False)[target_column]
        .agg(["count", "mean", "std", "min", "max"])
        .reset_index()
        .rename(
            columns={
                "count": "sample_count",
                "mean": f"mean_{target_column}",
                "std": f"std_{target_column}",
                "min": f"min_{target_column}",
                "max": f"max_{target_column}",
            }
        )
    )


def calculate_temperature_target_mean(
    df: pd.DataFrame, target_column: str
) -> pd.DataFrame:
    """Calculate target averages by process temperature range."""
    temperature_column = "process_temp_c"
    if temperature_column not in df.columns:
        return pd.DataFrame()
    if not pd.api.types.is_numeric_dtype(df[temperature_column]):
        return pd.DataFrame()

    temp_df = df[[temperature_column, target_column]].dropna()
    if temp_df.empty:
        return pd.DataFrame()

    unique_temperature_count = temp_df[temperature_column].nunique()
    if unique_temperature_count == 1:
        temperature_label = f"{temp_df[temperature_column].iloc[0]:.4g}"
        return pd.DataFrame(
            {
                "temperature_bin": [temperature_label],
                "sample_count": [len(temp_df)],
                f"mean_{target_column}": [temp_df[target_column].mean()],
                f"std_{target_column}": [temp_df[target_column].std()],
                f"min_{target_column}": [temp_df[target_column].min()],
                f"max_{target_column}": [temp_df[target_column].max()],
            }
        )

    # Use up to five bins so the report stays readable for beginners.
    bin_count = min(5, unique_temperature_count)
    temp_df = temp_df.copy()
    temp_df["temperature_bin"] = pd.cut(
        temp_df[temperature_column], bins=bin_count, duplicates="drop"
    )

    grouped = (
        temp_df.groupby("temperature_bin", observed=False)[target_column]
        .agg(["count", "mean", "std", "min", "max"])
        .reset_index()
    )
    grouped["temperature_bin"] = grouped["temperature_bin"].astype(str)
    return grouped.rename(
        columns={
            "count": "sample_count",
            "mean": f"mean_{target_column}",
            "std": f"std_{target_column}",
            "min": f"min_{target_column}",
            "max": f"max_{target_column}",
        }
    )


def validate_multi_objective_inputs(
    df: pd.DataFrame, targets: list[str] | None, goals: list[str] | None
) -> tuple[list[str], list[str]]:
    """Clean and validate targets/goals for multi-objective screening."""
    if targets is None or len(targets) == 0:
        raise ValueError(
            "Multi-objective process screening needs at least one target. "
            "Please provide targets with --targets."
        )

    if goals is None or len(goals) == 0:
        raise ValueError(
            "Multi-objective process screening needs one goal for each target. "
            "Please provide goals with --goals, such as: "
            "--goals maximize maximize minimize"
        )

    if len(targets) != len(goals):
        raise ValueError(
            "--targets and --goals must have the same number of values.\n"
            f"Received {len(targets)} targets: {targets}\n"
            f"Received {len(goals)} goals: {goals}"
        )

    cleaned_targets = [clean_column_name(target) for target in targets]
    duplicate_targets = sorted(
        {target for target in cleaned_targets if cleaned_targets.count(target) > 1}
    )
    if duplicate_targets:
        raise ValueError(
            "Duplicate target columns were provided after column-name cleanup: "
            f"{duplicate_targets}\n"
            "Please provide each target only once."
        )

    invalid_goals = [goal for goal in goals if goal not in {"maximize", "minimize"}]
    if invalid_goals:
        raise ValueError(
            "Each value in --goals must be either maximize or minimize.\n"
            f"Invalid goals: {invalid_goals}"
        )

    missing_targets = [
        target for target in cleaned_targets if target not in df.columns
    ]
    if missing_targets:
        available_columns = ", ".join(df.columns)
        raise ValueError(
            "One or more multi-objective target columns were not found.\n"
            f"Requested targets after cleanup: {cleaned_targets}\n"
            f"Missing targets: {missing_targets}\n"
            f"Available columns are: {available_columns}"
        )

    non_numeric_targets = [
        target
        for target in cleaned_targets
        if not pd.api.types.is_numeric_dtype(df[target])
    ]
    if non_numeric_targets:
        raise ValueError(
            "Multi-objective targets must be numeric columns.\n"
            f"Non-numeric targets: {non_numeric_targets}"
        )

    return cleaned_targets, goals


def calculate_target_score(series: pd.Series, goal: str) -> pd.Series:
    """Convert one target column into a 0-to-1 score.

    A score near 1 means "better" for the selected goal. For minimize goals,
    the scale is reversed so smaller raw values receive higher scores.
    """
    numeric_series = pd.to_numeric(series, errors="coerce")
    min_value = numeric_series.min(skipna=True)
    max_value = numeric_series.max(skipna=True)

    if pd.isna(min_value) or pd.isna(max_value):
        return pd.Series(np.nan, index=series.index)

    value_range = max_value - min_value
    if np.isclose(value_range, 0):
        # If every non-missing value is identical, the target cannot rank rows.
        # Give all non-missing rows the same perfect tie score.
        return numeric_series.where(numeric_series.isna(), 1.0)

    if goal == "maximize":
        return (numeric_series - min_value) / value_range

    return (max_value - numeric_series) / value_range


def build_multi_objective_scores(
    df: pd.DataFrame, target_columns: list[str], goals: list[str]
) -> tuple[pd.DataFrame, list[str]]:
    """Add per-target score columns and one average composite score."""
    scores_df = df.copy()
    score_columns: list[str] = []

    for target_column, goal in zip(target_columns, goals):
        score_column = f"score_{target_column}"
        scores_df[score_column] = calculate_target_score(
            scores_df[target_column], goal
        )
        score_columns.append(score_column)

    # The composite score treats every target equally. Missing target values are
    # ignored by pandas mean(), so a row can still be ranked when at least one
    # target score is available.
    scores_df["composite_score"] = scores_df[score_columns].mean(axis=1)
    return scores_df, score_columns


def run_multi_objective_process_analysis(
    df: pd.DataFrame,
    input_path: Path,
    output_paths: OutputPaths,
    targets: list[str] | None,
    goals: list[str] | None,
) -> dict[str, Path]:
    """Run process screening with several targets at the same time."""
    target_columns, validated_goals = validate_multi_objective_inputs(
        df=df, targets=targets, goals=goals
    )

    cleaned_data_path = save_cleaned_data(df, output_paths)
    scores_df, score_columns = build_multi_objective_scores(
        df=df,
        target_columns=target_columns,
        goals=validated_goals,
    )

    # Composite score is a screening score: higher values mean a row better
    # matches the requested target directions in the observed dataset.
    best_conditions = scores_df.sort_values(
        "composite_score", ascending=False, na_position="last"
    ).head(5)
    worst_conditions = scores_df.sort_values(
        "composite_score", ascending=True, na_position="last"
    ).head(5)

    scores_path = save_dataframe(
        scores_df, output_paths.processed / "multi_objective_scores.csv"
    )
    best_conditions_path = save_dataframe(
        best_conditions,
        output_paths.processed / "multi_objective_best_conditions.csv",
    )
    worst_conditions_path = save_dataframe(
        worst_conditions,
        output_paths.processed / "multi_objective_worst_conditions.csv",
    )

    figure_results = create_multi_objective_figures(
        scores_df=scores_df,
        score_columns=score_columns,
        output_paths=output_paths,
    )

    report_text = build_multi_objective_process_report(
        input_path=input_path,
        output_paths=output_paths,
        cleaned_data_path=cleaned_data_path,
        scores_path=scores_path,
        best_conditions_path=best_conditions_path,
        worst_conditions_path=worst_conditions_path,
        target_columns=target_columns,
        goals=validated_goals,
        score_columns=score_columns,
        df=df,
        best_conditions=best_conditions,
        worst_conditions=worst_conditions,
        figure_results=figure_results,
    )
    report_path = save_text_report(
        report_text, output_paths.reports / "process_report.md"
    )

    return {
        "cleaned_data": cleaned_data_path,
        "report": report_path,
        "multi_objective_scores": scores_path,
    }


def run_process_analysis(
    df: pd.DataFrame,
    input_path: Path,
    target: str | None,
    output_paths: OutputPaths,
    goal: str = "maximize",
    targets: list[str] | None = None,
    goals: list[str] | None = None,
) -> dict[str, Path]:
    """Analyze process-condition candidates based on the target column."""
    if targets is not None:
        return run_multi_objective_process_analysis(
            df=df,
            input_path=input_path,
            output_paths=output_paths,
            targets=targets,
            goals=goals,
        )

    target_name = target or DEFAULT_PROCESS_TARGET
    try:
        target_column = prepare_target_column(target_name, df)
    except ValueError as exc:
        if target is None:
            raise ValueError(
                "Process mode needs a numeric target column. "
                f"No --target was provided, so `{DEFAULT_PROCESS_TARGET}` was used, "
                "but that column was not available or not numeric. "
                "Please provide a valid target with --target."
            ) from exc
        raise

    cleaned_data_path = save_cleaned_data(df, output_paths)

    # Top and bottom rows are simple candidates based only on observed target
    # values. This is useful for screening, but it is not a real optimization.
    best_ascending = goal == "minimize"
    best_conditions = df.sort_values(
        target_column, ascending=best_ascending, na_position="last"
    ).head(5)
    worst_conditions = df.sort_values(
        target_column, ascending=not best_ascending, na_position="last"
    ).head(5)

    numeric_columns = get_numeric_columns(df)
    target_ranking = build_target_correlation_ranking(
        df, numeric_columns, target_column
    )
    material_summary = calculate_material_target_mean(df, target_column)
    temperature_summary = calculate_temperature_target_mean(df, target_column)
    figure_results = create_process_figures(
        df=df,
        target_column=target_column,
        material_summary=material_summary,
        temperature_summary=temperature_summary,
        output_paths=output_paths,
    )

    best_conditions_path = save_dataframe(
        best_conditions, output_paths.processed / "best_conditions.csv"
    )
    worst_conditions_path = save_dataframe(
        worst_conditions, output_paths.processed / "worst_conditions.csv"
    )
    ranking_path = save_dataframe(
        target_ranking, output_paths.processed / "target_correlation_ranking.csv"
    )

    material_summary_path = None
    if not material_summary.empty:
        material_summary_path = save_dataframe(
            material_summary, output_paths.processed / "material_target_summary.csv"
        )

    temperature_summary_path = None
    if not temperature_summary.empty:
        temperature_summary_path = save_dataframe(
            temperature_summary,
            output_paths.processed / "temperature_target_summary.csv",
        )

    report_text = build_process_report(
        input_path=input_path,
        output_paths=output_paths,
        cleaned_data_path=cleaned_data_path,
        target_column=target_column,
        goal=goal,
        best_conditions_path=best_conditions_path,
        worst_conditions_path=worst_conditions_path,
        ranking_path=ranking_path,
        material_summary_path=material_summary_path,
        temperature_summary_path=temperature_summary_path,
        df=df,
        best_conditions=best_conditions,
        worst_conditions=worst_conditions,
        target_ranking=target_ranking,
        material_summary=material_summary,
        temperature_summary=temperature_summary,
        figure_results=figure_results,
    )
    report_path = save_text_report(
        report_text, output_paths.reports / "process_report.md"
    )
    return {"cleaned_data": cleaned_data_path, "report": report_path}
