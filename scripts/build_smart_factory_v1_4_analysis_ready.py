"""Build SECOM v1.4.3 analysis-ready and audit artifacts.

This script reads local-only SECOM raw files created by the v1.4.2 access gate.
It does not call a network API, download data, train models, select features by
target association, or generate SPC charts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from connectors.smart_factory import sha256_file  # noqa: E402
from loaders.process_quality import (  # noqa: E402
    ProcessQualityLoadConfig,
    build_row_position_aligned_table,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Build Smart Factory v1.4.3 SECOM analysis-ready artifacts."
    )
    parser.add_argument(
        "--normalization-spec",
        default="data/case_studies/smart_factory/normalization_spec_v1_4.json",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def build_load_config(spec: dict[str, Any]) -> ProcessQualityLoadConfig:
    """Build generic loader config from normalization spec."""
    target_mapping = {
        int(raw_value): int(mapping["target_failure"])
        for raw_value, mapping in spec["target_mapping"].items()
    }
    return ProcessQualityLoadConfig(
        feature_prefix=spec["feature_naming"]["prefix"],
        target_mapping=target_mapping,
        timestamp_format=spec["timestamp"]["parse_format"],
        timestamp_dayfirst=bool(spec["timestamp"]["dayfirst"]),
        raw_target_column=spec["target_columns"]["raw"],
        mapped_target_column=spec["target_columns"]["mapped"],
        timestamp_column=spec["timestamp"]["parsed_column"],
        raw_timestamp_column=spec["timestamp"]["raw_column"],
        sample_index_column="sample_index",
        source_order_column=spec["row_order_preservation"]["source_order_column"],
        chronological_rank_column=spec["timestamp"]["chronological_rank_column"],
    )


def verify_source_hashes(raw_dir: Path, manifest: dict[str, Any]) -> dict[str, str]:
    """Verify local raw file hashes against acquisition manifest."""
    observed: dict[str, str] = {}
    for record in manifest["raw_files"]:
        path = raw_dir / record["relative_path"]
        digest = sha256_file(path)
        if digest != record["sha256"]:
            raise ValueError(
                f"Source checksum changed for {record['relative_path']}: "
                f"{digest} != {record['sha256']}"
            )
        observed[record["relative_path"]] = digest
    return observed


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Return deterministic process feature columns."""
    return [column for column in df.columns if column.startswith("process_feature_")]


def build_feature_quality_inventory(
    df: pd.DataFrame,
    thresholds: dict[str, float],
) -> pd.DataFrame:
    """Build target-independent feature-quality inventory."""
    rows: list[dict[str, Any]] = []
    n_rows = len(df)
    for feature_name in feature_columns(df):
        source_column_index = int(feature_name.rsplit("_", 1)[1])
        values = pd.to_numeric(df[feature_name], errors="coerce")
        non_missing = values.dropna()
        missing_count = int(values.isna().sum())
        missing_rate = float(missing_count / n_rows) if n_rows else 0.0
        finite_mask = np.isfinite(non_missing.to_numpy(dtype=float)) if len(non_missing) else np.array([])
        finite_count = int(finite_mask.sum())
        infinite_status = "has_infinite" if finite_count < len(non_missing) else "no_infinite"
        unique_count = int(non_missing.nunique(dropna=True))
        all_missing = missing_count == n_rows
        constant = bool(not all_missing and unique_count <= 1)
        if len(non_missing):
            top_value_rate = float(non_missing.value_counts(dropna=True).iloc[0] / len(non_missing))
        else:
            top_value_rate = 0.0
        near_constant = bool(
            not all_missing
            and not constant
            and top_value_rate >= thresholds["near_constant_top_value_rate_min"]
        )
        readiness_category, exclusion_reason = classify_feature_readiness(
            missing_rate=missing_rate,
            all_missing=all_missing,
            constant=constant,
            near_constant=near_constant,
            thresholds=thresholds,
        )
        quantiles = (
            values.quantile([0.01, 0.25, 0.5, 0.75, 0.99])
            if not all_missing
            else pd.Series([np.nan] * 5, index=[0.01, 0.25, 0.5, 0.75, 0.99])
        )
        rows.append(
            {
                "feature_name": feature_name,
                "source_column_index": source_column_index,
                "dtype": str(df[feature_name].dtype),
                "non_missing_count": int(non_missing.size),
                "missing_count": missing_count,
                "missing_rate": missing_rate,
                "unique_count": unique_count,
                "finite_count": finite_count,
                "mean": float(values.mean()) if not all_missing else np.nan,
                "std": float(values.std()) if not all_missing else np.nan,
                "median": float(quantiles.loc[0.5]) if not all_missing else np.nan,
                "q01": float(quantiles.loc[0.01]) if not all_missing else np.nan,
                "q25": float(quantiles.loc[0.25]) if not all_missing else np.nan,
                "q75": float(quantiles.loc[0.75]) if not all_missing else np.nan,
                "q99": float(quantiles.loc[0.99]) if not all_missing else np.nan,
                "minimum": float(values.min()) if not all_missing else np.nan,
                "maximum": float(values.max()) if not all_missing else np.nan,
                "constant_status": "constant" if constant else "not_constant",
                "all_missing_status": "all_missing" if all_missing else "not_all_missing",
                "near_constant_status": "near_constant" if near_constant else "not_near_constant",
                "infinite_status": infinite_status,
                "readiness_category": readiness_category,
                "exclusion_reason": exclusion_reason,
            }
        )
    return pd.DataFrame(rows)


def classify_feature_readiness(
    *,
    missing_rate: float,
    all_missing: bool,
    constant: bool,
    near_constant: bool,
    thresholds: dict[str, float],
) -> tuple[str, str]:
    """Classify a feature using target-independent thresholds."""
    if all_missing:
        return "all_missing", "all_missing"
    if constant:
        return "constant", "constant"
    if near_constant:
        return "near_constant", "near_constant"
    if missing_rate == thresholds["complete_missing_rate_max"]:
        return "complete", ""
    if missing_rate <= thresholds["low_missing_rate_max"]:
        return "low_missing", ""
    if missing_rate <= thresholds["moderate_missing_rate_max"]:
        return "moderate_missing", ""
    if missing_rate <= thresholds["high_missing_rate_max"]:
        return "high_missing", "high_missing"
    return "very_high_missing", "very_high_missing"


def build_integrity_summary(df: pd.DataFrame, duplicate_output_path: Path) -> pd.DataFrame:
    """Build compact duplicate and integrity summary."""
    features = feature_columns(df)
    feature_hash = pd.util.hash_pandas_object(df[features], index=False)
    exact_duplicate_count = int(df.duplicated(subset=features, keep=False).sum())
    duplicate_groups = (
        pd.DataFrame({"feature_hash": feature_hash, "target_failure": df["target_failure"]})
        .groupby("feature_hash", dropna=False)
        .agg(row_count=("target_failure", "size"), target_nunique=("target_failure", "nunique"))
        .reset_index()
    )
    duplicate_feature_groups = duplicate_groups[duplicate_groups["row_count"] > 1]
    conflicting_groups = duplicate_feature_groups[duplicate_feature_groups["target_nunique"] > 1]
    same_target_groups = duplicate_feature_groups[duplicate_feature_groups["target_nunique"] == 1]

    duplicate_rows = df.loc[feature_hash.isin(set(duplicate_feature_groups["feature_hash"]))]
    duplicate_output_path.parent.mkdir(parents=True, exist_ok=True)
    duplicate_rows[
        [
            "sample_index",
            "source_timestamp_raw",
            "observation_timestamp",
            "target_raw",
            "target_failure",
        ]
    ].to_csv(duplicate_output_path, index=False)

    timestamp_duplicate_count = int(df["observation_timestamp"].duplicated(keep=False).sum())
    timestamp_feature_duplicate_count = int(
        pd.DataFrame(
            {
                "timestamp": df["observation_timestamp"],
                "feature_hash": feature_hash,
            }
        )
        .duplicated(keep=False)
        .sum()
    )
    feature_values = df[features]
    all_zero_rows = int(feature_values.fillna(np.nan).eq(0).all(axis=1).sum())
    all_missing_rows = int(feature_values.isna().all(axis=1).sum())
    non_finite_values = int(np.isinf(feature_values.to_numpy(dtype=float)).sum())
    source_order_inversions = int(
        (df.sort_values("source_order_index")["observation_timestamp"].diff().dt.total_seconds() < 0).sum()
    )
    rows = [
        ("exact_duplicate_full_feature_rows", exact_duplicate_count, "ready"),
        ("duplicate_feature_rows_same_target", int(same_target_groups["row_count"].sum()), "ready"),
        (
            "duplicate_feature_rows_conflicting_target",
            int(conflicting_groups["row_count"].sum()),
            "ready" if conflicting_groups.empty else "not_ready",
        ),
        ("duplicate_timestamps", timestamp_duplicate_count, "conditionally_ready" if timestamp_duplicate_count else "ready"),
        ("duplicate_timestamp_feature_vector_rows", timestamp_feature_duplicate_count, "ready"),
        ("all_zero_rows", all_zero_rows, "ready" if all_zero_rows == 0 else "conditionally_ready"),
        ("all_missing_rows", all_missing_rows, "ready" if all_missing_rows == 0 else "not_ready"),
        ("non_finite_values", non_finite_values, "ready" if non_finite_values == 0 else "not_ready"),
        (
            "source_order_chronological_inversions",
            source_order_inversions,
            "ready" if source_order_inversions == 0 else "conditionally_ready",
        ),
    ]
    return pd.DataFrame(
        [
            {
                "check": check,
                "value": value,
                "status": status,
                "note": integrity_note(check),
            }
            for check, value, status in rows
        ]
    )


def integrity_note(check: str) -> str:
    """Return note for integrity summary check."""
    notes = {
        "duplicate_feature_rows_conflicting_target": "Conflicting duplicate feature vectors should stop future modeling if nonzero.",
        "duplicate_timestamps": "Equal timestamps are retained; source_order_index is the deterministic tie-breaker.",
        "source_order_chronological_inversions": "Computed in source row order before any chronological ranking.",
    }
    return notes.get(check, "Compact integrity count; row-level diagnostics are local-only.")


def build_missingness_summary(
    df: pd.DataFrame,
    feature_inventory: pd.DataFrame,
) -> pd.DataFrame:
    """Build compact missingness audit summary."""
    features = feature_columns(df)
    feature_values = df[features]
    total_values = int(feature_values.size)
    total_missing = int(feature_values.isna().sum().sum())
    row_missing_rate = feature_values.isna().mean(axis=1)
    rows: list[dict[str, Any]] = [
        {
            "section": "dataset",
            "metric": "dataset_wide_missing_rate",
            "value": float(total_missing / total_values) if total_values else 0.0,
            "status": "descriptive",
            "note": "Feature-matrix missingness only.",
        }
    ]
    bins = [
        ("complete", 0.0, 0.0),
        ("low_missing", 0.0, 0.05),
        ("moderate_missing", 0.05, 0.2),
        ("high_missing", 0.2, 0.5),
        ("very_high_missing", 0.5, 1.0),
    ]
    for name, lower, upper in bins:
        if name == "complete":
            count = int((feature_inventory["missing_rate"] == 0.0).sum())
        else:
            count = int(
                ((feature_inventory["missing_rate"] > lower) & (feature_inventory["missing_rate"] <= upper)).sum()
            )
        rows.append(
            {
                "section": "feature_missing_rate_distribution",
                "metric": name,
                "value": count,
                "status": "descriptive",
                "note": "Target-independent feature missingness bucket.",
            }
        )
    for threshold in [0.05, 0.2, 0.5, 0.8]:
        rows.append(
            {
                "section": "row_missing_rate_threshold",
                "metric": f"rows_missing_rate_above_{threshold}",
                "value": int((row_missing_rate > threshold).sum()),
                "status": "descriptive",
                "note": "Rows are retained in v1.4.3.",
            }
        )
    temporal = (
        pd.DataFrame(
            {
                "month": df["observation_timestamp"].dt.to_period("M").astype(str),
                "row_missing_rate": row_missing_rate,
            }
        )
        .groupby("month")["row_missing_rate"]
        .mean()
    )
    if not temporal.empty:
        rows.extend(
            [
                {
                    "section": "temporal_missingness_change",
                    "metric": "monthly_missing_rate_min",
                    "value": float(temporal.min()),
                    "status": "descriptive",
                    "note": "Temporal missingness drift proxy.",
                },
                {
                    "section": "temporal_missingness_change",
                    "metric": "monthly_missing_rate_max",
                    "value": float(temporal.max()),
                    "status": "descriptive",
                    "note": "Temporal missingness drift proxy.",
                },
            ]
        )
    subgroup = (
        pd.DataFrame(
            {
                "target_failure": df["target_failure"],
                "row_missing_rate": row_missing_rate,
            }
        )
        .groupby("target_failure")["row_missing_rate"]
        .mean()
    )
    for target_value, missing_rate in subgroup.items():
        rows.append(
            {
                "section": "failure_pass_subgroup_missingness",
                "metric": f"target_failure_{target_value}_mean_row_missing_rate",
                "value": float(missing_rate),
                "status": "descriptive_post_hoc",
                "note": "Do not use subgroup missingness as a feature-selection criterion.",
            }
        )
    return pd.DataFrame(rows)


def build_temporal_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Build compact temporal integrity summary."""
    timestamps = df["observation_timestamp"]
    sorted_timestamps = timestamps.sort_values(kind="mergesort")
    gaps = sorted_timestamps.diff().dt.total_seconds().dropna()
    duplicate_count = int(timestamps.duplicated(keep=False).sum())
    source_monotonic = bool(
        df.sort_values("source_order_index")["observation_timestamp"].dropna().is_monotonic_increasing
    )
    chronological_reorder_needed = bool(
        not (df["source_order_index"].equals(df.sort_values("chronological_rank")["source_order_index"].reset_index(drop=True)))
    )
    rows = [
        ("timestamp_min", timestamps.min(), "ready", "Minimum parsed timestamp."),
        ("timestamp_max", timestamps.max(), "ready", "Maximum parsed timestamp."),
        ("timestamp_parse_failure_count", int(timestamps.isna().sum()), "ready", "Explicit day-first format parse failures."),
        ("duplicate_timestamp_count", duplicate_count, "conditionally_ready" if duplicate_count else "ready", "Equal timestamps use source order tie-break."),
        ("source_order_monotonicity", source_monotonic, "ready" if source_monotonic else "conditionally_ready", "Evaluated before any chronological sorting."),
        ("chronological_reorder_needed", chronological_reorder_needed, "conditionally_ready" if chronological_reorder_needed else "ready", "True means source order differs from chronological rank."),
        ("min_time_gap_seconds", float(gaps.min()) if not gaps.empty else np.nan, "descriptive", "Chronological adjacent gap."),
        ("median_time_gap_seconds", float(gaps.median()) if not gaps.empty else np.nan, "descriptive", "Chronological adjacent gap."),
        ("max_time_gap_seconds", float(gaps.max()) if not gaps.empty else np.nan, "descriptive", "Chronological adjacent gap."),
    ]
    for freq_name, period in [("day", "D"), ("week", "W"), ("month", "M")]:
        counts = timestamps.dt.to_period(period).value_counts().sort_index()
        if counts.empty:
            continue
        rows.append(
            (
                f"sample_density_by_{freq_name}",
                f"periods={len(counts)}; min={int(counts.min())}; max={int(counts.max())}",
                "descriptive",
                "Sample density by parsed timestamp period.",
            )
        )
    monthly_target = (
        pd.DataFrame(
            {
                "month": timestamps.dt.to_period("M").astype(str),
                "target_failure": df["target_failure"],
            }
        )
        .groupby("month")["target_failure"]
        .agg(["count", "sum", "mean"])
    )
    if not monthly_target.empty:
        rows.append(
            (
                "target_prevalence_over_months",
                f"periods={len(monthly_target)}; fail_rate_min={monthly_target['mean'].min():.6f}; fail_rate_max={monthly_target['mean'].max():.6f}",
                "descriptive_post_hoc",
                "Target prevalence over time is descriptive and not a feature-selection rule.",
            )
        )
    return pd.DataFrame(
        [
            {"metric": metric, "value": value, "status": status, "note": note}
            for metric, value, status, note in rows
        ]
    )


def build_split_feasibility(
    df: pd.DataFrame,
    thresholds: dict[str, int],
) -> pd.DataFrame:
    """Build candidate chronological split feasibility table without modeling."""
    ordered = df.sort_values(["observation_timestamp", "source_order_index"], kind="mergesort").reset_index(drop=True)
    n_rows = len(ordered)
    candidates: list[tuple[str, str, int, int]] = [
        ("expanding_train_future_test_60_20", "expanding_train_future_test", int(n_rows * 0.60), int(n_rows * 0.80)),
        ("expanding_train_future_test_70_15", "expanding_train_future_test", int(n_rows * 0.70), int(n_rows * 0.85)),
        ("final_holdout_period_80_20", "final_holdout_period", int(n_rows * 0.80), n_rows),
    ]
    fold_edges = np.linspace(0, n_rows, 6, dtype=int)
    for fold_idx in range(1, 5):
        candidates.append(
            (
                f"blocked_chronological_fold_{fold_idx}",
                "blocked_chronological_fold",
                int(fold_edges[fold_idx]),
                int(fold_edges[fold_idx + 1]),
            )
        )
    rows = []
    for split_name, split_type, train_end, test_end in candidates:
        train = ordered.iloc[:train_end]
        test = ordered.iloc[train_end:test_end]
        rows.append(build_split_row(split_name, split_type, train, test, thresholds))
    return pd.DataFrame(rows)


def build_split_row(
    split_name: str,
    split_type: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
    thresholds: dict[str, int],
) -> dict[str, Any]:
    """Build one chronological split feasibility row."""
    train_failures = int(train["target_failure"].sum()) if not train.empty else 0
    test_failures = int(test["target_failure"].sum()) if not test.empty else 0
    leakage_status = "no_future_to_past"
    if not train.empty and not test.empty and train["observation_timestamp"].max() > test["observation_timestamp"].min():
        leakage_status = "time_overlap"
    feasible = (
        len(train) >= thresholds["min_train_rows"]
        and len(test) >= thresholds["min_test_rows"]
        and train_failures >= thresholds["min_train_failures"]
        and test_failures >= thresholds["min_test_failures"]
        and leakage_status == "no_future_to_past"
    )
    reason = []
    if len(train) < thresholds["min_train_rows"]:
        reason.append("too_few_train_rows")
    if len(test) < thresholds["min_test_rows"]:
        reason.append("too_few_test_rows")
    if train_failures < thresholds["min_train_failures"]:
        reason.append("too_few_train_failures")
    if test_failures < thresholds["min_test_failures"]:
        reason.append("too_few_test_failures")
    if leakage_status != "no_future_to_past":
        reason.append("time_leakage")
    return {
        "split_name": split_name,
        "split_type": split_type,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_failures": train_failures,
        "test_failures": test_failures,
        "train_time_start": train["observation_timestamp"].min() if not train.empty else "",
        "train_time_end": train["observation_timestamp"].max() if not train.empty else "",
        "test_time_start": test["observation_timestamp"].min() if not test.empty else "",
        "test_time_end": test["observation_timestamp"].max() if not test.empty else "",
        "leakage_status": leakage_status,
        "feasibility_status": "feasible" if feasible else "not_feasible",
        "infeasibility_reason": ";".join(reason),
        "primary_validation_candidate": bool(feasible),
    }


def build_spc_feasibility(
    feature_inventory: pd.DataFrame,
    spec: dict[str, Any],
) -> pd.DataFrame:
    """Build conservative SPC and capability feasibility summary."""
    thresholds = spec["feature_quality_thresholds"]
    candidate_features = feature_inventory[
        (feature_inventory["non_missing_count"] >= thresholds["min_non_missing_for_spc_candidate"])
        & (feature_inventory["constant_status"] == "not_constant")
        & (feature_inventory["all_missing_status"] == "not_all_missing")
        & (feature_inventory["infinite_status"] == "no_infinite")
    ]
    return pd.DataFrame(
        [
            {
                "analysis": "I-MR",
                "status": "conditional_stable_baseline_required",
                "candidate_feature_count": int(len(candidate_features)),
                "note": "No chart is generated in v1.4.3; candidates are target-independent coverage/finite/non-constant features.",
            },
            {
                "analysis": "X-bar/R",
                "status": "not_ready_no_rational_subgroup",
                "candidate_feature_count": 0,
                "note": "SECOM has no explicit rational subgroup identifier.",
            },
            {
                "analysis": "X-bar/S",
                "status": "not_ready_no_rational_subgroup",
                "candidate_feature_count": 0,
                "note": "SECOM has no explicit rational subgroup identifier.",
            },
            {
                "analysis": "p/np chart",
                "status": "conditional_chronological_aggregation_required",
                "candidate_feature_count": 1,
                "note": "Only target counts by valid chronological intervals may be considered later.",
            },
            {
                "analysis": "Cp/Cpk/Pp/Ppk",
                "status": "not_ready_no_specification_limits",
                "candidate_feature_count": 0,
                "note": "No specification limits are available; capability indices must not be calculated.",
            },
        ]
    )


def build_analysis_ready_summary(
    df: pd.DataFrame,
    feature_inventory: pd.DataFrame,
    integrity_summary: pd.DataFrame,
    raw_hash_before: dict[str, str],
    raw_hash_after: dict[str, str],
) -> pd.DataFrame:
    """Build compact analysis-ready summary."""
    features = feature_columns(df)
    source_sha_unchanged = raw_hash_before == raw_hash_after
    return pd.DataFrame(
        [
            {"metric": "row_count", "value": len(df), "status": "ready"},
            {"metric": "feature_count", "value": len(features), "status": "ready"},
            {"metric": "target_failure_count", "value": int(df["target_failure"].sum()), "status": "ready"},
            {"metric": "target_pass_count", "value": int((df["target_failure"] == 0).sum()), "status": "ready"},
            {"metric": "timestamp_parse_failure_count", "value": int(df["observation_timestamp"].isna().sum()), "status": "ready"},
            {
                "metric": "source_sha_unchanged",
                "value": str(source_sha_unchanged),
                "status": "ready" if source_sha_unchanged else "not_ready",
            },
            {
                "metric": "analysis_ready_local_only",
                "value": "data/processed/smart_factory_v1_4_secom_analysis_ready.csv",
                "status": "local_only",
            },
            {
                "metric": "usable_feature_categories",
                "value": int(feature_inventory["readiness_category"].isin(["complete", "low_missing", "moderate_missing"]).sum()),
                "status": "descriptive",
            },
            {
                "metric": "conflicting_duplicate_feature_rows",
                "value": int(
                    integrity_summary.loc[
                        integrity_summary["check"] == "duplicate_feature_rows_conflicting_target",
                        "value",
                    ].iloc[0]
                ),
                "status": "ready",
            },
        ]
    )


def write_csv(path: Path, df: pd.DataFrame) -> None:
    """Write CSV with parent creation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def main() -> None:
    """Run v1.4.3 analysis-ready normalization and audits."""
    args = parse_args()
    spec_path = PROJECT_ROOT / args.normalization_spec
    spec = load_json(spec_path)
    manifest = load_json(PROJECT_ROOT / spec["source_artifacts"]["acquisition_manifest"])
    raw_feature_path = PROJECT_ROOT / spec["source_artifacts"]["feature_matrix"]
    raw_label_path = PROJECT_ROOT / spec["source_artifacts"]["label_timestamp_file"]
    raw_dir = raw_feature_path.parent
    raw_hash_before = verify_source_hashes(raw_dir, manifest)

    config = build_load_config(spec)
    analysis_ready = build_row_position_aligned_table(raw_feature_path, raw_label_path, config)
    analysis_ready_path = PROJECT_ROOT / spec["local_output_paths"]["analysis_ready"]
    write_csv(analysis_ready_path, analysis_ready)

    feature_inventory = build_feature_quality_inventory(
        analysis_ready,
        spec["feature_quality_thresholds"],
    )
    duplicate_output_path = PROJECT_ROOT / spec["local_output_paths"]["row_level_duplicate_diagnostics"]
    integrity_summary = build_integrity_summary(analysis_ready, duplicate_output_path)
    missingness_summary = build_missingness_summary(analysis_ready, feature_inventory)
    temporal_summary = build_temporal_summary(analysis_ready)
    split_feasibility = build_split_feasibility(
        analysis_ready,
        spec["split_feasibility_thresholds"],
    )
    spc_feasibility = build_spc_feasibility(feature_inventory, spec)

    raw_hash_after = verify_source_hashes(raw_dir, manifest)
    analysis_ready_summary = build_analysis_ready_summary(
        analysis_ready,
        feature_inventory,
        integrity_summary,
        raw_hash_before,
        raw_hash_after,
    )

    outputs = spec["tracked_output_paths"]
    write_csv(PROJECT_ROOT / outputs["feature_quality_inventory"], feature_inventory)
    write_csv(PROJECT_ROOT / outputs["integrity_summary"], integrity_summary)
    write_csv(PROJECT_ROOT / outputs["missingness_summary"], missingness_summary)
    write_csv(PROJECT_ROOT / outputs["temporal_summary"], temporal_summary)
    write_csv(PROJECT_ROOT / outputs["split_feasibility"], split_feasibility)
    write_csv(PROJECT_ROOT / outputs["spc_feasibility"], spc_feasibility)
    write_csv(PROJECT_ROOT / outputs["analysis_ready_summary"], analysis_ready_summary)

    print("Analysis-ready rows:", len(analysis_ready))
    print("Process features:", len(feature_columns(analysis_ready)))
    print("Analysis-ready output:", spec["local_output_paths"]["analysis_ready"])
    print("Feature quality inventory:", outputs["feature_quality_inventory"])
    print("Integrity summary:", outputs["integrity_summary"])
    print("Missingness summary:", outputs["missingness_summary"])
    print("Temporal summary:", outputs["temporal_summary"])
    print("Split feasibility:", outputs["split_feasibility"])
    print("SPC feasibility:", outputs["spc_feasibility"])
    print("Source SHA unchanged:", raw_hash_before == raw_hash_after)


if __name__ == "__main__":
    main()
