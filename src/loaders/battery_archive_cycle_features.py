"""Battery Archive cycle quality checks and conservative derived metrics.

This module works from the v1.1.3b normalized cycle table. It does not read raw
zip files, modify normalized source rows, or run analyzer modes. Derived values
are source-traceable screening features, not battery degradation forecasts.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


SUPPORTED_CAPACITY_UNITS = {"Ah"}
SUPPORTED_ENERGY_UNITS = {"Wh"}
BASELINE_WINDOW = 5
BASELINE_METHOD = "first_5_valid_discharge_capacity_median_by_cycle_index"
QUALITY_DELIMITER = ";"
HIGH_RETENTION_WARNING_PCT = 120.0
PERSISTENT_THRESHOLD_WINDOW = 3

PROVENANCE_COLUMNS = [
    "zip_file",
    "internal_csv_path",
    "file_name",
    "source",
    "cell_id",
    "chemistry",
    "form_factor",
    "temperature_C",
    "soc_min_pct",
    "soc_max_pct",
    "soc_window",
    "charge_c_rate",
    "discharge_c_rate",
    "protocol_label",
    "schema_fingerprint",
    "source_row_number",
]

REQUIRED_NORMALIZED_COLUMNS = [
    "zip_file",
    "internal_csv_path",
    "file_name",
    "source_row_number",
    "cycle_index",
    "charge_capacity",
    "charge_capacity_unit",
    "discharge_capacity",
    "discharge_capacity_unit",
    "charge_energy",
    "charge_energy_unit",
    "discharge_energy",
    "discharge_energy_unit",
]

QUALITY_OUTPUT_COLUMNS = [
    "cycle_series_id",
    "quality_status",
    "quality_issue_count",
    "quality_issues",
    "initial_discharge_capacity",
    "baseline_capacity_unit",
    "baseline_cycle_count",
    "baseline_method",
    "baseline_status",
    "capacity_retention",
    "capacity_retention_pct",
    "soh_capacity_proxy",
    "soh_capacity_proxy_pct",
]

SERIES_SUMMARY_COLUMNS = [
    "cycle_series_id",
    "zip_file",
    "internal_csv_path",
    "file_name",
    "source",
    "cell_id",
    "chemistry",
    "form_factor",
    "temperature_C",
    "soc_window",
    "charge_c_rate",
    "discharge_c_rate",
    "capacity_unit",
    "total_rows",
    "valid_cycle_rows",
    "warning_rows",
    "invalid_rows",
    "min_cycle_index",
    "max_cycle_index",
    "baseline_capacity",
    "baseline_cycle_count",
    "baseline_method",
    "baseline_status",
    "initial_retention_pct",
    "final_retention_pct",
    "min_retention_pct",
    "first_cycle_below_80pct",
    "persistent_cycle_below_80pct",
    "first_cycle_below_70pct",
    "persistent_cycle_below_70pct",
    "reached_80pct_threshold",
    "reached_70pct_threshold",
    "observed_censored_80pct",
    "observed_censored_70pct",
    "has_duplicate_cycle_index",
    "has_nonmonotonic_cycle_index",
    "mixed_capacity_unit",
    "data_quality_status",
    "data_quality_message",
]

QUALITY_SUMMARY_COLUMNS = ["metric", "count", "percentage", "description"]

INVALID_ISSUES = {
    "missing_cycle_index",
    "nonpositive_cycle_index",
    "missing_discharge_capacity",
    "negative_discharge_capacity",
    "negative_charge_capacity",
    "negative_discharge_energy",
    "unsupported_capacity_unit",
    "unsupported_energy_unit",
}

WARNING_ISSUES = {
    "duplicate_cycle_index",
    "nonmonotonic_cycle_index",
    "zero_discharge_capacity",
    "missing_charge_capacity",
    "missing_discharge_energy",
    "high_capacity_retention_warning",
}

QUALITY_ISSUE_ORDER = [
    "missing_cycle_index",
    "nonpositive_cycle_index",
    "duplicate_cycle_index",
    "nonmonotonic_cycle_index",
    "missing_discharge_capacity",
    "negative_discharge_capacity",
    "zero_discharge_capacity",
    "missing_charge_capacity",
    "negative_charge_capacity",
    "missing_discharge_energy",
    "negative_discharge_energy",
    "unsupported_capacity_unit",
    "unsupported_energy_unit",
    "high_capacity_retention_warning",
]


def validate_normalized_cycle_table(df: pd.DataFrame) -> None:
    """Validate the minimal normalized-cycle columns needed for v1.1.4."""
    missing_columns = [
        column for column in REQUIRED_NORMALIZED_COLUMNS if column not in df.columns
    ]
    if missing_columns:
        raise ValueError(
            "Battery Archive normalized cycle table is missing required column(s): "
            + ", ".join(missing_columns)
        )


def build_cycle_series_id(zip_file: object, internal_csv_path: object) -> str:
    """Build a deterministic series id from source-relative provenance keys."""
    key = f"{str(zip_file)}|{str(internal_csv_path)}"
    return "ba_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def add_cycle_series_id(df: pd.DataFrame) -> pd.DataFrame:
    """Add deterministic cycle-series identifiers without using absolute paths."""
    output = df.copy()
    output["cycle_series_id"] = [
        build_cycle_series_id(zip_file, internal_csv_path)
        for zip_file, internal_csv_path in zip(
            output["zip_file"], output["internal_csv_path"]
        )
    ]
    return output


def _numeric(series: pd.Series) -> pd.Series:
    """Convert a Series to numeric values with invalid cells as NaN."""
    return pd.to_numeric(series, errors="coerce")


def _is_supported_unit(value: object, supported_units: set[str]) -> bool:
    """Return whether a unit is one of the explicitly supported observed units."""
    if pd.isna(value):
        return False
    return str(value).strip() in supported_units


def _initial_issue_lists(row_count: int) -> list[list[str]]:
    return [[] for _ in range(row_count)]


def _append_issue(
    issue_lists: list[list[str]],
    mask: pd.Series,
    issue: str,
) -> None:
    """Append one issue to rows where mask is true."""
    for position in mask[mask.fillna(False)].index:
        issue_lists[int(position)].append(issue)


def _build_duplicate_cycle_mask(df: pd.DataFrame) -> pd.Series:
    valid = df["cycle_index"].notna()
    return valid & df.duplicated(
        ["cycle_series_id", "cycle_index"],
        keep=False,
    )


def _build_nonmonotonic_cycle_mask(df: pd.DataFrame) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    ordered = df.sort_values(
        ["cycle_series_id", "source_row_number"],
        kind="stable",
    )
    for _, group in ordered.groupby("cycle_series_id", dropna=False):
        last_value: float | None = None
        for row_index, value in group["cycle_index"].items():
            if pd.isna(value):
                continue
            current_value = float(value)
            if last_value is not None and current_value < last_value:
                mask.loc[row_index] = True
            last_value = current_value
    return mask


def _issues_to_status(issues: list[str]) -> str:
    """Classify issue lists into valid, warning, or invalid."""
    if any(issue in INVALID_ISSUES for issue in issues):
        return "invalid"
    if any(issue in WARNING_ISSUES for issue in issues):
        return "warning"
    return "valid"


def add_cycle_quality_flags(normalized_df: pd.DataFrame) -> pd.DataFrame:
    """Add row-level conservative quality flags without filtering rows."""
    validate_normalized_cycle_table(normalized_df)
    df = add_cycle_series_id(normalized_df)
    df = df.reset_index(drop=True)

    numeric_columns = [
        "source_row_number",
        "cycle_index",
        "charge_capacity",
        "discharge_capacity",
        "charge_energy",
        "discharge_energy",
    ]
    for column in numeric_columns:
        df[column] = _numeric(df[column])

    issue_lists = _initial_issue_lists(len(df))
    duplicate_cycle_mask = _build_duplicate_cycle_mask(df)
    nonmonotonic_cycle_mask = _build_nonmonotonic_cycle_mask(df)

    capacity_unit_unsupported = ~(
        df["charge_capacity_unit"].map(
            lambda value: _is_supported_unit(value, SUPPORTED_CAPACITY_UNITS)
        )
        & df["discharge_capacity_unit"].map(
            lambda value: _is_supported_unit(value, SUPPORTED_CAPACITY_UNITS)
        )
    )
    energy_unit_unsupported = ~(
        df["charge_energy_unit"].map(
            lambda value: _is_supported_unit(value, SUPPORTED_ENERGY_UNITS)
        )
        & df["discharge_energy_unit"].map(
            lambda value: _is_supported_unit(value, SUPPORTED_ENERGY_UNITS)
        )
    )

    issue_masks = {
        "missing_cycle_index": df["cycle_index"].isna(),
        "nonpositive_cycle_index": df["cycle_index"].notna() & (df["cycle_index"] <= 0),
        "duplicate_cycle_index": duplicate_cycle_mask,
        "nonmonotonic_cycle_index": nonmonotonic_cycle_mask,
        "missing_discharge_capacity": df["discharge_capacity"].isna(),
        "negative_discharge_capacity": df["discharge_capacity"].notna()
        & (df["discharge_capacity"] < 0),
        "zero_discharge_capacity": df["discharge_capacity"].notna()
        & (df["discharge_capacity"] == 0),
        "missing_charge_capacity": df["charge_capacity"].isna(),
        "negative_charge_capacity": df["charge_capacity"].notna()
        & (df["charge_capacity"] < 0),
        "missing_discharge_energy": df["discharge_energy"].isna(),
        "negative_discharge_energy": df["discharge_energy"].notna()
        & (df["discharge_energy"] < 0),
        "unsupported_capacity_unit": capacity_unit_unsupported,
        "unsupported_energy_unit": energy_unit_unsupported,
    }
    for issue in QUALITY_ISSUE_ORDER:
        mask = issue_masks.get(issue)
        if mask is not None:
            _append_issue(issue_lists, mask, issue)

    df["quality_issues"] = [
        QUALITY_DELIMITER.join(issue for issue in QUALITY_ISSUE_ORDER if issue in issues)
        for issues in issue_lists
    ]
    df["quality_issue_count"] = [len(issues) for issues in issue_lists]
    df["quality_status"] = [_issues_to_status(issues) for issues in issue_lists]
    return df


def _single_unit_or_mixed(series: pd.Series) -> str:
    units = sorted({str(value).strip() for value in series.dropna() if str(value).strip()})
    if not units:
        return "unknown"
    if len(units) == 1:
        return units[0]
    return "mixed"


def build_initial_capacity_baselines(
    quality_df: pd.DataFrame,
    baseline_window: int = BASELINE_WINDOW,
) -> pd.DataFrame:
    """Compute conservative per-series initial discharge capacity baselines."""
    baseline_rows: list[dict[str, object]] = []
    ordered = quality_df.sort_values(
        ["cycle_series_id", "cycle_index", "source_row_number"],
        kind="stable",
    )
    for series_id, group in ordered.groupby("cycle_series_id", dropna=False):
        capacity_unit = _single_unit_or_mixed(group["discharge_capacity_unit"])
        baseline_status = "valid"
        baseline_capacity = pd.NA
        baseline_count = 0

        if capacity_unit == "mixed":
            baseline_status = "invalid_mixed_capacity_unit"
        elif capacity_unit not in SUPPORTED_CAPACITY_UNITS:
            baseline_status = "invalid_unsupported_capacity_unit"
        else:
            valid = group[
                group["cycle_index"].notna()
                & (group["cycle_index"] > 0)
                & group["discharge_capacity"].notna()
                & (group["discharge_capacity"] > 0)
                & group["discharge_capacity_unit"].eq(capacity_unit)
            ].sort_values(["cycle_index", "source_row_number"], kind="stable")
            baseline_values = valid["discharge_capacity"].head(baseline_window)
            baseline_count = int(baseline_values.count())
            if baseline_count == 0:
                baseline_status = "invalid_no_valid_capacity"
            else:
                candidate = float(baseline_values.median())
                if candidate <= 0:
                    baseline_status = "invalid_nonpositive_baseline"
                else:
                    baseline_capacity = candidate

        baseline_rows.append(
            {
                "cycle_series_id": series_id,
                "initial_discharge_capacity": baseline_capacity,
                "baseline_capacity_unit": capacity_unit,
                "baseline_cycle_count": baseline_count,
                "baseline_method": BASELINE_METHOD,
                "baseline_status": baseline_status,
            }
        )

    return pd.DataFrame(
        baseline_rows,
        columns=[
            "cycle_series_id",
            "initial_discharge_capacity",
            "baseline_capacity_unit",
            "baseline_cycle_count",
            "baseline_method",
            "baseline_status",
        ],
    )


def _append_retention_warning(df: pd.DataFrame) -> pd.DataFrame:
    """Append high-retention warning flags without clipping retention values."""
    high_mask = df["capacity_retention_pct"].notna() & (
        df["capacity_retention_pct"] > HIGH_RETENTION_WARNING_PCT
    )
    if not bool(high_mask.any()):
        return df

    output = df.copy()
    existing = output["quality_issues"].fillna("").astype(str)
    output.loc[high_mask, "quality_issues"] = existing.loc[high_mask].map(
        lambda value: (
            f"{value}{QUALITY_DELIMITER}high_capacity_retention_warning"
            if value
            else "high_capacity_retention_warning"
        )
    )
    output["quality_issue_count"] = output["quality_issues"].map(
        lambda value: 0 if not value else len(str(value).split(QUALITY_DELIMITER))
    )
    output["quality_status"] = output["quality_issues"].map(
        lambda value: _issues_to_status(str(value).split(QUALITY_DELIMITER) if value else [])
    )
    return output


def add_capacity_metrics(
    quality_df: pd.DataFrame,
    baseline_df: pd.DataFrame,
) -> pd.DataFrame:
    """Add retention and capacity-based SOH proxy columns without clipping."""
    df = quality_df.merge(baseline_df, on="cycle_series_id", how="left")
    can_compute = (
        df["baseline_status"].eq("valid")
        & df["initial_discharge_capacity"].notna()
        & (df["initial_discharge_capacity"] > 0)
        & df["discharge_capacity"].notna()
        & (df["discharge_capacity"] >= 0)
        & df["discharge_capacity_unit"].eq(df["baseline_capacity_unit"])
    )
    df["capacity_retention"] = pd.NA
    df.loc[can_compute, "capacity_retention"] = (
        df.loc[can_compute, "discharge_capacity"]
        / df.loc[can_compute, "initial_discharge_capacity"]
    )
    df["capacity_retention"] = _numeric(df["capacity_retention"])
    df["capacity_retention_pct"] = df["capacity_retention"] * 100.0
    df["soh_capacity_proxy"] = df["capacity_retention"]
    df["soh_capacity_proxy_pct"] = df["capacity_retention_pct"]
    return _append_retention_warning(df)


def _first_non_null(series: pd.Series) -> object:
    valid = series.dropna()
    if valid.empty:
        return pd.NA
    return valid.iloc[0]


def _threshold_crossing(group: pd.DataFrame, threshold_pct: float) -> object:
    valid = group.dropna(subset=["cycle_index", "capacity_retention_pct"]).sort_values(
        ["cycle_index", "source_row_number"],
        kind="stable",
    )
    below = valid[valid["capacity_retention_pct"] < threshold_pct]
    if below.empty:
        return pd.NA
    return below["cycle_index"].iloc[0]


def _persistent_threshold_crossing(
    group: pd.DataFrame,
    threshold_pct: float,
    window: int = PERSISTENT_THRESHOLD_WINDOW,
) -> object:
    valid = group.dropna(subset=["cycle_index", "capacity_retention_pct"]).sort_values(
        ["cycle_index", "source_row_number"],
        kind="stable",
    )
    values = valid[["cycle_index", "capacity_retention_pct"]].reset_index(drop=True)
    if len(values) < window:
        return pd.NA
    below = values["capacity_retention_pct"] < threshold_pct
    for start in range(0, len(values) - window + 1):
        if bool(below.iloc[start : start + window].all()):
            return values.loc[start, "cycle_index"]
    return pd.NA


def build_cycle_series_summary(analysis_ready_df: pd.DataFrame) -> pd.DataFrame:
    """Build one compact quality and threshold summary row per cycle series."""
    rows: list[dict[str, object]] = []
    ordered = analysis_ready_df.sort_values(
        ["cycle_series_id", "cycle_index", "source_row_number"],
        kind="stable",
    )
    for series_id, group in ordered.groupby("cycle_series_id", dropna=False):
        total_rows = int(len(group))
        valid_rows = int(group["quality_status"].eq("valid").sum())
        warning_rows = int(group["quality_status"].eq("warning").sum())
        invalid_rows = int(group["quality_status"].eq("invalid").sum())
        retention = group["capacity_retention_pct"].dropna()

        first_80 = _threshold_crossing(group, 80.0)
        first_70 = _threshold_crossing(group, 70.0)
        persistent_80 = _persistent_threshold_crossing(group, 80.0)
        persistent_70 = _persistent_threshold_crossing(group, 70.0)
        reached_80 = not pd.isna(first_80)
        reached_70 = not pd.isna(first_70)
        has_retention = bool(group["capacity_retention_pct"].notna().any())

        duplicate_issue = group["quality_issues"].fillna("").str.contains(
            "duplicate_cycle_index",
            regex=False,
        )
        nonmonotonic_issue = group["quality_issues"].fillna("").str.contains(
            "nonmonotonic_cycle_index",
            regex=False,
        )
        mixed_capacity_unit = _single_unit_or_mixed(group["discharge_capacity_unit"]) == "mixed"
        baseline_status = str(_first_non_null(group["baseline_status"]))

        if invalid_rows:
            data_quality_status = "has_invalid_rows"
        elif warning_rows:
            data_quality_status = "has_warnings"
        elif baseline_status != "valid":
            data_quality_status = "baseline_invalid"
        else:
            data_quality_status = "analysis_candidate"

        messages: list[str] = []
        if invalid_rows:
            messages.append(f"{invalid_rows} invalid rows")
        if warning_rows:
            messages.append(f"{warning_rows} warning rows")
        if baseline_status != "valid":
            messages.append(f"baseline_status={baseline_status}")
        if reached_80:
            messages.append("80pct threshold reached")
        if not messages:
            messages.append("no strong quality warning")

        rows.append(
            {
                "cycle_series_id": series_id,
                "zip_file": _first_non_null(group["zip_file"]),
                "internal_csv_path": _first_non_null(group["internal_csv_path"]),
                "file_name": _first_non_null(group["file_name"]),
                "source": _first_non_null(group["source"]) if "source" in group else pd.NA,
                "cell_id": _first_non_null(group["cell_id"]) if "cell_id" in group else pd.NA,
                "chemistry": _first_non_null(group["chemistry"])
                if "chemistry" in group
                else pd.NA,
                "form_factor": _first_non_null(group["form_factor"])
                if "form_factor" in group
                else pd.NA,
                "temperature_C": _first_non_null(group["temperature_C"])
                if "temperature_C" in group
                else pd.NA,
                "soc_window": _first_non_null(group["soc_window"])
                if "soc_window" in group
                else pd.NA,
                "charge_c_rate": _first_non_null(group["charge_c_rate"])
                if "charge_c_rate" in group
                else pd.NA,
                "discharge_c_rate": _first_non_null(group["discharge_c_rate"])
                if "discharge_c_rate" in group
                else pd.NA,
                "capacity_unit": _single_unit_or_mixed(group["discharge_capacity_unit"]),
                "total_rows": total_rows,
                "valid_cycle_rows": valid_rows,
                "warning_rows": warning_rows,
                "invalid_rows": invalid_rows,
                "min_cycle_index": group["cycle_index"].min(),
                "max_cycle_index": group["cycle_index"].max(),
                "baseline_capacity": _first_non_null(group["initial_discharge_capacity"]),
                "baseline_cycle_count": int(_first_non_null(group["baseline_cycle_count"])),
                "baseline_method": _first_non_null(group["baseline_method"]),
                "baseline_status": baseline_status,
                "initial_retention_pct": retention.iloc[0] if not retention.empty else pd.NA,
                "final_retention_pct": retention.iloc[-1] if not retention.empty else pd.NA,
                "min_retention_pct": retention.min() if not retention.empty else pd.NA,
                "first_cycle_below_80pct": first_80,
                "persistent_cycle_below_80pct": persistent_80,
                "first_cycle_below_70pct": first_70,
                "persistent_cycle_below_70pct": persistent_70,
                "reached_80pct_threshold": reached_80,
                "reached_70pct_threshold": reached_70,
                "observed_censored_80pct": bool(has_retention and not reached_80),
                "observed_censored_70pct": bool(has_retention and not reached_70),
                "has_duplicate_cycle_index": bool(duplicate_issue.any()),
                "has_nonmonotonic_cycle_index": bool(nonmonotonic_issue.any()),
                "mixed_capacity_unit": bool(mixed_capacity_unit),
                "data_quality_status": data_quality_status,
                "data_quality_message": QUALITY_DELIMITER.join(messages),
            }
        )

    return pd.DataFrame(rows, columns=SERIES_SUMMARY_COLUMNS).sort_values(
        ["zip_file", "internal_csv_path"],
        key=lambda series: series.astype(str).str.casefold(),
    ).reset_index(drop=True)


def _summary_row(
    metric: str,
    count: int | float,
    denominator: int | float,
    description: str,
) -> dict[str, object]:
    percentage = 0.0 if denominator == 0 else (float(count) / float(denominator)) * 100.0
    return {
        "metric": metric,
        "count": count,
        "percentage": round(percentage, 4),
        "description": description,
    }


def build_data_quality_summary(
    analysis_ready_df: pd.DataFrame,
    series_summary_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build compact row/series/source-level data-quality metrics."""
    total_rows = len(analysis_ready_df)
    total_series = len(series_summary_df)
    rows: list[dict[str, object]] = [
        _summary_row("total_cycle_rows", total_rows, total_rows, "Total cycle rows."),
        _summary_row(
            "valid_rows",
            int(analysis_ready_df["quality_status"].eq("valid").sum()),
            total_rows,
            "Rows with no row-level quality issues.",
        ),
        _summary_row(
            "warning_rows",
            int(analysis_ready_df["quality_status"].eq("warning").sum()),
            total_rows,
            "Rows with warning-level quality issues.",
        ),
        _summary_row(
            "invalid_rows",
            int(analysis_ready_df["quality_status"].eq("invalid").sum()),
            total_rows,
            "Rows with invalid-level quality issues.",
        ),
        _summary_row("series_count", total_series, total_series, "Total cycle series."),
        _summary_row(
            "series_with_valid_baseline",
            int(series_summary_df["baseline_status"].eq("valid").sum()),
            total_series,
            "Series with a valid initial discharge capacity baseline.",
        ),
        _summary_row(
            "series_with_mixed_units",
            int(series_summary_df["mixed_capacity_unit"].sum()),
            total_series,
            "Series containing more than one discharge capacity unit.",
        ),
        _summary_row(
            "series_with_duplicate_cycle_index",
            int(series_summary_df["has_duplicate_cycle_index"].sum()),
            total_series,
            "Series with duplicated cycle_index values.",
        ),
        _summary_row(
            "series_with_nonmonotonic_cycle_index",
            int(series_summary_df["has_nonmonotonic_cycle_index"].sum()),
            total_series,
            "Series where cycle_index decreases in source row order.",
        ),
        _summary_row(
            "series_reaching_80pct",
            int(series_summary_df["reached_80pct_threshold"].sum()),
            total_series,
            "Series with at least one observed retention value below 80%.",
        ),
        _summary_row(
            "series_not_reaching_80pct",
            int((~series_summary_df["reached_80pct_threshold"]).sum()),
            total_series,
            "Series not observed below 80%; treated as observed-censored.",
        ),
        _summary_row(
            "series_reaching_70pct",
            int(series_summary_df["reached_70pct_threshold"].sum()),
            total_series,
            "Series with at least one observed retention value below 70%.",
        ),
        _summary_row(
            "series_not_reaching_70pct",
            int((~series_summary_df["reached_70pct_threshold"]).sum()),
            total_series,
            "Series not observed below 70%; treated as observed-censored.",
        ),
        _summary_row(
            "derived_metric_coverage_rows",
            int(analysis_ready_df["capacity_retention_pct"].notna().sum()),
            total_rows,
            "Rows with computable capacity retention and SOH proxy.",
        ),
        _summary_row(
            "high_retention_warning_rows",
            int(
                analysis_ready_df["quality_issues"]
                .fillna("")
                .str.contains("high_capacity_retention_warning", regex=False)
                .sum()
            ),
            total_rows,
            f"Rows with capacity_retention_pct > {HIGH_RETENTION_WARNING_PCT}.",
        ),
    ]

    if "source" in series_summary_df:
        for source, group in series_summary_df.groupby("source", dropna=False):
            label = str(source)
            rows.append(
                _summary_row(
                    f"source:{label}:series_count",
                    len(group),
                    total_series,
                    f"Cycle series count for source {label}.",
                )
            )
            rows.append(
                _summary_row(
                    f"source:{label}:non_candidate_series",
                    int((group["data_quality_status"] != "analysis_candidate").sum()),
                    len(group),
                    f"Series from {label} with warnings, invalid rows, or baseline issues.",
                )
            )

    return pd.DataFrame(rows, columns=QUALITY_SUMMARY_COLUMNS)


def build_analysis_ready_tables(
    normalized_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build cycle analysis-ready, series summary, and quality summary tables."""
    quality_df = add_cycle_quality_flags(normalized_df)
    baseline_df = build_initial_capacity_baselines(quality_df)
    analysis_ready_df = add_capacity_metrics(quality_df, baseline_df)
    output_columns = list(normalized_df.columns)
    if "cycle_series_id" not in output_columns:
        output_columns = ["cycle_series_id"] + output_columns
    for column in QUALITY_OUTPUT_COLUMNS:
        if column not in output_columns:
            output_columns.append(column)
    analysis_ready_df = analysis_ready_df[output_columns].sort_values(
        ["zip_file", "internal_csv_path", "source_row_number"],
        kind="stable",
    ).reset_index(drop=True)
    series_summary_df = build_cycle_series_summary(analysis_ready_df)
    quality_summary_df = build_data_quality_summary(
        analysis_ready_df,
        series_summary_df,
    )
    return analysis_ready_df, series_summary_df, quality_summary_df


def assert_no_absolute_paths(df: pd.DataFrame) -> None:
    """Raise if a table appears to contain absolute local filesystem paths."""
    pattern = r"^[A-Za-z]:\\|^/"
    contains_absolute_path = df.astype(str).apply(
        lambda series: series.str.contains(pattern, regex=True, na=False)
    )
    if bool(contains_absolute_path.any().any()):
        raise ValueError("Generated Battery Archive table contains an absolute path.")


def output_size_bytes(path: str | Path) -> int:
    """Return file size in bytes for console reporting."""
    return Path(path).stat().st_size
