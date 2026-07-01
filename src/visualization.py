"""Matplotlib-based visualization helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import OutputPaths
from io_utils import display_path, safe_file_stem


FIGURE_COLUMN_MISSING_MESSAGE = (
    "\ud574\ub2f9 \uceec\ub7fc\uc774 \uc5c6\uc5b4 "
    "\uc0dd\uc131\ud558\uc9c0 \uc54a\uc74c"
)
FIGURE_NON_NUMERIC_MESSAGE = (
    "\ud574\ub2f9 \uceec\ub7fc\uc774 \uc22b\uc790\ud615\uc774 "
    "\uc544\ub2c8\ub77c \uc0dd\uc131\ud558\uc9c0 \uc54a\uc74c"
)
FIGURE_NO_VALID_DATA_MESSAGE = (
    "\uadf8\ub798\ud504\uc5d0 \uc0ac\uc6a9\ud560 \uc720\ud6a8\ud55c "
    "\ub370\uc774\ud130\uac00 \uc5c6\uc5b4 \uc0dd\uc131\ud558\uc9c0 \uc54a\uc74c"
)


def get_pyplot():
    """Import matplotlib.pyplot only when plots are actually needed."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        missing_dependency = exc.name or "matplotlib"
        raise RuntimeError(
            f"Missing Python package: {missing_dependency}\n"
            "Please install the project dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    return plt


def try_get_pyplot():
    """Return matplotlib.pyplot when available, otherwise return a skip reason.

    The analysis should still run even when matplotlib is not installed in a
    lightweight execution environment. In a normal project setup,
    `pip install -r requirements.txt` enables the actual PNG output.
    """
    try:
        return get_pyplot(), None
    except RuntimeError:
        return None, "matplotlib 패키지가 없어 생성하지 않음"


def add_figure_result(
    figure_results: list[tuple[str, str]], label: str, path: Path | None, reason: str
) -> None:
    """Store one figure status line for a Markdown report."""
    if path is not None:
        figure_results.append((label, f"`{display_path(path)}`"))
    else:
        figure_results.append((label, reason))


def figure_results_to_markdown(figure_results: list[tuple[str, str]]) -> list[str]:
    """Convert figure statuses to report lines."""
    if not figure_results:
        return ["- No figures were requested."]

    return [f"- {label}: {status}" for label, status in figure_results]


def missing_or_not_numeric_reason(df: pd.DataFrame, columns: list[str]) -> str | None:
    """Return a clear reason when a required plotting column is unavailable."""
    missing_columns = [column for column in columns if column not in df.columns]
    if missing_columns:
        return FIGURE_COLUMN_MISSING_MESSAGE

    non_numeric_columns = [
        column
        for column in columns
        if not pd.api.types.is_numeric_dtype(df[column])
    ]
    if non_numeric_columns:
        return FIGURE_NON_NUMERIC_MESSAGE

    return None


def plot_scatter_if_available(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    output_path: Path,
    title: str,
    x_label: str,
    y_label: str,
) -> tuple[Path | None, str]:
    """Create a scatter plot when both columns exist and are numeric."""
    reason = missing_or_not_numeric_reason(df, [x_column, y_column])
    if reason:
        return None, reason

    plot_df = df[[x_column, y_column]].dropna()
    if plot_df.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib을 불러올 수 없어 생성하지 않음"

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(plot_df[x_column], plot_df[y_column], color="#4c78a8", alpha=0.85)
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.grid(True, linestyle="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def plot_bar_from_summary(
    summary_df: pd.DataFrame,
    x_column: str,
    y_column: str,
    output_path: Path,
    title: str,
    x_label: str,
    y_label: str,
    missing_reason: str,
) -> tuple[Path | None, str]:
    """Create a bar chart from an already calculated summary table."""
    if summary_df.empty or x_column not in summary_df.columns or y_column not in summary_df.columns:
        return None, missing_reason

    plot_df = summary_df[[x_column, y_column]].dropna()
    if plot_df.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib을 불러올 수 없어 생성하지 않음"

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(plot_df[x_column].astype(str), plot_df[y_column], color="#59a14f")
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def plot_group_mean_bar_if_available(
    df: pd.DataFrame,
    group_column: str,
    value_column: str,
    output_path: Path,
    title: str,
    x_label: str,
    y_label: str,
) -> tuple[Path | None, str]:
    """Create a bar chart of mean value by group when columns are available."""
    if group_column not in df.columns:
        return None, FIGURE_COLUMN_MISSING_MESSAGE

    reason = missing_or_not_numeric_reason(df, [value_column])
    if reason:
        return None, reason

    summary_df = (
        df[[group_column, value_column]]
        .dropna()
        .groupby(group_column, dropna=False)[value_column]
        .mean()
        .reset_index()
    )
    return plot_bar_from_summary(
        summary_df=summary_df,
        x_column=group_column,
        y_column=value_column,
        output_path=output_path,
        title=title,
        x_label=x_label,
        y_label=y_label,
        missing_reason=FIGURE_NO_VALID_DATA_MESSAGE,
    )


def plot_histogram_if_available(
    df: pd.DataFrame,
    column: str,
    output_path: Path,
    title: str,
    x_label: str,
) -> tuple[Path | None, str]:
    """Create a histogram when the requested numeric column is available."""
    reason = missing_or_not_numeric_reason(df, [column])
    if reason:
        return None, reason

    series = df[column].dropna()
    if series.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib을 불러올 수 없어 생성하지 않음"

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(series, bins=20, color="#f28e2b", edgecolor="white")
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel("Count")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def plot_time_series_if_available(
    df: pd.DataFrame,
    y_column: str,
    output_path: Path,
    title: str,
    y_label: str,
) -> tuple[Path | None, str]:
    """Create a time-series plot and mark rows where any_anomaly is True."""
    if "timestamp" not in df.columns:
        return None, FIGURE_COLUMN_MISSING_MESSAGE

    reason = missing_or_not_numeric_reason(df, [y_column])
    if reason:
        return None, reason

    plot_columns = ["timestamp", y_column]
    if "any_anomaly" in df.columns:
        plot_columns.append("any_anomaly")

    plot_df = df[plot_columns].copy()
    if "any_anomaly" not in plot_df.columns:
        plot_df["any_anomaly"] = False

    plot_df["timestamp"] = pd.to_datetime(plot_df["timestamp"], errors="coerce")
    plot_df = plot_df.dropna(subset=["timestamp", y_column])
    if plot_df.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib을 불러올 수 없어 생성하지 않음"

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(plot_df["timestamp"], plot_df[y_column], marker="o", color="#4c78a8")

    # Highlight anomaly candidates on top of the normal line plot.
    if "any_anomaly" in plot_df.columns:
        anomaly_df = plot_df[plot_df["any_anomaly"] == True]
        if not anomaly_df.empty:
            ax.scatter(
                anomaly_df["timestamp"],
                anomaly_df[y_column],
                color="#e15759",
                s=70,
                label="any_anomaly=True",
                zorder=3,
            )
            ax.legend()

    ax.set_title(title)
    ax.set_xlabel("timestamp")
    ax.set_ylabel(y_label)
    ax.grid(True, linestyle="--", alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def plot_histograms(
    df: pd.DataFrame, numeric_columns: list[str], output_paths: OutputPaths
) -> list[Path]:
    """Save one histogram image for each numeric column.

    A histogram shows the distribution of values in one column. For example, it
    can quickly show whether process temperatures are clustered around one
    recipe or spread across many settings.
    """
    if not numeric_columns:
        return []

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        # Keep the analysis running in lightweight environments where
        # matplotlib is not installed yet. Other plotting helpers use the same
        # graceful skip behavior.
        return []

    histogram_paths: list[Path] = []

    for column in numeric_columns:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(df[column].dropna(), bins=20, color="#4c78a8", edgecolor="white")
        ax.set_title(f"Histogram of {column}")
        ax.set_xlabel(column)
        ax.set_ylabel("Count")
        fig.tight_layout()

        output_path = output_paths.figures / f"histogram_{safe_file_stem(column)}.png"
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        histogram_paths.append(output_path)

    # Keep the previous combined histogram image as a convenient overview.
    columns_per_row = 3
    row_count = int(np.ceil(len(numeric_columns) / columns_per_row))
    fig, axes = plt.subplots(
        row_count,
        columns_per_row,
        figsize=(5 * columns_per_row, 4 * row_count),
        squeeze=False,
    )

    for index, column in enumerate(numeric_columns):
        row = index // columns_per_row
        col = index % columns_per_row
        ax = axes[row][col]
        ax.hist(df[column].dropna(), bins=20, color="#4c78a8", edgecolor="white")
        ax.set_title(column)
        ax.set_xlabel("Value")
        ax.set_ylabel("Count")

    # Hide empty subplot boxes when the number of columns is not a multiple of 3.
    for index in range(len(numeric_columns), row_count * columns_per_row):
        row = index // columns_per_row
        col = index % columns_per_row
        axes[row][col].axis("off")

    fig.tight_layout()
    output_path = output_paths.figures / "histograms.png"
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    histogram_paths.append(output_path)
    return histogram_paths


def plot_correlation_heatmap(
    correlation_matrix: pd.DataFrame, output_paths: OutputPaths
) -> Path | None:
    """Save a heatmap image for the correlation matrix."""
    if correlation_matrix.empty:
        return None

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None

    column_count = len(correlation_matrix.columns)
    figure_size = max(6, min(16, column_count * 0.8))
    fig, ax = plt.subplots(figsize=(figure_size, figure_size))

    image = ax.imshow(correlation_matrix, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(column_count))
    ax.set_yticks(range(column_count))
    ax.set_xticklabels(correlation_matrix.columns, rotation=45, ha="right")
    ax.set_yticklabels(correlation_matrix.columns)
    ax.set_title("Correlation Heatmap")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)

    # Small matrices are easier to read when the correlation values are printed.
    if column_count <= 12:
        for row in range(column_count):
            for col in range(column_count):
                value = correlation_matrix.iloc[row, col]
                text_color = "white" if abs(value) > 0.6 else "black"
                ax.text(
                    col,
                    row,
                    f"{value:.2f}",
                    ha="center",
                    va="center",
                    color=text_color,
                    fontsize=8,
                )

    fig.tight_layout()
    output_path = output_paths.figures / "correlation_heatmap.png"
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def create_process_figures(
    df: pd.DataFrame,
    target_column: str,
    material_summary: pd.DataFrame,
    temperature_summary: pd.DataFrame,
    output_paths: OutputPaths,
) -> list[tuple[str, str]]:
    """Create process-mode figures and collect report-friendly statuses."""
    figure_results: list[tuple[str, str]] = []

    # Scatter plots show whether the target tends to change with one process
    # condition. They are screening plots, not proof of causality.
    scatter_specs = [
        (
            "target vs process_temp_c",
            "process_temp_c",
            output_paths.figures / "process_temp_vs_target.png",
            f"{target_column} vs process_temp_c",
            "process_temp_c",
        ),
        (
            "target vs process_time_min",
            "process_time_min",
            output_paths.figures / "process_time_vs_target.png",
            f"{target_column} vs process_time_min",
            "process_time_min",
        ),
        (
            "target vs pressure_mpa",
            "pressure_mpa",
            output_paths.figures / "pressure_vs_target.png",
            f"{target_column} vs pressure_mpa",
            "pressure_mpa",
        ),
    ]

    for label, x_column, output_path, title, x_label in scatter_specs:
        path, reason = plot_scatter_if_available(
            df=df,
            x_column=x_column,
            y_column=target_column,
            output_path=output_path,
            title=title,
            x_label=x_label,
            y_label=target_column,
        )
        add_figure_result(figure_results, label, path, reason)

    mean_column = f"mean_{target_column}"
    path, reason = plot_bar_from_summary(
        summary_df=material_summary,
        x_column="material",
        y_column=mean_column,
        output_path=output_paths.figures / "material_target_mean.png",
        title=f"Mean {target_column} by material",
        x_label="material",
        y_label=f"mean_{target_column}",
        missing_reason="material 컬럼이 없어 생성하지 않음",
    )
    add_figure_result(figure_results, "material별 target 평균", path, reason)

    path, reason = plot_bar_from_summary(
        summary_df=temperature_summary,
        x_column="temperature_bin",
        y_column=mean_column,
        output_path=output_paths.figures / "temperature_bin_target_mean.png",
        title=f"Mean {target_column} by temperature bin",
        x_label="temperature_bin",
        y_label=f"mean_{target_column}",
        missing_reason="process_temp_c 컬럼이 없어 생성하지 않음",
    )
    add_figure_result(figure_results, "temperature bin별 target 평균", path, reason)

    return figure_results


def plot_composite_score_ranking(
    scores_df: pd.DataFrame, output_path: Path
) -> tuple[Path | None, str]:
    """Create a bar chart sorted by composite score."""
    if "composite_score" not in scores_df.columns:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    plot_df = scores_df.dropna(subset=["composite_score"]).sort_values(
        "composite_score", ascending=False
    )
    if plot_df.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    # Very large charts become unreadable, so keep the saved PNG focused on the
    # best-ranked rows while the CSV still keeps every row.
    max_bars = 30
    was_truncated = len(plot_df) > max_bars
    plot_df = plot_df.head(max_bars)
    labels = (
        plot_df["sample_id"].astype(str).tolist()
        if "sample_id" in plot_df.columns
        else [f"row_{index}" for index in plot_df.index]
    )

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib could not be loaded"

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(labels, plot_df["composite_score"], color="#4c78a8")
    title = "Composite Score Ranking"
    if was_truncated:
        title += " (Top 30)"
    ax.set_title(title)
    ax.set_xlabel("condition")
    ax.set_ylabel("composite_score")
    ax.set_ylim(0, 1.05)
    ax.tick_params(axis="x", rotation=35)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def plot_target_score_heatmap(
    scores_df: pd.DataFrame, score_columns: list[str], output_path: Path
) -> tuple[Path | None, str]:
    """Create a heatmap of per-target scores for each condition."""
    if not score_columns:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    plot_df = scores_df.dropna(subset=score_columns, how="all").sort_values(
        "composite_score", ascending=False, na_position="last"
    )
    if plot_df.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    max_rows = 30
    was_truncated = len(plot_df) > max_rows
    plot_df = plot_df.head(max_rows)
    score_matrix = plot_df[score_columns].to_numpy(dtype=float)
    if np.isnan(score_matrix).all():
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    labels = (
        plot_df["sample_id"].astype(str).tolist()
        if "sample_id" in plot_df.columns
        else [f"row_{index}" for index in plot_df.index]
    )
    target_labels = [
        column[len("score_") :] if column.startswith("score_") else column
        for column in score_columns
    ]

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib could not be loaded"

    masked_scores = np.ma.masked_invalid(score_matrix)
    fig_height = max(4.5, min(12, len(plot_df) * 0.35 + 2))
    fig_width = max(6, len(score_columns) * 1.4 + 3)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    image = ax.imshow(masked_scores, cmap="viridis", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(target_labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(target_labels, rotation=35, ha="right")
    ax.set_yticklabels(labels)
    title = "Target Score Heatmap"
    if was_truncated:
        title += " (Top 30)"
    ax.set_title(title)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label="score")

    # Small heatmaps are easier for beginners when the values are printed.
    if len(plot_df) <= 20 and len(score_columns) <= 8:
        for row_index in range(score_matrix.shape[0]):
            for col_index in range(score_matrix.shape[1]):
                value = score_matrix[row_index, col_index]
                if np.isnan(value):
                    continue
                text_color = "white" if value < 0.45 else "black"
                ax.text(
                    col_index,
                    row_index,
                    f"{value:.2f}",
                    ha="center",
                    va="center",
                    color=text_color,
                    fontsize=8,
                )

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def create_multi_objective_figures(
    scores_df: pd.DataFrame, score_columns: list[str], output_paths: OutputPaths
) -> list[tuple[str, str]]:
    """Create multi-objective process-screening figures."""
    figure_results: list[tuple[str, str]] = []

    path, reason = plot_composite_score_ranking(
        scores_df=scores_df,
        output_path=output_paths.figures / "composite_score_ranking.png",
    )
    add_figure_result(figure_results, "composite_score ranking", path, reason)

    path, reason = plot_target_score_heatmap(
        scores_df=scores_df,
        score_columns=score_columns,
        output_path=output_paths.figures / "target_score_heatmap.png",
    )
    add_figure_result(figure_results, "target score heatmap", path, reason)

    return figure_results


def create_reliability_figures(
    df: pd.DataFrame, output_paths: OutputPaths
) -> list[tuple[str, str]]:
    """Create reliability-mode figures and collect report-friendly statuses."""
    figure_results: list[tuple[str, str]] = []

    path, reason = plot_group_mean_bar_if_available(
        df=df,
        group_column="chip_thickness_um",
        value_column="thermal_cycle_count",
        output_path=output_paths.figures / "chip_thickness_cycle_count.png",
        title="Mean thermal_cycle_count by chip_thickness_um",
        x_label="chip_thickness_um",
        y_label="mean thermal_cycle_count",
    )
    add_figure_result(
        figure_results,
        "chip_thickness_um별 mean thermal_cycle_count",
        path,
        reason,
    )

    path, reason = plot_group_mean_bar_if_available(
        df=df,
        group_column="substrate_thickness_um",
        value_column="thermal_cycle_count",
        output_path=output_paths.figures / "substrate_thickness_cycle_count.png",
        title="Mean thermal_cycle_count by substrate_thickness_um",
        x_label="substrate_thickness_um",
        y_label="mean thermal_cycle_count",
    )
    add_figure_result(
        figure_results,
        "substrate_thickness_um별 mean thermal_cycle_count",
        path,
        reason,
    )

    path, reason = plot_histogram_if_available(
        df=df,
        column="resistance_change_percent",
        output_path=output_paths.figures / "resistance_change_histogram.png",
        title="Histogram of resistance_change_percent",
        x_label="resistance_change_percent",
    )
    add_figure_result(
        figure_results,
        "resistance_change_percent histogram",
        path,
        reason,
    )

    return figure_results


def create_smart_factory_figures(
    anomaly_log: pd.DataFrame, output_paths: OutputPaths
) -> list[tuple[str, str]]:
    """Create smart-factory time-series figures and collect statuses."""
    figure_results: list[tuple[str, str]] = []

    path, reason = plot_time_series_if_available(
        df=anomaly_log,
        y_column="defect_rate",
        output_path=output_paths.figures / "defect_rate_time_series.png",
        title="defect_rate time series",
        y_label="defect_rate",
    )
    add_figure_result(
        figure_results,
        "defect_rate time series",
        path,
        reason,
    )

    path, reason = plot_time_series_if_available(
        df=anomaly_log,
        y_column="yield_percent",
        output_path=output_paths.figures / "yield_percent_time_series.png",
        title="yield_percent time series",
        y_label="yield_percent",
    )
    add_figure_result(
        figure_results,
        "yield_percent time series",
        path,
        reason,
    )

    path, reason = plot_time_series_if_available(
        df=anomaly_log,
        y_column="temperature_c",
        output_path=output_paths.figures / "temperature_time_series.png",
        title="temperature_c time series",
        y_label="temperature_c",
    )
    add_figure_result(
        figure_results,
        "temperature_c time series",
        path,
        reason,
    )

    return figure_results


def get_control_chart_x_values(spc_df: pd.DataFrame) -> tuple[pd.Series, str]:
    """Choose a readable x-axis for SPC charts.

    When timestamp exists, the chart follows time. Otherwise, it uses the
    original row order after cleaning and sorting.
    """
    if "timestamp" in spc_df.columns:
        timestamps = pd.to_datetime(spc_df["timestamp"], errors="coerce")
        if timestamps.notna().any():
            return timestamps, "timestamp"

    return spc_df["spc_order"], "row order"


def plot_i_chart(
    spc_df: pd.DataFrame,
    target_column: str,
    center_line: float,
    i_ucl: float,
    i_lcl: float,
    output_path: Path,
) -> tuple[Path | None, str]:
    """Create an Individuals chart for one numeric target column."""
    if spc_df.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib could not be loaded"

    x_values, x_label = get_control_chart_x_values(spc_df)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(
        x_values,
        spc_df[target_column],
        marker="o",
        color="#4c78a8",
        label=target_column,
    )

    # Highlight points outside the control limits so a beginner can quickly
    # see which measurements need follow-up.
    violation_df = spc_df[spc_df["i_chart_violation"] == True]
    if not violation_df.empty:
        violation_x, _ = get_control_chart_x_values(violation_df)
        ax.scatter(
            violation_x,
            violation_df[target_column],
            color="#e15759",
            s=70,
            label="I chart violation",
            zorder=3,
        )

    ax.axhline(center_line, color="#59a14f", linestyle="-", label="Center line")
    if pd.notna(i_ucl):
        ax.axhline(i_ucl, color="#e15759", linestyle="--", label="I UCL")
    if pd.notna(i_lcl):
        ax.axhline(i_lcl, color="#e15759", linestyle="--", label="I LCL")

    ax.set_title(f"I Chart of {target_column}")
    ax.set_xlabel(x_label)
    ax.set_ylabel(target_column)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def plot_moving_range_chart(
    spc_df: pd.DataFrame,
    mr_bar: float,
    mr_ucl: float,
    mr_lcl: float,
    output_path: Path,
) -> tuple[Path | None, str]:
    """Create a moving range chart for consecutive target differences."""
    plot_df = spc_df.dropna(subset=["moving_range"])
    if plot_df.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib could not be loaded"

    x_values, x_label = get_control_chart_x_values(plot_df)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(
        x_values,
        plot_df["moving_range"],
        marker="o",
        color="#f28e2b",
        label="moving range",
    )

    violation_df = plot_df[plot_df["mr_chart_violation"] == True]
    if not violation_df.empty:
        violation_x, _ = get_control_chart_x_values(violation_df)
        ax.scatter(
            violation_x,
            violation_df["moving_range"],
            color="#e15759",
            s=70,
            label="MR chart violation",
            zorder=3,
        )

    if pd.notna(mr_bar):
        ax.axhline(mr_bar, color="#59a14f", linestyle="-", label="MR center line")
    if pd.notna(mr_ucl):
        ax.axhline(mr_ucl, color="#e15759", linestyle="--", label="MR UCL")
    ax.axhline(mr_lcl, color="#e15759", linestyle="--", label="MR LCL")

    ax.set_title("Moving Range Chart")
    ax.set_xlabel(x_label)
    ax.set_ylabel("moving_range")
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def plot_capability_histogram(
    spc_df: pd.DataFrame,
    target_column: str,
    lsl: float | None,
    usl: float | None,
    output_path: Path,
) -> tuple[Path | None, str]:
    """Create a target histogram with specification limits."""
    if lsl is None or usl is None:
        return None, "LSL 또는 USL이 없어 생성하지 않음"

    series = spc_df[target_column].dropna()
    if series.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib could not be loaded"

    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.hist(series, bins=20, color="#4c78a8", edgecolor="white", alpha=0.85)
    ax.axvline(lsl, color="#e15759", linestyle="--", label="LSL")
    ax.axvline(usl, color="#e15759", linestyle="--", label="USL")
    ax.set_title(f"Capability Histogram of {target_column}")
    ax.set_xlabel(target_column)
    ax.set_ylabel("Count")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def create_spc_figures(
    spc_df: pd.DataFrame,
    target_column: str,
    summary: dict[str, float],
    output_paths: OutputPaths,
    lsl: float | None,
    usl: float | None,
) -> list[tuple[str, str]]:
    """Create SPC figures and collect report-friendly statuses."""
    figure_results: list[tuple[str, str]] = []

    path, reason = plot_i_chart(
        spc_df=spc_df,
        target_column=target_column,
        center_line=summary["center_line"],
        i_ucl=summary["i_ucl"],
        i_lcl=summary["i_lcl"],
        output_path=output_paths.figures / "i_chart.png",
    )
    add_figure_result(figure_results, "I chart", path, reason)

    path, reason = plot_moving_range_chart(
        spc_df=spc_df,
        mr_bar=summary["mr_bar"],
        mr_ucl=summary["mr_ucl"],
        mr_lcl=summary["mr_lcl"],
        output_path=output_paths.figures / "moving_range_chart.png",
    )
    add_figure_result(figure_results, "Moving range chart", path, reason)

    path, reason = plot_capability_histogram(
        spc_df=spc_df,
        target_column=target_column,
        lsl=lsl,
        usl=usl,
        output_path=output_paths.figures / "capability_histogram.png",
    )
    add_figure_result(figure_results, "Capability histogram", path, reason)

    return figure_results


def plot_actual_vs_predicted(
    predictions_df: pd.DataFrame,
    output_path: Path,
) -> tuple[Path | None, str]:
    """Create an actual-vs-predicted scatter plot for regression results."""
    required_columns = ["actual", "predicted"]
    if any(column not in predictions_df.columns for column in required_columns):
        return None, FIGURE_COLUMN_MISSING_MESSAGE

    plot_df = predictions_df[required_columns].dropna()
    if plot_df.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib could not be loaded"

    min_value = min(plot_df["actual"].min(), plot_df["predicted"].min())
    max_value = max(plot_df["actual"].max(), plot_df["predicted"].max())

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(plot_df["actual"], plot_df["predicted"], color="#4c78a8", alpha=0.85)
    ax.plot(
        [min_value, max_value],
        [min_value, max_value],
        color="#e15759",
        linestyle="--",
        label="perfect prediction",
    )
    ax.set_title("Actual vs Predicted")
    ax.set_xlabel("actual")
    ax.set_ylabel("predicted")
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def plot_feature_importance(
    feature_importance_df: pd.DataFrame,
    output_path: Path,
) -> tuple[Path | None, str]:
    """Create a horizontal bar chart of model feature importance."""
    required_columns = ["feature", "importance"]
    if any(column not in feature_importance_df.columns for column in required_columns):
        return None, FIGURE_COLUMN_MISSING_MESSAGE

    plot_df = feature_importance_df[required_columns].dropna()
    if plot_df.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    plot_df = plot_df.sort_values("importance", ascending=True)

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib could not be loaded"

    fig_height = max(4, len(plot_df) * 0.45 + 1.5)
    fig, ax = plt.subplots(figsize=(8, fig_height))
    ax.barh(plot_df["feature"], plot_df["importance"], color="#59a14f")
    ax.set_title("Feature Importance")
    ax.set_xlabel("importance")
    ax.set_ylabel("feature")
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def create_simulation_figures(
    predictions_df: pd.DataFrame,
    feature_importance_df: pd.DataFrame,
    output_paths: OutputPaths,
) -> list[tuple[str, str]]:
    """Create simulation-mode figures and collect report-friendly statuses."""
    figure_results: list[tuple[str, str]] = []

    path, reason = plot_actual_vs_predicted(
        predictions_df=predictions_df,
        output_path=output_paths.figures / "actual_vs_predicted.png",
    )
    add_figure_result(figure_results, "Actual vs predicted", path, reason)

    path, reason = plot_feature_importance(
        feature_importance_df=feature_importance_df,
        output_path=output_paths.figures / "feature_importance.png",
    )
    add_figure_result(figure_results, "Feature importance", path, reason)

    return figure_results


def plot_scenario_prediction_ranking(
    scenario_ranking_df: pd.DataFrame,
    predicted_column: str,
    output_path: Path,
) -> tuple[Path | None, str]:
    """Create a ranking bar chart for scenario what-if predictions."""
    required_columns = ["scenario_id", predicted_column]
    if any(column not in scenario_ranking_df.columns for column in required_columns):
        return None, FIGURE_COLUMN_MISSING_MESSAGE

    plot_df = scenario_ranking_df[required_columns].dropna()
    if plot_df.empty:
        return None, FIGURE_NO_VALID_DATA_MESSAGE

    max_bars = 30
    was_truncated = len(plot_df) > max_bars
    plot_df = plot_df.head(max_bars)

    plt, matplotlib_reason = try_get_pyplot()
    if plt is None:
        return None, matplotlib_reason or "matplotlib could not be loaded"

    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(
        plot_df["scenario_id"].astype(str),
        plot_df[predicted_column],
        color="#4c78a8",
    )
    title = "Scenario Prediction Ranking"
    if was_truncated:
        title += " (Top 30)"
    ax.set_title(title)
    ax.set_xlabel("scenario_id")
    ax.set_ylabel(predicted_column)
    ax.tick_params(axis="x", rotation=35)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path, "created"


def create_scenario_prediction_figures(
    scenario_ranking_df: pd.DataFrame,
    predicted_column: str,
    output_paths: OutputPaths,
) -> list[tuple[str, str]]:
    """Create scenario what-if prediction figures."""
    figure_results: list[tuple[str, str]] = []

    path, reason = plot_scenario_prediction_ranking(
        scenario_ranking_df=scenario_ranking_df,
        predicted_column=predicted_column,
        output_path=output_paths.figures / "scenario_prediction_ranking.png",
    )
    add_figure_result(figure_results, "Scenario prediction ranking", path, reason)

    return figure_results
