"""Statistical Process Control analysis mode."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import OutputPaths
from io_utils import save_cleaned_data, save_dataframe, save_text_report
from preprocessing import clean_column_name
from reports import build_spc_report
from visualization import create_spc_figures


def validate_spc_target(target: str | None, df: pd.DataFrame) -> str:
    """Clean and validate the numeric column used for SPC analysis."""
    if target is None:
        raise ValueError(
            "SPC mode needs a numeric target column. Please provide --target."
        )

    target_column = clean_column_name(target)
    if target_column not in df.columns:
        available_columns = ", ".join(df.columns)
        raise ValueError(
            "SPC mode could not find the target column.\n"
            f"Requested target: {target}\n"
            f"After column-name cleanup, it was searched as: {target_column}\n"
            f"Available columns are: {available_columns}"
        )

    if not pd.api.types.is_numeric_dtype(df[target_column]):
        raise ValueError(
            "SPC mode needs a numeric target column.\n"
            f"Column exists but is not numeric: {target_column}"
        )

    return target_column


def prepare_spc_dataframe(df: pd.DataFrame, target_column: str) -> pd.DataFrame:
    """Sort by timestamp when available and keep valid target values.

    SPC charts depend on measurement order. Timestamp order is preferred for
    process logs. If there is no timestamp column, the existing row order is
    used as the measurement sequence.
    """
    prepared_df = df.copy()

    if "timestamp" in prepared_df.columns:
        prepared_df["timestamp"] = pd.to_datetime(
            prepared_df["timestamp"], errors="coerce"
        )
        prepared_df = prepared_df.sort_values("timestamp", na_position="last")

    prepared_df = prepared_df.dropna(subset=[target_column]).reset_index(drop=True)
    if prepared_df.empty:
        raise ValueError(
            f"SPC mode could not run because `{target_column}` has no valid values."
        )

    # spc_order is a simple 1-based sequence number used when timestamp is not
    # available and is also useful when reading output CSV files.
    prepared_df["spc_order"] = np.arange(1, len(prepared_df) + 1)
    prepared_df["moving_range"] = prepared_df[target_column].diff().abs()
    return prepared_df


def calculate_spc_summary(
    spc_df: pd.DataFrame, target_column: str
) -> dict[str, float]:
    """Calculate Individuals and Moving Range chart limits."""
    center_line = spc_df[target_column].mean()
    mr_bar = spc_df["moving_range"].mean(skipna=True)
    sigma_estimate = mr_bar / 1.128 if pd.notna(mr_bar) else np.nan

    if pd.notna(sigma_estimate):
        i_ucl = center_line + 3 * sigma_estimate
        i_lcl = center_line - 3 * sigma_estimate
    else:
        i_ucl = np.nan
        i_lcl = np.nan

    mr_ucl = 3.267 * mr_bar if pd.notna(mr_bar) else np.nan
    mr_lcl = 0.0

    return {
        "center_line": center_line,
        "mr_bar": mr_bar,
        "sigma_estimate": sigma_estimate,
        "i_ucl": i_ucl,
        "i_lcl": i_lcl,
        "mr_ucl": mr_ucl,
        "mr_lcl": mr_lcl,
    }


def add_spc_violation_flags(
    spc_df: pd.DataFrame, target_column: str, summary: dict[str, float]
) -> pd.DataFrame:
    """Mark rows that fall outside I chart or moving range limits."""
    flagged_df = spc_df.copy()

    if pd.notna(summary["i_ucl"]) and pd.notna(summary["i_lcl"]):
        flagged_df["i_chart_violation"] = (
            (flagged_df[target_column] > summary["i_ucl"])
            | (flagged_df[target_column] < summary["i_lcl"])
        )
    else:
        flagged_df["i_chart_violation"] = False

    if pd.notna(summary["mr_ucl"]):
        flagged_df["mr_chart_violation"] = (
            flagged_df["moving_range"] > summary["mr_ucl"]
        )
    else:
        flagged_df["mr_chart_violation"] = False

    flagged_df["any_spc_violation"] = (
        flagged_df["i_chart_violation"] | flagged_df["mr_chart_violation"]
    )
    return flagged_df


def build_spc_summary_table(
    target_column: str, row_count: int, summary: dict[str, float]
) -> pd.DataFrame:
    """Turn SPC summary values into a simple CSV-friendly table."""
    rows = [
        {"metric": "target_column", "value": target_column},
        {"metric": "row_count", "value": row_count},
        {"metric": "center_line", "value": summary["center_line"]},
        {"metric": "mr_bar", "value": summary["mr_bar"]},
        {"metric": "sigma_estimate", "value": summary["sigma_estimate"]},
        {"metric": "i_ucl", "value": summary["i_ucl"]},
        {"metric": "i_lcl", "value": summary["i_lcl"]},
        {"metric": "mr_ucl", "value": summary["mr_ucl"]},
        {"metric": "mr_lcl", "value": summary["mr_lcl"]},
    ]
    return pd.DataFrame(rows)



def assess_capability_readiness(
    spc_df: pd.DataFrame,
    *,
    lsl: float | None,
    usl: float | None,
    minimum_observations: int = 20,
) -> dict[str, object]:
    """Assess whether Cp/Cpk should be reported for the observed sequence."""
    reasons: list[str] = []
    if lsl is None or usl is None:
        reasons.append("specification_limits_not_provided")
    elif usl <= lsl:
        reasons.append("invalid_specification_limits")
    if len(spc_df) < minimum_observations:
        reasons.append("insufficient_observations")
    violation_count = int(spc_df.get("any_spc_violation", pd.Series(dtype=bool)).sum())
    if violation_count:
        reasons.append("process_not_in_statistical_control")
    if "timestamp" in spc_df.columns and spc_df["timestamp"].isna().any():
        reasons.append("invalid_or_missing_timestamp_order")
    return {
        "ready": not reasons,
        "status": "ready" if not reasons else "not_ready",
        "reason_codes": reasons,
        "minimum_observations": minimum_observations,
        "observed_count": int(len(spc_df)),
        "control_violation_count": violation_count,
        "measurement_system_reviewed": False,
        "distribution_assumption_reviewed": False,
        "note": (
            "Cp/Cpk is a diagnostic only. Measurement-system adequacy, distribution, "
            "subgrouping, and specification provenance still require domain review."
        ),
    }

def calculate_process_capability(
    lsl: float | None,
    usl: float | None,
    mean_value: float,
    sigma_estimate: float,
    readiness: dict[str, object] | None = None,
) -> pd.DataFrame:
    """Calculate Cp and Cpk when specification limits are provided."""
    if readiness is not None and not bool(readiness.get("ready")):
        return pd.DataFrame(
            [
                {"metric": "capability_status", "value": "not_ready"},
                {
                    "metric": "capability_reason_codes",
                    "value": ";".join(str(x) for x in readiness.get("reason_codes", [])),
                },
                {"metric": "cp", "value": np.nan},
                {"metric": "cpk", "value": np.nan},
            ]
        )

    if lsl is None or usl is None:
        return pd.DataFrame(
            [{"metric": "message", "value": "spec limits not provided"}]
        )

    if usl <= lsl:
        raise ValueError(
            "SPC capability analysis needs USL to be greater than LSL."
        )

    if pd.isna(sigma_estimate) or sigma_estimate == 0:
        return pd.DataFrame(
            [
                {"metric": "lsl", "value": lsl},
                {"metric": "usl", "value": usl},
                {
                    "metric": "message",
                    "value": "sigma estimate unavailable; Cp/Cpk not calculated",
                },
            ]
        )

    cp = (usl - lsl) / (6 * sigma_estimate)
    cpk = min(
        (usl - mean_value) / (3 * sigma_estimate),
        (mean_value - lsl) / (3 * sigma_estimate),
    )

    return pd.DataFrame(
        [
            {"metric": "lsl", "value": lsl},
            {"metric": "usl", "value": usl},
            {"metric": "cp", "value": cp},
            {"metric": "cpk", "value": cpk},
        ]
    )


def run_spc_analysis(
    df: pd.DataFrame,
    input_path: Path,
    target: str | None,
    output_paths: OutputPaths,
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, Path]:
    """Run SPC control chart and process capability analysis."""
    target_column = validate_spc_target(target, df)
    spc_df = prepare_spc_dataframe(df, target_column)
    summary = calculate_spc_summary(spc_df, target_column)
    spc_df = add_spc_violation_flags(spc_df, target_column, summary)

    violation_df = spc_df[spc_df["any_spc_violation"] == True].copy()
    summary_df = build_spc_summary_table(
        target_column=target_column,
        row_count=len(spc_df),
        summary=summary,
    )
    capability_readiness = assess_capability_readiness(
        spc_df, lsl=lsl, usl=usl
    )
    capability_df = calculate_process_capability(
        lsl=lsl,
        usl=usl,
        mean_value=summary["center_line"],
        sigma_estimate=summary["sigma_estimate"],
        readiness=capability_readiness,
    )

    cleaned_data_path = save_cleaned_data(spc_df, output_paths)
    summary_path = save_dataframe(
        summary_df, output_paths.processed / "spc_summary.csv"
    )
    violations_path = save_dataframe(
        violation_df, output_paths.processed / "control_violations.csv"
    )
    capability_path = save_dataframe(
        capability_df, output_paths.processed / "process_capability.csv"
    )
    readiness_path = save_dataframe(
        pd.DataFrame(
            [
                {
                    **{k: v for k, v in capability_readiness.items() if k != "reason_codes"},
                    "reason_codes": ";".join(capability_readiness["reason_codes"]),
                }
            ]
        ),
        output_paths.processed / "capability_readiness.csv",
    )

    figure_results = create_spc_figures(
        spc_df=spc_df,
        target_column=target_column,
        summary=summary,
        output_paths=output_paths,
        lsl=lsl,
        usl=usl,
    )

    report_text = build_spc_report(
        input_path=input_path,
        output_paths=output_paths,
        cleaned_data_path=cleaned_data_path,
        summary_path=summary_path,
        violations_path=violations_path,
        capability_path=capability_path,
        target_column=target_column,
        row_count=len(spc_df),
        summary=summary,
        capability_df=capability_df,
        violation_count=int(spc_df["any_spc_violation"].sum()),
        figure_results=figure_results,
    )
    report_path = save_text_report(
        report_text, output_paths.reports / "spc_report.md"
    )

    return {
        "cleaned_data": cleaned_data_path,
        "report": report_path,
        "capability_readiness": readiness_path,
    }
