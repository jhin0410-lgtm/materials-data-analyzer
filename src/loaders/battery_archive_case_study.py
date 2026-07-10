"""Battery Archive case-study summaries from compact cycle-series tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


GROUP_COLUMNS = [
    "source",
    "chemistry",
    "form_factor",
    "temperature_C",
    "soc_window",
    "charge_c_rate",
    "discharge_c_rate",
]

REQUIRED_SERIES_COLUMNS = GROUP_COLUMNS + [
    "cycle_series_id",
    "total_rows",
    "max_cycle_index",
    "final_retention_pct",
    "min_retention_pct",
    "reached_80pct_threshold",
    "reached_70pct_threshold",
    "persistent_cycle_below_80pct",
    "persistent_cycle_below_70pct",
    "observed_censored_80pct",
    "observed_censored_70pct",
    "warning_rows",
    "invalid_rows",
    "has_duplicate_cycle_index",
    "has_nonmonotonic_cycle_index",
    "data_quality_status",
]

GROUP_SUMMARY_COLUMNS = GROUP_COLUMNS + [
    "series_count",
    "small_group_flag",
    "median_last_observed_cycle",
    "max_last_observed_cycle",
    "median_final_retention_pct",
    "median_min_retention_pct",
    "reached_80pct_count",
    "reached_80pct_rate",
    "reached_70pct_count",
    "reached_70pct_rate",
    "observed_censored_80pct_count",
    "observed_censored_70pct_count",
    "median_persistent_cycle_below_80pct",
    "median_persistent_cycle_below_70pct",
    "warning_series_count",
    "warning_series_rate",
    "invalid_series_count",
    "analysis_candidate_series_count",
    "group_quality_message",
]

REQUIRED_CASE_STUDY_SECTIONS = [
    "Objective",
    "Dataset Scope",
    "Pipeline",
    "Data Quality",
    "Existing Platform Workflow",
    "Reliability Summary",
    "Group Comparisons",
    "Threshold/Censoring Interpretation",
    "Optional Simulation Validation",
    "Limitations",
    "Reproduction Commands",
    "Output Files",
    "Conclusion",
]


def validate_series_summary(series_df: pd.DataFrame) -> None:
    """Validate the compact Battery Archive series summary table."""
    missing_columns = [
        column for column in REQUIRED_SERIES_COLUMNS if column not in series_df.columns
    ]
    if missing_columns:
        raise ValueError(
            "Battery Archive series summary is missing required column(s): "
            + ", ".join(missing_columns)
        )


def prepare_grouping_columns(series_df: pd.DataFrame) -> pd.DataFrame:
    """Preserve missing metadata groups with explicit placeholder values."""
    output = series_df.copy()
    for column in GROUP_COLUMNS:
        output[column] = output[column].where(output[column].notna(), "missing")
    return output


def _count_true(series: pd.Series) -> int:
    return int(_as_bool(series).sum())


def _as_bool(series: pd.Series) -> pd.Series:
    """Convert bool-like CSV values to booleans without treating 'False' as true."""
    return series.map(
        lambda value: (
            False
            if pd.isna(value)
            else str(value).strip().lower() in {"true", "1", "yes"}
        )
    )


def _rate(count: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((float(count) / float(denominator)) * 100.0, 4)


def build_reliability_group_summary(
    series_df: pd.DataFrame,
    small_group_threshold: int = 3,
) -> pd.DataFrame:
    """Build compact group-level reliability/degradation proxy summary."""
    validate_series_summary(series_df)
    prepared = prepare_grouping_columns(series_df)
    rows: list[dict[str, object]] = []

    grouped = prepared.groupby(GROUP_COLUMNS, dropna=False, sort=True)
    for group_key, group in grouped:
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        series_count = int(len(group))
        reached_80_count = _count_true(group["reached_80pct_threshold"])
        reached_70_count = _count_true(group["reached_70pct_threshold"])
        censored_80_count = _count_true(group["observed_censored_80pct"])
        censored_70_count = _count_true(group["observed_censored_70pct"])
        warning_series_count = int(
            (
                group["warning_rows"].fillna(0).astype(float).gt(0)
                | group["data_quality_status"].ne("analysis_candidate")
            ).sum()
        )
        invalid_series_count = int(group["invalid_rows"].fillna(0).astype(float).gt(0).sum())
        analysis_candidate_count = int(
            group["data_quality_status"].eq("analysis_candidate").sum()
        )

        message_parts: list[str] = []
        if series_count < small_group_threshold:
            message_parts.append("small group; interpret cautiously")
        if warning_series_count:
            message_parts.append(f"{warning_series_count} series with warnings")
        if invalid_series_count:
            message_parts.append(f"{invalid_series_count} series with invalid rows")
        if censored_80_count:
            message_parts.append(f"{censored_80_count} censored at 80pct")
        if not message_parts:
            message_parts.append("no strong group-level warning")

        row = {column: value for column, value in zip(GROUP_COLUMNS, group_key)}
        row.update(
            {
                "series_count": series_count,
                "small_group_flag": bool(series_count < small_group_threshold),
                "median_last_observed_cycle": group["max_cycle_index"].median(),
                "max_last_observed_cycle": group["max_cycle_index"].max(),
                "median_final_retention_pct": group["final_retention_pct"].median(),
                "median_min_retention_pct": group["min_retention_pct"].median(),
                "reached_80pct_count": reached_80_count,
                "reached_80pct_rate": _rate(reached_80_count, series_count),
                "reached_70pct_count": reached_70_count,
                "reached_70pct_rate": _rate(reached_70_count, series_count),
                "observed_censored_80pct_count": censored_80_count,
                "observed_censored_70pct_count": censored_70_count,
                "median_persistent_cycle_below_80pct": group[
                    "persistent_cycle_below_80pct"
                ].median(),
                "median_persistent_cycle_below_70pct": group[
                    "persistent_cycle_below_70pct"
                ].median(),
                "warning_series_count": warning_series_count,
                "warning_series_rate": _rate(warning_series_count, series_count),
                "invalid_series_count": invalid_series_count,
                "analysis_candidate_series_count": analysis_candidate_count,
                "group_quality_message": "; ".join(message_parts),
            }
        )
        rows.append(row)

    return pd.DataFrame(rows, columns=GROUP_SUMMARY_COLUMNS).sort_values(
        GROUP_COLUMNS,
        key=lambda series: series.astype(str).str.casefold(),
    ).reset_index(drop=True)


def _markdown_table(df: pd.DataFrame, max_rows: int = 12) -> str:
    """Render a small DataFrame as a Markdown table."""
    if df.empty:
        return "_No rows._"
    table = df.head(max_rows).copy()
    lines = [
        "| " + " | ".join(table.columns.astype(str)) + " |",
        "| " + " | ".join("---" for _ in table.columns) + " |",
    ]
    for _, row in table.iterrows():
        values = ["" if pd.isna(value) else str(value) for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def build_case_study_markdown(
    series_df: pd.DataFrame,
    group_summary_df: pd.DataFrame,
) -> str:
    """Build the Battery Archive case-study report markdown."""
    total_series = len(series_df)
    total_rows = int(series_df["total_rows"].sum()) if "total_rows" in series_df else 0
    warning_series = int((series_df["data_quality_status"] != "analysis_candidate").sum())
    duplicate_series = _count_true(series_df["has_duplicate_cycle_index"])
    nonmonotonic_series = _count_true(series_df["has_nonmonotonic_cycle_index"])
    invalid_series = int(series_df["invalid_rows"].fillna(0).astype(float).gt(0).sum())
    reached_80 = _count_true(series_df["reached_80pct_threshold"])
    reached_70 = _count_true(series_df["reached_70pct_threshold"])
    censored_80 = _count_true(series_df["observed_censored_80pct"])
    censored_70 = _count_true(series_df["observed_censored_70pct"])
    top_groups = group_summary_df.sort_values(
        ["series_count", "source"],
        ascending=[False, True],
    )[
        [
            "source",
            "chemistry",
            "form_factor",
            "temperature_C",
            "soc_window",
            "charge_c_rate",
            "discharge_c_rate",
            "series_count",
            "median_final_retention_pct",
            "reached_80pct_rate",
            "warning_series_rate",
        ]
    ]

    return "\n".join(
        [
            "# Battery Archive Reliability Case Study",
            "",
            "## Objective",
            "",
            "This case study documents how `materials_data_analyzer` can turn "
            "Battery Archive cycle-level CSV data into compact reliability and "
            "degradation proxy summaries. It is a tabular engineering data case "
            "study, not a degradation forecasting model or remaining useful life "
            "prediction workflow.",
            "",
            "## Dataset Scope",
            "",
            "- Raw source: 9 Battery Archive zip files stored locally under `data/raw/battery_archive/`.",
            "- Raw data is not committed to Git.",
            "- Inventory audit found 196 `*_cycle_data.csv` files and 196 timeseries CSV files.",
            "- This case study uses only cycle-level CSV files.",
            "- Filename-derived metadata is used for source, chemistry, form factor, temperature, SOC window, and C-rate fields.",
            "- Timeseries feature extraction is out of scope for this case study.",
            "",
            "## Pipeline",
            "",
            "1. Zip inventory without extraction.",
            "2. Filename metadata enrichment.",
            "3. Cycle CSV schema audit.",
            "4. Schema normalization.",
            "5. Cycle quality flags.",
            "6. Initial discharge-capacity baseline.",
            "7. Capacity retention.",
            "8. Capacity-based SOH proxy.",
            "9. 80% and 70% threshold crossing proxies.",
            "10. Series-level and group-level summaries.",
            "",
            "## Data Quality",
            "",
            f"- Cycle rows represented in compact summaries: {total_rows:,}.",
            f"- Cycle series: {total_series:,}.",
            f"- Series with duplicate cycle index: {duplicate_series:,}.",
            f"- Series with nonmonotonic cycle index: {nonmonotonic_series:,}.",
            f"- Series with invalid rows: {invalid_series:,}.",
            f"- Series with warning or non-candidate status: {warning_series:,}.",
            "",
            "Duplicate cycle-index and nonmonotonic cycle-index cases are retained as "
            "quality warnings. Source rows are not deleted. Groups with small sample "
            "counts are explicitly flagged so simple averages are not overinterpreted.",
            "",
            "## Existing Platform Workflow",
            "",
            "The compact `battery_archive_cycle_series_summary.csv` table can be "
            "passed to the existing EDA and reliability CLI modes without changing "
            "core analyzer logic. These smoke runs summarize the series-level table; "
            "they do not create a new forecasting model.",
            "",
            "```powershell",
            "python src/process_data.py --mode eda --input data/processed/battery_archive_cycle_series_summary.csv --run-name battery_archive_series_summary_eda_smoke",
            "python src/process_data.py --mode reliability --input data/processed/battery_archive_cycle_series_summary.csv --run-name battery_archive_series_summary_reliability_smoke",
            "```",
            "",
            "## Reliability Summary",
            "",
            f"- Series reaching the 80% threshold proxy: {reached_80:,}.",
            f"- Series reaching the 70% threshold proxy: {reached_70:,}.",
            f"- Observed-censored at 80%: {censored_80:,}.",
            f"- Observed-censored at 70%: {censored_70:,}.",
            "",
            "Threshold crossings are observed proxies only. A series that does not "
            "cross a threshold is treated as censored within the observed data window; "
            "no cycle life or RUL is inferred.",
            "",
            "## Group Comparisons",
            "",
            "Groups are defined by source, chemistry, form factor, temperature, SOC "
            "window, and charge/discharge C-rate. Metadata-missing groups are kept "
            "rather than silently dropped.",
            "",
            _markdown_table(top_groups, max_rows=12),
            "",
            "## Threshold/Censoring Interpretation",
            "",
            "The case study reports first crossing and persistent three-cycle crossing "
            "for 80% and 70% capacity-retention thresholds. Persistent crossing is a "
            "more conservative proxy than a single noisy crossing, but it is still an "
            "observed-data summary rather than a life prediction.",
            "",
            "## Optional Simulation Validation",
            "",
            "Simulation was not run automatically in v1.1.5. A future smoke run may "
            "use `capacity_retention_pct` as the target with group-aware validation "
            "by `cycle_series_id`. The `cycle_series_id`, baseline capacity, and "
            "`discharge_capacity` should not be used as predictive features because "
            "they either identify the group or are directly tied to target calculation.",
            "",
            "## Limitations",
            "",
            "- Battery Archive source/protocol differences mean group comparisons are descriptive.",
            "- Filename metadata may be incomplete or heuristic.",
            "- SOH is represented only as a capacity-based proxy.",
            "- Threshold crossing proxies are not remaining useful life estimates.",
            "- Timeseries behavior and impedance are not included.",
            "",
            "## Reproduction Commands",
            "",
            "```powershell",
            "python scripts/build_battery_archive_cycle_inventory.py --raw-dir data/raw/battery_archive --output data/processed/battery_archive_cycle_file_inventory.csv",
            "python scripts/enrich_battery_archive_cycle_inventory.py --input data/processed/battery_archive_cycle_file_inventory.csv --output data/processed/battery_archive_cycle_file_inventory_enriched.csv",
            "python scripts/audit_battery_archive_cycle_schemas.py --raw-dir data/raw/battery_archive --inventory data/processed/battery_archive_cycle_file_inventory_enriched.csv --schema-output data/processed/battery_archive_cycle_schema_inventory.csv --column-output data/processed/battery_archive_cycle_column_inventory.csv --report-output docs/BATTERY_ARCHIVE_CYCLE_SCHEMA_AUDIT.md",
            "python scripts/build_battery_archive_cycle_normalized.py --raw-dir data/raw/battery_archive --inventory data/processed/battery_archive_cycle_file_inventory_enriched.csv --schema-inventory data/processed/battery_archive_cycle_schema_inventory.csv --column-inventory data/processed/battery_archive_cycle_column_inventory.csv --normalized-output data/processed/battery_archive_cycle_normalized.csv --summary-output data/processed/battery_archive_cycle_load_summary.csv --mapping-output data/processed/battery_archive_cycle_column_mapping.csv",
            "python scripts/build_battery_archive_analysis_ready.py --input data/processed/battery_archive_cycle_normalized.csv --analysis-ready-output data/processed/battery_archive_cycle_analysis_ready.csv --series-summary-output data/processed/battery_archive_cycle_series_summary.csv --quality-summary-output data/processed/battery_archive_data_quality_summary.csv",
            "python scripts/build_battery_archive_case_study.py --series-summary data/processed/battery_archive_cycle_series_summary.csv --group-summary-output data/processed/battery_archive_reliability_group_summary.csv --report-output data/case_studies/battery_archive/case_study.md",
            "```",
            "",
            "## Output Files",
            "",
            "- `data/processed/battery_archive_cycle_series_summary.csv`: compact per-series quality and threshold summary.",
            "- `data/processed/battery_archive_data_quality_summary.csv`: compact global/source data-quality metrics.",
            "- `data/processed/battery_archive_reliability_group_summary.csv`: compact group-level reliability proxy summary.",
            "- `data/case_studies/battery_archive/case_study.md`: narrative case-study report.",
            "- `data/processed/battery_archive_cycle_analysis_ready.csv`: large generated local artifact, not recommended for Git tracking.",
            "",
            "## Conclusion",
            "",
            "This Battery Archive case study complements the Kaggle NASA battery case "
            "study by demonstrating a larger, multi-source cycle-data workflow. It "
            "emphasizes raw zip inventory, schema normalization, quality flags, "
            "censored threshold interpretation, and compact reproducibility outputs "
            "rather than predictive degradation modeling.",
            "",
        ]
    )


def build_methodology_markdown() -> str:
    """Build concise methodology documentation with script commands."""
    return "\n".join(
        [
            "# Battery Archive Case Study Methodology",
            "",
            "This methodology is intentionally conservative and reproducible.",
            "",
            "## Steps",
            "",
            "1. Zip inventory",
            "2. Filename metadata enrichment",
            "3. Schema audit",
            "4. Schema normalization",
            "5. Quality flags",
            "6. Baseline capacity",
            "7. Capacity retention",
            "8. Capacity-based SOH proxy",
            "9. 80%/70% threshold crossing proxy",
            "10. Series-level summary",
            "11. Group-level reliability summary",
            "",
            "## Commands",
            "",
            "```powershell",
            "python scripts/build_battery_archive_cycle_inventory.py --raw-dir data/raw/battery_archive --output data/processed/battery_archive_cycle_file_inventory.csv",
            "python scripts/enrich_battery_archive_cycle_inventory.py --input data/processed/battery_archive_cycle_file_inventory.csv --output data/processed/battery_archive_cycle_file_inventory_enriched.csv",
            "python scripts/audit_battery_archive_cycle_schemas.py --raw-dir data/raw/battery_archive --inventory data/processed/battery_archive_cycle_file_inventory_enriched.csv --schema-output data/processed/battery_archive_cycle_schema_inventory.csv --column-output data/processed/battery_archive_cycle_column_inventory.csv --report-output docs/BATTERY_ARCHIVE_CYCLE_SCHEMA_AUDIT.md",
            "python scripts/build_battery_archive_cycle_normalized.py --raw-dir data/raw/battery_archive --inventory data/processed/battery_archive_cycle_file_inventory_enriched.csv --schema-inventory data/processed/battery_archive_cycle_schema_inventory.csv --column-inventory data/processed/battery_archive_cycle_column_inventory.csv --normalized-output data/processed/battery_archive_cycle_normalized.csv --summary-output data/processed/battery_archive_cycle_load_summary.csv --mapping-output data/processed/battery_archive_cycle_column_mapping.csv",
            "python scripts/build_battery_archive_analysis_ready.py --input data/processed/battery_archive_cycle_normalized.csv --analysis-ready-output data/processed/battery_archive_cycle_analysis_ready.csv --series-summary-output data/processed/battery_archive_cycle_series_summary.csv --quality-summary-output data/processed/battery_archive_data_quality_summary.csv",
            "python scripts/build_battery_archive_case_study.py --series-summary data/processed/battery_archive_cycle_series_summary.csv --group-summary-output data/processed/battery_archive_reliability_group_summary.csv --report-output data/case_studies/battery_archive/case_study.md",
            "```",
            "",
            "No raw zip is extracted by these scripts. Large generated cycle-level "
            "tables should remain local-only by default.",
            "",
        ]
    )


def write_text(path: str | Path, content: str) -> None:
    """Write UTF-8 text after creating the parent directory."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def save_group_summary(summary_df: pd.DataFrame, output_path: str | Path) -> None:
    """Save group summary CSV without an index."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(path, index=False)
