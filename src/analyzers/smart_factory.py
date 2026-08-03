"""Smart-factory anomaly detection mode."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import OutputPaths
from io_utils import save_cleaned_data, save_dataframe, save_text_report
from preprocessing import get_numeric_columns
from reports import build_smart_factory_report
from visualization import create_smart_factory_figures


def prepare_smart_factory_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Convert timestamp to datetime and sort the data by time when possible."""
    prepared_df = df.copy()

    if "timestamp" in prepared_df.columns:
        prepared_df["timestamp"] = pd.to_datetime(
            prepared_df["timestamp"], errors="coerce"
        )
        prepared_df = prepared_df.sort_values("timestamp", na_position="last")
        prepared_df = prepared_df.reset_index(drop=True)

    return prepared_df


def calculate_numeric_mean_std(
    df: pd.DataFrame, numeric_columns: list[str]
) -> pd.DataFrame:
    """Calculate mean and standard deviation for each numeric column."""
    if not numeric_columns:
        return pd.DataFrame(columns=["column", "mean", "std"])

    rows = []
    for column in numeric_columns:
        rows.append(
            {
                "column": column,
                "mean": df[column].mean(),
                "std": df[column].std(),
            }
        )
    return pd.DataFrame(rows)


def _smart_factory_mode_column(df: pd.DataFrame) -> str | None:
    for column in ("operating_mode", "mode", "recipe_id", "machine_id"):
        if column in df.columns:
            return column
    return None


def create_anomaly_log(
    df: pd.DataFrame,
    numeric_columns: list[str],
    *,
    minimum_history: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create mode-aware robust anomaly flags with explicit readiness evidence."""
    anomaly_log = df.copy()
    summary_rows: list[dict[str, object]] = []
    anomaly_columns: list[str] = []
    mode_column = _smart_factory_mode_column(df)
    groups = (
        list(df.groupby(mode_column, dropna=False, sort=False))
        if mode_column
        else [("all", df)]
    )

    for column in numeric_columns:
        anomaly_column = f"{column}_anomaly"
        anomaly_log[anomaly_column] = False
        anomaly_columns.append(anomaly_column)
        for mode_value, group in groups:
            series = group[column].dropna()
            count = int(series.shape[0])
            mean_value = series.mean()
            std_value = series.std()
            median_value = series.median()
            mad = float((series - median_value).abs().median()) if count else float("nan")
            robust_sigma = 1.4826 * mad if pd.notna(mad) else float("nan")
            lower_bound = mean_value - 3 * std_value
            upper_bound = mean_value + 3 * std_value
            robust_lower = median_value - 3 * robust_sigma
            robust_upper = median_value + 3 * robust_sigma
            history_ready = count >= minimum_history and pd.notna(robust_sigma) and robust_sigma > 0
            lag1 = float(series.autocorr(lag=1)) if count >= 3 else float("nan")
            first_half = series.iloc[: max(1, count // 2)]
            second_half = series.iloc[max(1, count // 2) :]
            mean_shift = (
                abs(float(first_half.mean()) - float(second_half.mean()))
                if len(second_half)
                else float("nan")
            )
            stationarity_warning = bool(
                pd.notna(std_value)
                and std_value > 0
                and pd.notna(mean_shift)
                and mean_shift > std_value
            )
            if history_ready:
                mask = (df.index.isin(group.index)) & (
                    (df[column] < robust_lower) | (df[column] > robust_upper)
                )
                anomaly_log.loc[mask, anomaly_column] = True
            summary_rows.append(
                {
                    "column": column,
                    "mode_column": mode_column or "",
                    "mode_value": mode_value,
                    "observation_count": count,
                    "minimum_history": minimum_history,
                    "history_ready": history_ready,
                    "mean": mean_value,
                    "std": std_value,
                    "median": median_value,
                    "mad": mad,
                    "robust_sigma": robust_sigma,
                    "lower_3sigma": lower_bound,
                    "upper_3sigma": upper_bound,
                    "lower_robust": robust_lower,
                    "upper_robust": robust_upper,
                    "lag1_autocorrelation": lag1,
                    "stationarity_warning": stationarity_warning,
                    "anomaly_count": int(anomaly_log.loc[group.index, anomaly_column].sum()),
                    "scientific_status": "diagnostic_only",
                }
            )

    if anomaly_columns:
        anomaly_log["any_anomaly"] = anomaly_log[anomaly_columns].any(axis=1)
    else:
        anomaly_log["any_anomaly"] = False
    return anomaly_log, pd.DataFrame(summary_rows)


def select_high_defect_points(df: pd.DataFrame) -> pd.DataFrame:
    """Return the five rows with the highest defect_rate when available."""
    if "defect_rate" not in df.columns:
        return df.head(0).copy()
    if not pd.api.types.is_numeric_dtype(df["defect_rate"]):
        return df.head(0).copy()

    return df.sort_values("defect_rate", ascending=False, na_position="last").head(5)


def select_low_yield_points(df: pd.DataFrame) -> pd.DataFrame:
    """Return the five rows with the lowest yield_percent when available."""
    if "yield_percent" not in df.columns:
        return df.head(0).copy()
    if not pd.api.types.is_numeric_dtype(df["yield_percent"]):
        return df.head(0).copy()

    return df.sort_values("yield_percent", ascending=True, na_position="last").head(5)


def run_smart_factory_analysis(
    df: pd.DataFrame,
    input_path: Path,
    target: str | None,
    output_paths: OutputPaths,
) -> dict[str, Path]:
    """Run smart-factory anomaly detection for process log data."""
    del target

    prepared_df = prepare_smart_factory_dataframe(df)
    cleaned_data_path = save_cleaned_data(prepared_df, output_paths)
    numeric_columns = get_numeric_columns(prepared_df)
    numeric_summary = calculate_numeric_mean_std(prepared_df, numeric_columns)
    anomaly_log, anomaly_summary = create_anomaly_log(prepared_df, numeric_columns)
    high_defect_points = select_high_defect_points(prepared_df)
    low_yield_points = select_low_yield_points(prepared_df)
    figure_results = create_smart_factory_figures(anomaly_log, output_paths)

    anomaly_log_path = save_dataframe(
        anomaly_log, output_paths.processed / "anomaly_log.csv"
    )
    anomaly_summary_path = save_dataframe(
        anomaly_summary, output_paths.processed / "anomaly_readiness.csv"
    )
    high_defect_path = save_dataframe(
        high_defect_points, output_paths.processed / "high_defect_points.csv"
    )
    low_yield_path = save_dataframe(
        low_yield_points, output_paths.processed / "low_yield_points.csv"
    )

    report_text = build_smart_factory_report(
        input_path=input_path,
        output_paths=output_paths,
        cleaned_data_path=cleaned_data_path,
        anomaly_log_path=anomaly_log_path,
        high_defect_path=high_defect_path,
        low_yield_path=low_yield_path,
        df=prepared_df,
        numeric_summary=numeric_summary,
        anomaly_summary=anomaly_summary,
        high_defect_points=high_defect_points,
        low_yield_points=low_yield_points,
        figure_results=figure_results,
    )
    report_path = save_text_report(
        report_text, output_paths.reports / "smart_factory_report.md"
    )
    return {
        "cleaned_data": cleaned_data_path,
        "report": report_path,
        "anomaly_readiness": anomaly_summary_path,
    }
