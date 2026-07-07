"""Compare Kaggle battery simulation case-study runs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd


DEFAULT_RUN_SPECS = [
    "metadata_random=outputs/kaggle_battery_metadata_only_retention_simulation",
    "feature_random=outputs/kaggle_battery_feature_enriched_retention_simulation",
    "metadata_group=outputs/kaggle_battery_metadata_only_group_retention_simulation",
    "feature_group=outputs/kaggle_battery_feature_enriched_group_retention_simulation",
    (
        "feature_no_count_group="
        "outputs/kaggle_battery_feature_enriched_no_count_group_retention_simulation"
    ),
]

REQUIRED_FILES = {
    "train_test_metrics": Path("processed") / "train_test_metrics.csv",
    "overfitting_diagnostics": Path("processed") / "overfitting_diagnostics.csv",
    "cross_validation_metrics": Path("processed") / "cross_validation_metrics.csv",
    "feature_importance": Path("processed") / "feature_importance.csv",
}

SUMMARY_COLUMNS = [
    "run_name",
    "validation_type",
    "train_r2",
    "test_r2",
    "r2_gap",
    "train_mae",
    "test_mae",
    "train_rmse",
    "test_rmse",
    "rmse_ratio",
    "cv_r2_mean",
    "cv_r2_std",
    "cv_rmse_mean",
    "cv_rmse_std",
    "top_1_feature",
    "top_1_importance",
    "top_3_features",
    "overfitting_summary",
    "interpretation_note",
]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Compare simulation run metrics for the Kaggle battery case study."
    )
    parser.add_argument("--output", required=True, help="Output comparison CSV path.")
    parser.add_argument("--report", required=True, help="Output Markdown report path.")
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        help="Additional run spec in the form name=outputs/run_folder.",
    )
    parser.add_argument(
        "--runs",
        nargs="+",
        default=None,
        help="Optional compatibility alias: run specs in name=path form.",
    )
    return parser.parse_args()


def parse_run_spec(spec: str) -> tuple[str, Path]:
    """Parse one name=path run specification."""
    if "=" not in spec:
        raise ValueError(
            f"Invalid run spec: {spec}. Expected format: run_name=outputs/run_folder"
        )
    run_name, run_path = spec.split("=", 1)
    run_name = run_name.strip()
    if not run_name:
        raise ValueError(f"Run spec has an empty run_name: {spec}")
    path = Path(run_path.strip())
    if not path.exists():
        raise FileNotFoundError(f"Run folder was not found for {run_name}: {path}")
    return run_name, path


def resolve_run_specs(extra_runs: list[str] | None = None) -> list[str]:
    """Return default run specs plus any extra CLI-provided run specs."""
    return DEFAULT_RUN_SPECS + list(extra_runs or [])


def read_required_csv(run_name: str, run_path: Path, key: str) -> pd.DataFrame:
    """Read a required simulation output CSV."""
    csv_path = run_path / REQUIRED_FILES[key]
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Required file for run '{run_name}' was not found: {csv_path}"
        )
    try:
        return pd.read_csv(csv_path)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"Required file for run '{run_name}' is empty: {csv_path}") from exc


def value_from_dataset(metrics_df: pd.DataFrame, dataset: str, column: str) -> object:
    """Return a metric value for train/test rows, or NaN when missing."""
    if column not in metrics_df.columns or "dataset" not in metrics_df.columns:
        return np.nan
    rows = metrics_df[metrics_df["dataset"] == dataset]
    if rows.empty:
        return np.nan
    return rows.iloc[0][column]


def infer_validation_type(metrics_df: pd.DataFrame) -> str:
    """Infer validation type while supporting older simulation outputs."""
    if "validation_type" in metrics_df.columns:
        values = metrics_df["validation_type"].dropna().astype(str).unique().tolist()
        if values:
            return values[0]

    note = " ".join(metrics_df.get("note", pd.Series(dtype="object")).dropna().astype(str))
    if "GroupShuffleSplit" in note or "group_column" in note:
        return "group_split"
    if "train/test split used" in note:
        return "random_split"
    if "split was skipped" in note:
        return "split_skipped"
    return "unknown"


def summarize_cross_validation(cv_df: pd.DataFrame) -> dict[str, object]:
    """Calculate CV mean/std summaries from cross_validation_metrics.csv."""
    usable = cv_df.copy()
    if "fold" in usable.columns:
        usable = usable[usable["fold"].astype(str).str.lower() != "skipped"]

    r2 = pd.to_numeric(usable.get("r2", pd.Series(dtype="float64")), errors="coerce")
    rmse = pd.to_numeric(
        usable.get("rmse", pd.Series(dtype="float64")), errors="coerce"
    )
    return {
        "cv_r2_mean": r2.mean(skipna=True),
        "cv_r2_std": r2.std(skipna=True),
        "cv_rmse_mean": rmse.mean(skipna=True),
        "cv_rmse_std": rmse.std(skipna=True),
    }


def summarize_feature_importance(feature_df: pd.DataFrame) -> tuple[object, object, str]:
    """Return top feature summaries from feature_importance.csv."""
    if feature_df.empty or "feature" not in feature_df.columns:
        return np.nan, np.nan, ""

    sorted_df = feature_df.copy()
    if "rank" in sorted_df.columns:
        sorted_df = sorted_df.sort_values("rank", kind="mergesort")
    elif "importance" in sorted_df.columns:
        sorted_df = sorted_df.sort_values("importance", ascending=False)

    top_1 = sorted_df.iloc[0]
    top_1_feature = top_1.get("feature", np.nan)
    top_1_importance = top_1.get("importance", np.nan)
    top_3_features = ", ".join(sorted_df["feature"].head(3).astype(str).tolist())
    return top_1_feature, top_1_importance, top_3_features


def summarize_overfitting(overfitting_df: pd.DataFrame) -> str:
    """Collapse overfitting diagnostic interpretations into one field."""
    if "interpretation" not in overfitting_df.columns or overfitting_df.empty:
        return ""
    interpretations = overfitting_df["interpretation"].dropna().astype(str).tolist()
    return " | ".join(interpretations)


def build_interpretation_note(
    run_name: str,
    validation_type: str,
    r2_gap: object,
    rmse_ratio: object,
) -> str:
    """Create a concise per-run interpretation note."""
    notes: list[str] = []
    if "group" in validation_type:
        notes.append("Group-aware validation estimates battery-level generalization.")
    elif validation_type == "random_split":
        notes.append("Random split may mix cycles from the same battery.")

    if pd.notna(r2_gap) and float(r2_gap) > 0.2:
        notes.append("Large R2 gap suggests possible overfitting.")
    if pd.notna(rmse_ratio) and float(rmse_ratio) > 1.5:
        notes.append("Test RMSE is much higher than train RMSE.")
    if "feature" in run_name:
        notes.append("Uses raw-discharge-derived feature summary columns.")
    if "metadata" in run_name:
        notes.append("Uses metadata-level cycle summary columns only.")
    return " ".join(notes)


def summarize_run(run_name: str, run_path: Path) -> dict[str, object]:
    """Summarize one simulation run folder."""
    metrics_df = read_required_csv(run_name, run_path, "train_test_metrics")
    overfitting_df = read_required_csv(run_name, run_path, "overfitting_diagnostics")
    cv_df = read_required_csv(run_name, run_path, "cross_validation_metrics")
    feature_df = read_required_csv(run_name, run_path, "feature_importance")

    train_r2 = value_from_dataset(metrics_df, "train", "r2")
    test_r2 = value_from_dataset(metrics_df, "test", "r2")
    train_mae = value_from_dataset(metrics_df, "train", "mae")
    test_mae = value_from_dataset(metrics_df, "test", "mae")
    train_rmse = value_from_dataset(metrics_df, "train", "rmse")
    test_rmse = value_from_dataset(metrics_df, "test", "rmse")
    r2_gap = train_r2 - test_r2 if pd.notna(train_r2) and pd.notna(test_r2) else np.nan
    rmse_ratio = (
        test_rmse / train_rmse
        if pd.notna(train_rmse) and pd.notna(test_rmse) and train_rmse != 0
        else np.nan
    )
    validation_type = infer_validation_type(metrics_df)
    top_1_feature, top_1_importance, top_3_features = summarize_feature_importance(
        feature_df
    )
    cv_summary = summarize_cross_validation(cv_df)

    return {
        "run_name": run_name,
        "validation_type": validation_type,
        "train_r2": train_r2,
        "test_r2": test_r2,
        "r2_gap": r2_gap,
        "train_mae": train_mae,
        "test_mae": test_mae,
        "train_rmse": train_rmse,
        "test_rmse": test_rmse,
        "rmse_ratio": rmse_ratio,
        **cv_summary,
        "top_1_feature": top_1_feature,
        "top_1_importance": top_1_importance,
        "top_3_features": top_3_features,
        "overfitting_summary": summarize_overfitting(overfitting_df),
        "interpretation_note": build_interpretation_note(
            run_name=run_name,
            validation_type=validation_type,
            r2_gap=r2_gap,
            rmse_ratio=rmse_ratio,
        ),
    }


def build_comparison_table(run_specs: list[str]) -> pd.DataFrame:
    """Build comparison rows for all requested simulation runs."""
    rows = []
    for spec in run_specs:
        run_name, run_path = parse_run_spec(spec)
        rows.append(summarize_run(run_name, run_path))
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def format_value(value: object) -> str:
    """Format a Markdown table cell."""
    if pd.isna(value):
        return ""
    if isinstance(value, (float, np.floating)):
        return f"{value:.4f}"
    return str(value).replace("|", r"\|").replace("\n", " ")


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    """Convert a DataFrame to a compact Markdown table."""
    if df.empty:
        return "No data available."
    headers = [str(column) for column in df.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(format_value(row[column]) for column in headers) + " |")
    return "\n".join(lines)


def row_by_name(comparison_df: pd.DataFrame, run_name: str) -> pd.Series | None:
    """Return a comparison row by run_name."""
    rows = comparison_df[comparison_df["run_name"] == run_name]
    if rows.empty:
        return None
    return rows.iloc[0]


def metric_delta_text(
    comparison_df: pd.DataFrame,
    baseline_name: str,
    candidate_name: str,
    metric: str,
) -> str:
    """Describe a metric difference between two named rows."""
    baseline = row_by_name(comparison_df, baseline_name)
    candidate = row_by_name(comparison_df, candidate_name)
    if baseline is None or candidate is None:
        return f"- `{baseline_name}` or `{candidate_name}` was not available."
    baseline_value = baseline[metric]
    candidate_value = candidate[metric]
    if pd.isna(baseline_value) or pd.isna(candidate_value):
        return f"- `{metric}` could not be compared for `{baseline_name}` and `{candidate_name}`."
    delta = candidate_value - baseline_value
    return (
        f"- `{candidate_name}` {metric}: {candidate_value:.4f}; "
        f"`{baseline_name}` {metric}: {baseline_value:.4f}; delta: {delta:.4f}."
    )


def build_markdown_report(comparison_df: pd.DataFrame) -> str:
    """Build the simulation comparison Markdown report."""
    compact_columns = [
        "run_name",
        "validation_type",
        "test_r2",
        "r2_gap",
        "test_rmse",
        "rmse_ratio",
        "cv_r2_mean",
        "cv_rmse_mean",
        "top_1_feature",
    ]
    compact_table = comparison_df[compact_columns]

    raw_count_delta = metric_delta_text(
        comparison_df,
        "feature_group",
        "feature_no_count_group",
        "test_r2",
    )
    raw_count_rmse_delta = metric_delta_text(
        comparison_df,
        "feature_group",
        "feature_no_count_group",
        "test_rmse",
    )

    return "\n".join(
        [
            "# Kaggle Battery Simulation Comparison",
            "",
            "## Dataset and analysis-ready filtering summary",
            "",
            "- The case study uses Kaggle NASA battery discharge metadata and analysis-ready rows filtered by `retention_quality_flag == normal`.",
            "- Full quality-audited rows remain available in `kaggle_nasa_battery_cycle_summary.csv`; analyzer-facing runs use the analysis-ready summary or feature-joined analysis-ready table.",
            "- Raw discharge CSV files are summarized into scalar features only; raw time-series rows are not merged into the analyzer table.",
            "",
            "## Model comparison table",
            "",
            dataframe_to_markdown(compact_table),
            "",
            "## Random split vs group split interpretation",
            "",
            "- Random split runs can place cycles from the same battery in both train and test sets, which may overstate cycle-level predictive performance.",
            "- Group split runs use `battery_id` separation and are the more relevant check for battery-level generalization.",
            metric_delta_text(comparison_df, "metadata_random", "metadata_group", "test_r2"),
            metric_delta_text(comparison_df, "feature_random", "feature_group", "test_r2"),
            "",
            "## Metadata-only vs feature-enriched interpretation",
            "",
            "- Metadata-only runs use cycle index, ambient temperature, and capacity-style metadata features.",
            "- Feature-enriched runs include scalar summaries from raw discharge curves such as duration, voltage, current, and temperature statistics.",
            metric_delta_text(comparison_df, "metadata_random", "feature_random", "test_r2"),
            metric_delta_text(comparison_df, "metadata_group", "feature_group", "test_r2"),
            "",
            "## raw_sample_count exclusion result",
            "",
            "- `feature_no_count_group` excludes `raw_sample_count` to reduce dependence on a feature that may encode measurement length or logging behavior.",
            raw_count_delta,
            raw_count_rmse_delta,
            "",
            "## Limitations",
            "",
            "- These comparisons are case-study diagnostics, not proof of a production-ready battery degradation model.",
            "- The current features are cycle-level summaries and do not model sequence history directly.",
            "- Group-aware validation is stricter than random splitting, but it still depends on available battery diversity and metadata quality.",
            "- Feature importance is model-specific and should be interpreted as a screening signal, not a causal explanation.",
            "",
            "## Next step: battery-level generalization and lagged forecasting",
            "",
            "- Use group-aware validation as the default for battery-level claims.",
            "- Add lagged cycle features and battery-level holdout studies before forecasting future retention.",
            "- Compare simple baseline forecasting approaches before adding more complex time-series ML/DL.",
            "",
        ]
    )


def main() -> None:
    """Run the comparison utility."""
    args = parse_args()
    run_specs = resolve_run_specs(args.runs or args.run)
    try:
        comparison_df = build_comparison_table(run_specs)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        comparison_df.to_csv(output_path, index=False)

        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(build_markdown_report(comparison_df), encoding="utf-8")
    except (FileNotFoundError, ValueError) as exc:
        print(f"Simulation run comparison failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"output path: {output_path}")
    print(f"report path: {report_path}")
    print(f"run count: {len(comparison_df)}")
    print("runs:")
    for run_name in comparison_df["run_name"]:
        print(f"- {run_name}")


if __name__ == "__main__":
    main()
