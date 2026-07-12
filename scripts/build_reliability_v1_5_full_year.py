"""Build Reliability v1.5.3 Backblaze full-year normalization audit.

This script reads the local Backblaze 2013 ZIP member-by-member, excludes
macOS metadata, writes a local-only analysis-ready table, and creates compact
tracked summaries for event/censoring integrity and task readiness.

It does not train classifiers, fit survival models, estimate RUL, perform
feature selection, or extract the full archive to raw files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
import time
import zipfile
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from connectors.reliability import calculate_sha256, list_zip_members  # noqa: E402
from loaders.reliability import (  # noqa: E402
    build_full_archive_inventory,
    classify_censoring_status,
    classify_post_failure_status,
    normalize_backblaze_daily_frame,
    quantile_dict,
    select_valid_daily_members,
    smart_feature_metadata,
)


CASE_VERSION = "v1.5.3"
DATASET_ID = "backblaze_drive_stats"
EXPECTED_ARCHIVE_SHA = "7f5a53e79b16e695b4b034955806bb3bb194534b169f6eca460dfd3dc48096fe"
HORIZONS = [1, 3, 7, 14, 30]
LOOKBACKS = [0, 3, 7, 14, 30]
UNIQUE_VALUE_CAP = 10000
ASSET_COVERAGE_CAP = 10000


@dataclass
class AssetStats:
    """Source-derived trajectory summary for one asset."""

    obs_count: int = 0
    first_date: date | None = None
    last_date: date | None = None
    models: set[str] = field(default_factory=set)
    capacities: set[int] = field(default_factory=set)
    dates: list[date] = field(default_factory=list)
    failure_dates: list[date] = field(default_factory=list)
    duplicate_asset_date_rows: int = 0


@dataclass
class FeatureStats:
    """Compact SMART feature statistics accumulated across daily members."""

    feature_name: str
    member_count: int = 0
    non_missing_count: int = 0
    missing_count: int = 0
    negative_count: int = 0
    non_numeric_count: int = 0
    unique_values: set[str] = field(default_factory=set)
    unique_capped: bool = False
    assets: set[str] = field(default_factory=set)
    asset_coverage_capped: bool = False


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Build Backblaze full-year reliability normalization audit."
    )
    parser.add_argument(
        "--archive",
        default="data/raw/reliability/backblaze_drive_stats/data_2013.zip",
    )
    parser.add_argument(
        "--analysis-ready-output",
        default="data/processed/reliability_v1_5_backblaze_analysis_ready.csv",
    )
    parser.add_argument(
        "--normalization-spec",
        default="data/case_studies/reliability/normalization_spec_v1_5.json",
    )
    parser.add_argument(
        "--full-year-manifest",
        default="data/case_studies/reliability/full_year_manifest_v1_5.json",
    )
    parser.add_argument(
        "--archive-inventory-output",
        default="data/processed/reliability_v1_5_full_archive_inventory.csv",
    )
    parser.add_argument(
        "--schema-drift-output",
        default="data/processed/reliability_v1_5_schema_drift_summary.csv",
    )
    parser.add_argument(
        "--trajectory-output",
        default="data/processed/reliability_v1_5_trajectory_summary.csv",
    )
    parser.add_argument(
        "--event-output",
        default="data/processed/reliability_v1_5_event_integrity_summary.csv",
    )
    parser.add_argument(
        "--censoring-output",
        default="data/processed/reliability_v1_5_censoring_summary.csv",
    )
    parser.add_argument(
        "--temporal-output",
        default="data/processed/reliability_v1_5_temporal_coverage_summary.csv",
    )
    parser.add_argument(
        "--smart-output",
        default="data/processed/reliability_v1_5_smart_feature_inventory.csv",
    )
    parser.add_argument(
        "--leakage-output",
        default="data/processed/reliability_v1_5_full_leakage_audit.csv",
    )
    parser.add_argument(
        "--horizon-output",
        default="data/processed/reliability_v1_5_horizon_feasibility.csv",
    )
    parser.add_argument(
        "--lookback-output",
        default="data/processed/reliability_v1_5_lookback_feasibility.csv",
    )
    parser.add_argument(
        "--split-output",
        default="data/processed/reliability_v1_5_split_feasibility.csv",
    )
    parser.add_argument(
        "--full-readiness-output",
        default="data/processed/reliability_v1_5_full_readiness_summary.csv",
    )
    parser.add_argument(
        "--task-output",
        default="data/processed/reliability_v1_5_full_task_readiness.csv",
    )
    parser.add_argument(
        "--local-diagnostics-dir",
        default="outputs/reliability_v1_5_local",
    )
    return parser.parse_args()


def utc_now_iso() -> str:
    """Return a UTC timestamp for provenance records."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_daily_csv_from_zip(archive: zipfile.ZipFile, member: str) -> pd.DataFrame:
    """Read one daily CSV member from a ZIP archive."""
    with archive.open(member) as handle:
        return pd.read_csv(handle, encoding="utf-8", encoding_errors="replace", low_memory=False)


def read_header_from_zip(archive: zipfile.ZipFile, member: str) -> list[str]:
    """Read a member's CSV header only."""
    with archive.open(member) as handle:
        text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace", newline="")
        return next(csv.reader(text))


def build_schema_drift_summary(
    archive_path: Path,
    full_inventory: pd.DataFrame,
    valid_members: list[str],
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Compare headers for all included daily CSV members."""
    signature_rows: dict[str, dict[str, Any]] = {}
    member_schema_status: dict[str, str] = {}
    baseline_header: list[str] | None = None
    with zipfile.ZipFile(archive_path) as archive:
        for member in valid_members:
            header = read_header_from_zip(archive, member)
            baseline_header = baseline_header or header
            signature = hashlib.sha1("\x1f".join(header).encode("utf-8")).hexdigest()
            parsed_date = str(
                full_inventory.loc[full_inventory["member_name"] == member, "parsed_date"].iloc[0]
            )
            added = sorted(set(header) - set(baseline_header))
            removed = sorted(set(baseline_header) - set(header))
            member_schema_status[member] = "compatible" if not added and not removed else "schema_drift"
            if signature not in signature_rows:
                signature_rows[signature] = {
                    "schema_signature": signature,
                    "first_date": parsed_date,
                    "last_date": parsed_date,
                    "member_count": 0,
                    "column_count": len(header),
                    "added_columns": ",".join(added),
                    "removed_columns": ",".join(removed),
                    "compatibility_status": member_schema_status[member],
                    "normalization_action": "use_as_is" if not added and not removed else "union_columns_with_missing_values",
                    "columns": header,
                }
            signature_rows[signature]["member_count"] += 1
            signature_rows[signature]["last_date"] = parsed_date
    rows = []
    for row in signature_rows.values():
        compact = dict(row)
        compact.pop("columns")
        rows.append(compact)
    return pd.DataFrame(rows).sort_values(["first_date"]).reset_index(drop=True), {
        key: value["columns"] for key, value in signature_rows.items()
    } | {"member_schema_status": member_schema_status}


def first_pass_collect(
    archive_path: Path,
    valid_members: list[str],
) -> dict[str, Any]:
    """Collect compact full-year aggregates without keeping all rows in memory."""
    assets: dict[str, AssetStats] = defaultdict(AssetStats)
    feature_stats: dict[str, FeatureStats] = {}
    date_stats: dict[date, dict[str, Any]] = defaultdict(
        lambda: {
            "rows": 0,
            "failure_rows": 0,
            "files": set(),
            "active_assets": set(),
            "new_assets": 0,
            "disappearing_assets": 0,
        }
    )
    duplicate_asset_date_count = 0
    inconsistent_model_assets: set[str] = set()
    inconsistent_capacity_assets: set[str] = set()
    total_rows = 0
    start = time.perf_counter()

    with zipfile.ZipFile(archive_path) as archive:
        for member in valid_members:
            raw = read_daily_csv_from_zip(archive, member)
            frame = normalize_backblaze_daily_frame(
                raw,
                source_member=member,
                source_order_start=total_rows,
            )
            obs_date = pd.to_datetime(frame["observation_date"], errors="coerce").dt.date
            if obs_date.isna().any():
                raise ValueError(f"Unparseable observation date in {member}")
            frame["_obs_day"] = obs_date
            member_date = obs_date.iloc[0]
            date_stats[member_date]["files"].add(member)
            date_stats[member_date]["rows"] += int(len(frame))
            date_stats[member_date]["failure_rows"] += int(frame["event_indicator"].eq(1).sum())
            date_stats[member_date]["active_assets"].update(frame["serial_number"].dropna().astype(str).unique())

            duplicated = frame.duplicated(subset=["serial_number", "observation_date"], keep=False)
            duplicate_asset_date_count += int(duplicated.sum())

            duplicate_counts = (
                frame.groupby(["serial_number", "observation_date"], sort=False)
                .size()
                .loc[lambda values: values > 1]
            )
            if not duplicate_counts.empty:
                for (serial, _), count in duplicate_counts.items():
                    assets[str(serial)].duplicate_asset_date_rows += int(count)

            for row in frame[
                ["serial_number", "_obs_day", "model", "capacity_bytes", "event_indicator"]
            ].itertuples(index=False, name=None):
                serial, obs_day, model, capacity, event_indicator = row
                serial_key = str(serial)
                stats = assets[serial_key]
                stats.obs_count += 1
                stats.dates.append(obs_day)
                if pd.notna(model):
                    stats.models.add(str(model))
                if pd.notna(capacity):
                    stats.capacities.add(int(capacity))
                if int(event_indicator) == 1:
                    stats.failure_dates.append(obs_day)
                stats.first_date = obs_day if stats.first_date is None else min(stats.first_date, obs_day)
                stats.last_date = obs_day if stats.last_date is None else max(stats.last_date, obs_day)
                if len(stats.models) > 1:
                    inconsistent_model_assets.add(serial_key)
                if len(stats.capacities) > 1:
                    inconsistent_capacity_assets.add(serial_key)

            smart_columns = [column for column in frame.columns if str(column).casefold().startswith("smart_")]
            if smart_columns:
                missing_counts = frame[smart_columns].isna().sum()
            for column in smart_columns:
                stats = feature_stats.setdefault(column, FeatureStats(feature_name=column))
                series = frame[column]
                stats.member_count += 1
                missing_count = int(missing_counts[column])
                non_missing_count = int(len(series) - missing_count)
                stats.non_missing_count += non_missing_count
                stats.missing_count += missing_count
                if non_missing_count == 0:
                    continue
                non_missing = series.notna()
                numeric = pd.to_numeric(series, errors="coerce")
                stats.non_numeric_count += int(non_missing_count - numeric.notna().sum())
                stats.negative_count += int(numeric.lt(0).sum())
                if not stats.unique_capped:
                    values = series.dropna().astype(str).unique().tolist()
                    stats.unique_values.update(values)
                    if len(stats.unique_values) > UNIQUE_VALUE_CAP:
                        stats.unique_values = set(list(stats.unique_values)[:UNIQUE_VALUE_CAP])
                        stats.unique_capped = True
                if not stats.asset_coverage_capped:
                    stats.assets.update(
                        frame.loc[non_missing, "serial_number"].dropna().astype(str).unique().tolist()
                    )
                    if len(stats.assets) > ASSET_COVERAGE_CAP:
                        stats.assets = set(list(stats.assets)[:ASSET_COVERAGE_CAP])
                        stats.asset_coverage_capped = True

            total_rows += int(len(frame))

    archive_first_date = min(date_stats)
    archive_last_date = max(date_stats)
    for serial, stats in assets.items():
        if len(stats.models) > 1:
            inconsistent_model_assets.add(serial)
        if len(stats.capacities) > 1:
            inconsistent_capacity_assets.add(serial)
    for stats in assets.values():
        if stats.first_date in date_stats:
            date_stats[stats.first_date]["new_assets"] += 1
        if stats.last_date in date_stats:
            date_stats[stats.last_date]["disappearing_assets"] += 1

    return {
        "assets": dict(assets),
        "feature_stats": feature_stats,
        "date_stats": dict(date_stats),
        "duplicate_asset_date_count": duplicate_asset_date_count,
        "inconsistent_model_assets": inconsistent_model_assets,
        "inconsistent_capacity_assets": inconsistent_capacity_assets,
        "total_rows": total_rows,
        "archive_first_date": archive_first_date,
        "archive_last_date": archive_last_date,
        "processing_seconds_first_pass": round(time.perf_counter() - start, 3),
    }


def write_analysis_ready(
    archive_path: Path,
    valid_members: list[str],
    aggregates: dict[str, Any],
    output_path: Path,
    diagnostics_dir: Path,
) -> dict[str, Any]:
    """Write local-only analysis-ready rows in a second streaming pass."""
    assets: dict[str, AssetStats] = aggregates["assets"]
    archive_last = aggregates["archive_last_date"]
    asset_first = {key: stats.first_date for key, stats in assets.items()}
    asset_last = {key: stats.last_date for key, stats in assets.items()}
    first_failure = {
        key: min(stats.failure_dates) if stats.failure_dates else None
        for key, stats in assets.items()
    }
    failure_count = {key: len(stats.failure_dates) for key, stats in assets.items()}
    censoring_status = {
        key: classify_censoring_status(
            obs_count=stats.obs_count,
            failure_count=len(stats.failure_dates),
            first_failure_date=str(first_failure[key]) if first_failure[key] else "",
            last_observation_date=str(stats.last_date),
            archive_last_date=str(archive_last),
            has_post_failure_observation=bool(
                first_failure[key] is not None and stats.last_date and stats.last_date > first_failure[key]
            ),
        )
        for key, stats in assets.items()
    }
    rank_counter: dict[str, int] = defaultdict(int)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    anomaly_rows: list[dict[str, object]] = []
    rows_written = 0
    start = time.perf_counter()

    with zipfile.ZipFile(archive_path) as archive:
        for member in valid_members:
            raw = read_daily_csv_from_zip(archive, member)
            frame = normalize_backblaze_daily_frame(
                raw,
                source_member=member,
                source_order_start=rows_written,
            )
            serials = frame["serial_number"].astype(str)
            obs_dates = pd.to_datetime(frame["observation_date"]).dt.date
            frame["asset_first_observation_date"] = serials.map(asset_first).astype(str)
            frame["asset_last_observation_date"] = serials.map(asset_last).astype(str)
            ranks = []
            for serial in serials:
                rank_counter[serial] += 1
                ranks.append(rank_counter[serial])
            frame["chronological_rank_within_asset"] = ranks
            frame["observation_number_within_asset"] = ranks
            first_dates = pd.to_datetime(frame["asset_first_observation_date"]).dt.date
            last_dates = pd.to_datetime(frame["asset_last_observation_date"]).dt.date
            frame["days_since_first_observation"] = [
                (obs - first).days for obs, first in zip(obs_dates, first_dates, strict=True)
            ]
            frame["days_to_last_observation"] = [
                (last - obs).days for obs, last in zip(obs_dates, last_dates, strict=True)
            ]
            frame["is_last_observation"] = [
                bool(obs == last) for obs, last in zip(obs_dates, last_dates, strict=True)
            ]
            first_failure_string = {
                key: str(value) if value else "" for key, value in first_failure.items()
            }
            frame["_first_failure_date"] = serials.map(first_failure_string)
            frame["post_failure_status"] = [
                classify_post_failure_status(str(obs), int(failure), str(first_fail))
                for obs, failure, first_fail in zip(
                    frame["observation_date"],
                    frame["event_indicator"],
                    frame["_first_failure_date"],
                    strict=True,
                )
            ]
            frame["censoring_status"] = serials.map(censoring_status)
            frame.drop(columns=["_first_failure_date"], inplace=True)

            post_failure = frame["post_failure_status"].eq("post_failure_observation")
            if post_failure.any():
                anomaly_rows.extend(
                    {
                        "serial_number": row.serial_number,
                        "observation_date": row.observation_date,
                        "source_member": row.source_member,
                        "anomaly_type": "post_failure_observation",
                    }
                    for row in frame.loc[
                        post_failure, ["serial_number", "observation_date", "source_member"]
                    ].itertuples(index=False)
                )
            repeated_failure = frame["event_indicator"].eq(1) & serials.map(failure_count).gt(1)
            if repeated_failure.any():
                anomaly_rows.extend(
                    {
                        "serial_number": row.serial_number,
                        "observation_date": row.observation_date,
                        "source_member": row.source_member,
                        "anomaly_type": "multiple_failure_rows_for_asset",
                    }
                    for row in frame.loc[
                        repeated_failure, ["serial_number", "observation_date", "source_member"]
                    ].itertuples(index=False)
                )

            ordered_columns = [
                "source_member",
                "source_row_index",
                "observation_date",
                "serial_number",
                "model",
                "capacity_bytes",
                "failure",
                "event_indicator",
                "source_order_index",
                "chronological_rank_within_asset",
                "asset_first_observation_date",
                "asset_last_observation_date",
                "observation_number_within_asset",
                "days_since_first_observation",
                "days_to_last_observation",
                "is_last_observation",
                "post_failure_status",
                "censoring_status",
            ]
            smart_columns = [column for column in frame.columns if str(column).casefold().startswith("smart_")]
            frame[ordered_columns + smart_columns].to_csv(
                output_path,
                mode="a",
                index=False,
                header=not output_path.exists(),
            )
            rows_written += int(len(frame))

    anomaly_path = diagnostics_dir / "reliability_v1_5_event_anomalies.csv"
    pd.DataFrame(anomaly_rows).to_csv(anomaly_path, index=False)
    return {
        "rows_written": rows_written,
        "analysis_ready_path": output_path.as_posix(),
        "analysis_ready_size_bytes": output_path.stat().st_size,
        "event_anomaly_rows": len(anomaly_rows),
        "event_anomaly_path": anomaly_path.as_posix(),
        "processing_seconds_second_pass": round(time.perf_counter() - start, 3),
    }


def build_trajectory_summary(aggregates: dict[str, Any]) -> pd.DataFrame:
    """Build compact trajectory summary."""
    assets: dict[str, AssetStats] = aggregates["assets"]
    obs_counts = [stats.obs_count for stats in assets.values()]
    spans = [
        (stats.last_date - stats.first_date).days + 1
        for stats in assets.values()
        if stats.first_date and stats.last_date
    ]
    row = {
        "dataset_id": DATASET_ID,
        "total_assets": len(assets),
        "min_observations_per_asset": min(obs_counts) if obs_counts else 0,
        "median_observations_per_asset": float(pd.Series(obs_counts).median()) if obs_counts else 0.0,
        "max_observations_per_asset": max(obs_counts) if obs_counts else 0,
        "single_observation_asset_count": int(sum(count == 1 for count in obs_counts)),
        "multi_observation_asset_count": int(sum(count > 1 for count in obs_counts)),
        "duplicate_asset_date_count": aggregates["duplicate_asset_date_count"],
        "inconsistent_model_asset_count": len(aggregates["inconsistent_model_assets"]),
        "inconsistent_capacity_asset_count": len(aggregates["inconsistent_capacity_assets"]),
    }
    row.update(quantile_dict(obs_counts, "trajectory_observation_count"))
    row.update(quantile_dict(spans, "active_date_span_days"))
    return pd.DataFrame([row])


def build_event_integrity_summary(aggregates: dict[str, Any]) -> pd.DataFrame:
    """Build compact event integrity summary."""
    assets: dict[str, AssetStats] = aggregates["assets"]
    failed_assets = {
        serial: stats for serial, stats in assets.items() if stats.failure_dates
    }
    repeated = {
        serial: stats for serial, stats in failed_assets.items() if len(stats.failure_dates) > 1
    }
    post_failure = {
        serial: stats
        for serial, stats in failed_assets.items()
        if stats.last_date and min(stats.failure_dates) < stats.last_date
    }
    failure_on_last = {
        serial: stats
        for serial, stats in failed_assets.items()
        if stats.last_date and min(stats.failure_dates) == stats.last_date
    }
    missing_history = {
        serial: stats
        for serial, stats in failed_assets.items()
        if stats.first_date and min(stats.failure_dates) == stats.first_date
    }
    one_obs_failure = {
        serial: stats for serial, stats in failed_assets.items() if stats.obs_count == 1
    }
    return pd.DataFrame(
        [
            {
                "dataset_id": DATASET_ID,
                "failure_row_count": int(sum(len(stats.failure_dates) for stats in assets.values())),
                "unique_failed_asset_count": len(failed_assets),
                "multiple_failure_row_asset_count": len(repeated),
                "failure_followed_by_later_observation_asset_count": len(post_failure),
                "failure_before_final_observation_asset_count": len(post_failure),
                "failure_on_last_observation_asset_count": len(failure_on_last),
                "failure_asset_missing_previous_history_count": len(missing_history),
                "failure_asset_single_observation_count": len(one_obs_failure),
                "repeated_event_asset_count": len(repeated),
                "contradictory_event_sequence_count": len(post_failure),
                "terminal_event_policy": "first_failure_is_terminal_event_candidate",
                "post_event_policy": "retain_rows_flag_as_post_failure_not_prediction_features",
                "readiness_status": "conditionally_ready" if failed_assets else "not_ready",
            }
        ]
    )


def build_censoring_summary(aggregates: dict[str, Any]) -> pd.DataFrame:
    """Build asset censoring status summary."""
    assets: dict[str, AssetStats] = aggregates["assets"]
    archive_last = aggregates["archive_last_date"]
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"asset_count": 0, "observation_count": 0, "first": None, "last": None}
    )
    for stats in assets.values():
        first_failure = min(stats.failure_dates) if stats.failure_dates else None
        status = classify_censoring_status(
            obs_count=stats.obs_count,
            failure_count=len(stats.failure_dates),
            first_failure_date=str(first_failure) if first_failure else "",
            last_observation_date=str(stats.last_date),
            archive_last_date=str(archive_last),
            has_post_failure_observation=bool(first_failure and stats.last_date and stats.last_date > first_failure),
        )
        entry = grouped[status]
        entry["asset_count"] += 1
        entry["observation_count"] += stats.obs_count
        entry["first"] = stats.first_date if entry["first"] is None else min(entry["first"], stats.first_date)
        entry["last"] = stats.last_date if entry["last"] is None else max(entry["last"], stats.last_date)
    rows = []
    interpretations = {
        "observed_failure": "failure=1 observed and treated as explicit event candidate",
        "administrative_end_of_archive": "asset observed on archive final date without failure",
        "lost_to_observation": "asset exits before archive end without observed failure",
        "single_observation_unknown": "single row without enough follow-up context",
        "post_failure_inconsistent": "failure followed by later rows; retained as anomaly",
    }
    for status, entry in sorted(grouped.items()):
        rows.append(
            {
                "censoring_status": status,
                "asset_count": entry["asset_count"],
                "observation_count": entry["observation_count"],
                "date_range": f"{entry['first']} to {entry['last']}",
                "interpretation": interpretations.get(status, "requires_review"),
                "readiness_status": "conditionally_ready"
                if status in {"observed_failure", "administrative_end_of_archive", "lost_to_observation"}
                else "requires_review",
                "limitation": "Exit reason, retirement, and replacement are not directly observed.",
            }
        )
    return pd.DataFrame(rows)


def build_temporal_coverage_summary(aggregates: dict[str, Any]) -> pd.DataFrame:
    """Build daily coverage summary."""
    date_stats: dict[date, dict[str, Any]] = aggregates["date_stats"]
    first = aggregates["archive_first_date"]
    last = aggregates["archive_last_date"]
    all_dates = pd.date_range(first, last, freq="D").date
    rows = []
    for current in all_dates:
        stats = date_stats.get(
            current,
            {"rows": 0, "failure_rows": 0, "files": set(), "active_assets": set(), "new_assets": 0, "disappearing_assets": 0},
        )
        rows.append(
            {
                "date": str(current),
                "files_for_date": len(stats["files"]),
                "rows": int(stats["rows"]),
                "active_assets": len(stats["active_assets"]),
                "failure_rows": int(stats["failure_rows"]),
                "newly_appearing_assets": int(stats["new_assets"]),
                "disappearing_assets": int(stats["disappearing_assets"]),
                "coverage_status": "present" if stats["rows"] else "missing_calendar_date",
            }
        )
    return pd.DataFrame(rows)


def build_smart_feature_inventory(aggregates: dict[str, Any], total_rows: int, valid_member_count: int) -> pd.DataFrame:
    """Build compact SMART feature inventory."""
    rows = []
    for feature, stats in sorted(aggregates["feature_stats"].items()):
        metadata = smart_feature_metadata(feature)
        unique_count = len(stats.unique_values)
        all_missing = stats.non_missing_count == 0
        constant = unique_count <= 1 and not stats.unique_capped
        if all_missing:
            availability_status = "all_missing"
            candidate = False
            exclusion = "all_missing"
        elif stats.non_numeric_count:
            availability_status = "non_numeric_values_present"
            candidate = False
            exclusion = "non_numeric"
        elif constant:
            availability_status = "constant"
            candidate = False
            exclusion = "constant"
        else:
            availability_status = "available"
            candidate = True
            exclusion = ""
        rows.append(
            {
                "feature_name": feature,
                "smart_id": metadata["smart_id"],
                "feature_type": metadata["feature_type"],
                "member_coverage": stats.member_count / valid_member_count if valid_member_count else 0.0,
                "asset_coverage": f">={len(stats.assets)}" if stats.asset_coverage_capped else len(stats.assets),
                "non_missing_count": stats.non_missing_count,
                "missing_rate": stats.missing_count / total_rows if total_rows else 0.0,
                "unique_count": f">={unique_count}" if stats.unique_capped else unique_count,
                "constant_status": "constant" if constant else "variable_or_capped",
                "availability_status": availability_status,
                "prediction_feature_candidate": candidate,
                "exclusion_reason": exclusion,
                "negative_raw_value_count": stats.negative_count,
            }
        )
    return pd.DataFrame(rows)


def build_full_leakage_audit() -> pd.DataFrame:
    """Build a full-data leakage boundary table for known normalized fields."""
    rows = [
        ("days_to_last_observation", "full_lifetime_metadata", "target_construction_only", "Last observed date is future information at prediction time."),
        ("asset_last_observation_date", "archive_end_metadata", "target_construction_only", "Used for censoring/label feasibility only."),
        ("final_lifetime", "final_trajectory_statistic", "prohibited_feature", "No full-life statistic may be a prediction feature."),
        ("future_smart_values", "future_observation", "prohibited_feature", "Rolling features must use past windows only."),
        ("post_failure_rows", "post_event_measurement", "prohibited_feature", "Rows after first failure are retained only for diagnostics."),
        ("full_trajectory_normalization", "global_per_asset_normalization", "prohibited_feature", "Do not normalize using full asset history."),
        ("globally_fitted_smoothing", "global_filtering", "prohibited_feature", "Any smoothing must be train-only and past-only."),
        ("future_interpolation", "future_sample_interpolation", "prohibited_feature", "Past-only forward-fill is the safe default."),
        ("failure_date", "event_time", "target_construction_only", "Failure date is an outcome, not a feature."),
        ("censoring_date", "administrative_end", "target_construction_only", "Censoring date is evaluation metadata."),
        ("asset_maximum_observed_date", "asset_max_cycle_equivalent", "prohibited_feature", "Maximum observed date leaks follow-up length."),
        ("random_row_split", "same_asset_leakage", "prohibited_feature", "Random rows mix identical serial numbers across splits."),
        ("same_asset_train_test", "asset_identity_leakage", "prohibited_feature", "Asset-disjoint claims require serial_number exclusivity."),
        ("future_observations_in_rolling_windows", "future_window", "prohibited_feature", "Cutoffs must be closed-left/past-only."),
        ("model", "asset_family_proxy", "safe_feature", "Can be a static covariate but not a causal claim."),
        ("serial_number", "identity", "metadata_only", "Used for grouping, not as a prediction feature."),
        ("archive_end_knowledge", "administrative_end", "target_construction_only", "Allowed only to mark right-edge label feasibility."),
    ]
    return pd.DataFrame(
        [
            {
                "field_or_pattern": field,
                "leakage_type": leakage,
                "status": status,
                "mitigation": mitigation,
            }
            for field, leakage, status, mitigation in rows
        ]
    )


def build_horizon_feasibility(aggregates: dict[str, Any]) -> pd.DataFrame:
    """Assess future-failure label feasibility for fixed horizons."""
    assets: dict[str, AssetStats] = aggregates["assets"]
    archive_last = aggregates["archive_last_date"]
    rows = []
    for horizon in HORIZONS:
        positive = 0
        negative = 0
        right_edge = 0
        post_event_excluded = 0
        positive_assets: set[str] = set()
        negative_assets: set[str] = set()
        sufficient_lookback_assets: set[str] = set()
        for serial, stats in assets.items():
            if not stats.dates:
                continue
            first_failure = min(stats.failure_dates) if stats.failure_dates else None
            unique_dates = sorted(stats.dates)
            if len(set(unique_dates)) >= 2:
                sufficient_lookback_assets.add(serial)
            for origin in unique_dates:
                if first_failure and origin >= first_failure:
                    post_event_excluded += 1
                    continue
                horizon_end = origin + timedelta(days=horizon)
                if first_failure and origin < first_failure <= horizon_end:
                    positive += 1
                    positive_assets.add(serial)
                elif stats.last_date and stats.last_date >= horizon_end:
                    negative += 1
                    negative_assets.add(serial)
                else:
                    right_edge += 1
        eligible = positive + negative
        prevalence = positive / eligible if eligible else 0.0
        if positive >= 25 and negative >= 1000:
            status = "ready"
        elif positive >= 5 and negative >= 100:
            status = "conditionally_ready"
        else:
            status = "not_ready"
        rows.append(
            {
                "horizon_days": horizon,
                "eligible_prediction_rows": eligible,
                "positive_labels": positive,
                "negative_labels": negative,
                "unique_positive_assets": len(positive_assets),
                "unique_negative_assets": len(negative_assets),
                "assets_with_sufficient_lookback": len(sufficient_lookback_assets),
                "right_edge_censoring_affected_rows": right_edge,
                "post_event_excluded_rows": post_event_excluded,
                "prevalence": prevalence,
                "leakage_safe_constructibility": eligible > 0,
                "recommended_status": status,
            }
        )
    return pd.DataFrame(rows)


def build_lookback_feasibility(aggregates: dict[str, Any]) -> pd.DataFrame:
    """Assess lookback window feasibility without creating rolling features."""
    assets: dict[str, AssetStats] = aggregates["assets"]
    rows = []
    for lookback in LOOKBACKS:
        eligible_assets: set[str] = set()
        positive_origins = 0
        origin_count = 0
        obs_available: list[int] = []
        complete = 0
        irregular = 0
        for serial, stats in assets.items():
            if not stats.dates:
                continue
            first_failure = min(stats.failure_dates) if stats.failure_dates else None
            dates = sorted(stats.dates)
            unique_dates = sorted(set(dates))
            for origin in dates:
                if first_failure and origin >= first_failure:
                    continue
                if lookback == 0:
                    available = 1
                    is_complete = True
                else:
                    window_start = origin - timedelta(days=lookback - 1)
                    left = bisect_left(unique_dates, window_start)
                    right = bisect_right(unique_dates, origin)
                    available = right - left
                    is_complete = available >= lookback
                origin_count += 1
                obs_available.append(available)
                if is_complete:
                    complete += 1
                else:
                    irregular += 1
                eligible_assets.add(serial)
                if first_failure and origin < first_failure:
                    positive_origins += int((first_failure - origin).days <= 30)
        median_available = float(pd.Series(obs_available).median()) if obs_available else 0.0
        complete_prop = complete / origin_count if origin_count else 0.0
        irregular_prop = irregular / origin_count if origin_count else 0.0
        if origin_count and (lookback == 0 or complete_prop >= 0.5):
            status = "ready"
        elif origin_count:
            status = "conditionally_ready"
        else:
            status = "not_ready"
        rows.append(
            {
                "lookback_window_days": "current_day_only" if lookback == 0 else lookback,
                "eligible_assets": len(eligible_assets),
                "eligible_prediction_origins": origin_count,
                "positive_origins_within_30d": positive_origins,
                "median_observations_available": median_available,
                "complete_window_proportion": complete_prop,
                "irregular_gap_proportion": irregular_prop,
                "leakage_status": "past_or_current_observations_only",
                "feasibility_status": status,
            }
        )
    return pd.DataFrame(rows)


def build_split_feasibility(aggregates: dict[str, Any]) -> pd.DataFrame:
    """Build split feasibility table without creating model splits."""
    assets: dict[str, AssetStats] = aggregates["assets"]
    date_stats: dict[date, dict[str, Any]] = aggregates["date_stats"]
    first = aggregates["archive_first_date"]
    last = aggregates["archive_last_date"]
    total_rows = aggregates["total_rows"]
    failed_assets = {serial for serial, stats in assets.items() if stats.failure_dates}
    event_rows = sum(len(stats.failure_dates) for stats in assets.values())
    final_month_start = date(last.year, last.month, 1)
    train_rows = sum(stats["rows"] for day, stats in date_stats.items() if day < final_month_start)
    test_rows = sum(stats["rows"] for day, stats in date_stats.items() if day >= final_month_start)
    train_failures = sum(stats["failure_rows"] for day, stats in date_stats.items() if day < final_month_start)
    test_failures = sum(stats["failure_rows"] for day, stats in date_stats.items() if day >= final_month_start)
    rows = [
        {
            "split_id": "asset_disjoint_stratified_candidate",
            "split_type": "asset_disjoint",
            "train_rows": "estimated_80_percent_by_asset",
            "test_rows": "estimated_20_percent_by_asset",
            "train_assets": "asset_exclusive",
            "test_assets": "asset_exclusive",
            "train_failures": "requires_stratification",
            "test_failures": len(failed_assets),
            "positive_asset_count": len(failed_assets),
            "date_ranges": f"{first} to {last}",
            "asset_overlap": 0,
            "temporal_overlap": "allowed_for_unseen_asset_claim_only",
            "feasibility": "conditionally_ready" if len(failed_assets) >= 5 else "not_ready",
            "claim_scope": "unseen_asset_generalization",
        },
        {
            "split_id": "final_month_holdout",
            "split_type": "time_split",
            "train_rows": train_rows,
            "test_rows": test_rows,
            "train_assets": "known_and_new_assets_before_final_month",
            "test_assets": "assets_observed_in_final_month",
            "train_failures": train_failures,
            "test_failures": test_failures,
            "positive_asset_count": len(failed_assets),
            "date_ranges": f"train={first} to {final_month_start - timedelta(days=1)}; test={final_month_start} to {last}",
            "asset_overlap": "not_constrained",
            "temporal_overlap": 0,
            "feasibility": "conditionally_ready" if train_failures and test_failures else "not_ready",
            "claim_scope": "future_known_population_prediction",
        },
        {
            "split_id": "blocked_monthly_folds",
            "split_type": "time_split",
            "train_rows": total_rows,
            "test_rows": "monthly_blocks",
            "train_assets": "varies_by_fold",
            "test_assets": "assets_in_month",
            "train_failures": event_rows,
            "test_failures": "varies_by_month",
            "positive_asset_count": len(failed_assets),
            "date_ranges": f"{first} to {last}",
            "asset_overlap": "not_constrained",
            "temporal_overlap": 0,
            "feasibility": "conditionally_ready" if event_rows >= 5 else "not_ready",
            "claim_scope": "temporal_stability_diagnostic",
        },
        {
            "split_id": "combined_asset_disjoint_future_holdout",
            "split_type": "combined_asset_time_split",
            "train_rows": "requires_v1.5.4_split_materialization",
            "test_rows": "future_period_unseen_assets_only",
            "train_assets": "asset_exclusive",
            "test_assets": "asset_exclusive",
            "train_failures": "requires_v1.5.4_split_materialization",
            "test_failures": "requires_v1.5.4_split_materialization",
            "positive_asset_count": len(failed_assets),
            "date_ranges": f"{first} to {last}",
            "asset_overlap": 0,
            "temporal_overlap": 0,
            "feasibility": "conditionally_ready" if len(failed_assets) >= 5 and event_rows >= 5 else "not_ready",
            "claim_scope": "future_unseen_asset_generalization",
        },
        {
            "split_id": "random_row_split",
            "split_type": "random_row_split",
            "train_rows": "not_recommended",
            "test_rows": "not_recommended",
            "train_assets": "mixed",
            "test_assets": "mixed",
            "train_failures": "optimistic_only",
            "test_failures": "optimistic_only",
            "positive_asset_count": len(failed_assets),
            "date_ranges": f"{first} to {last}",
            "asset_overlap": "likely_nonzero",
            "temporal_overlap": "likely_nonzero",
            "feasibility": "prohibited_as_primary_evidence",
            "claim_scope": "optimistic_reference_only",
        },
    ]
    return pd.DataFrame(rows)


def build_task_readiness(
    horizon: pd.DataFrame,
    lookback: pd.DataFrame,
    split: pd.DataFrame,
    event_summary: pd.DataFrame,
) -> tuple[pd.DataFrame, str, str, str]:
    """Reassess task readiness from full-year evidence."""
    recommended_horizon = _recommend_horizon(horizon)
    recommended_lookback = _recommend_lookback(lookback)
    split_ready = split["feasibility"].astype(str).str.contains("ready|conditionally_ready", regex=True).any()
    event_count = int(event_summary.loc[0, "failure_row_count"])
    horizon_ready = recommended_horizon != "none"
    rows = [
        {
            "task": "binary_horizon_failure",
            "status": "conditionally_ready" if horizon_ready and split_ready else "not_ready",
            "basis": "Horizon labels can be constructed with first observed failure and past/current observations only.",
        },
        {
            "task": "terminal_event_prediction",
            "status": "conditionally_ready" if event_count >= 5 else "not_ready",
            "basis": "Terminal failure rows exist, but this is not yet a modeling task.",
        },
        {
            "task": "survival_time_to_event",
            "status": "conditionally_ready" if event_count >= 25 else "not_ready",
            "basis": "Events exist, but censoring is administrative/uncertain and requires survival-specific audit.",
        },
        {
            "task": "rul_regression",
            "status": "not_ready",
            "basis": "No RUL target is provided and non-event assets need explicit treatment.",
        },
        {
            "task": "recurrent_event_analysis",
            "status": "not_ready",
            "basis": "Failure is treated as terminal; repair/recurrent event semantics are absent.",
        },
        {
            "task": "degradation_trajectory",
            "status": "conditionally_ready",
            "basis": "SMART features provide longitudinal condition variables; rolling feature generation is deferred.",
        },
    ]
    task = pd.DataFrame(rows)
    selected = (
        "binary_horizon_failure"
        if task.loc[task["task"] == "binary_horizon_failure", "status"].iloc[0]
        == "conditionally_ready"
        else "none"
    )
    return task, selected, recommended_horizon, recommended_lookback


def build_full_readiness_summary(
    *,
    inventory: pd.DataFrame,
    trajectory: pd.DataFrame,
    event: pd.DataFrame,
    censoring: pd.DataFrame,
    temporal: pd.DataFrame,
    smart: pd.DataFrame,
    horizon: pd.DataFrame,
    lookback: pd.DataFrame,
    split: pd.DataFrame,
    selected_primary_task: str,
    recommended_horizon: str,
    recommended_lookback: str,
) -> pd.DataFrame:
    """Build the one-row full-year readiness conclusion."""
    valid_files = int(inventory["valid_daily_csv"].sum())
    total_rows = int(temporal["rows"].sum())
    asset_split = str(split.loc[split["split_id"] == "asset_disjoint_stratified_candidate", "feasibility"].iloc[0])
    time_split = str(split.loc[split["split_id"] == "final_month_holdout", "feasibility"].iloc[0])
    combined_split = str(split.loc[split["split_id"] == "combined_asset_disjoint_future_holdout", "feasibility"].iloc[0])
    usable_features = int(smart["prediction_feature_candidate"].astype(str).str.lower().isin(["true"]).sum())
    overall = "conditionally_ready" if selected_primary_task != "none" else "not_ready"
    return pd.DataFrame(
        [
            {
                "case_study_version": CASE_VERSION,
                "total_valid_daily_files": valid_files,
                "date_range": f"{temporal['date'].min()} to {temporal['date'].max()}",
                "total_rows": total_rows,
                "total_assets": int(trajectory.loc[0, "total_assets"]),
                "multi_observation_assets": int(trajectory.loc[0, "multi_observation_asset_count"]),
                "failure_rows": int(event.loc[0, "failure_row_count"]),
                "failed_assets": int(event.loc[0, "unique_failed_asset_count"]),
                "post_failure_anomalies": int(event.loc[0, "failure_followed_by_later_observation_asset_count"]),
                "censoring_categories": ",".join(censoring["censoring_status"].astype(str).tolist()),
                "smart_feature_count": len(smart),
                "usable_feature_count": usable_features,
                "recommended_horizon": recommended_horizon,
                "recommended_lookback": recommended_lookback,
                "asset_split_readiness": asset_split,
                "time_split_readiness": time_split,
                "combined_split_readiness": combined_split,
                "selected_primary_task": selected_primary_task,
                "overall_readiness": overall,
                "limitations": "Censoring is uncertain; no model training; full-lifetime metadata is prohibited as features.",
            }
        ]
    )


def build_normalization_spec(
    *,
    timestamp: str,
    archive_sha: str,
    analysis_ready_output: str,
) -> dict[str, Any]:
    """Build tracked normalization specification."""
    return {
        "schema_version": "1.0",
        "case_study_version": CASE_VERSION,
        "source_archive": "data/raw/reliability/backblaze_drive_stats/data_2013.zip",
        "archive_sha256": archive_sha,
        "member_inclusion_policy": "Include only YYYY-MM-DD.csv daily members outside macOS metadata folders.",
        "macos_metadata_exclusion": True,
        "filename_date_parsing": "basename must match YYYY-MM-DD.csv",
        "schema_harmonization_policy": "Track header signatures; use union columns with missing values if drift appears.",
        "required_identity_fields": ["date", "serial_number", "model", "capacity_bytes", "failure"],
        "failure_field_validation": "failure must be limited to {0, 1}",
        "smart_raw_normalized_policy": "Preserve SMART raw and normalized columns; audit availability without target-based selection.",
        "missing_column_policy": "Missing required columns stop processing; missing optional SMART columns are represented in schema drift outputs.",
        "duplicate_policy": "Duplicate asset/date rows are retained and counted.",
        "source_order_policy": "Preserve source_member, source_row_index, and global source_order_index.",
        "chronological_ordering_policy": "Daily members are processed by parsed date; per-asset ranks are derived chronologically.",
        "terminal_event_policy": "First failure row is a terminal event candidate.",
        "post_event_row_policy": "Post-failure rows are retained as diagnostics and prohibited as prediction features.",
        "censoring_interpretation": "Non-failed asset exits are administrative/right-censoring candidates with informative censoring risk.",
        "asset_observation_end_policy": "asset_last_observation_date is metadata/target-construction-only.",
        "local_analysis_ready_output": analysis_ready_output,
        "tracked_compact_outputs": [
            "data/processed/reliability_v1_5_full_archive_inventory.csv",
            "data/processed/reliability_v1_5_schema_drift_summary.csv",
            "data/processed/reliability_v1_5_trajectory_summary.csv",
            "data/processed/reliability_v1_5_event_integrity_summary.csv",
            "data/processed/reliability_v1_5_censoring_summary.csv",
            "data/processed/reliability_v1_5_temporal_coverage_summary.csv",
            "data/processed/reliability_v1_5_smart_feature_inventory.csv",
            "data/processed/reliability_v1_5_full_leakage_audit.csv",
            "data/processed/reliability_v1_5_horizon_feasibility.csv",
            "data/processed/reliability_v1_5_lookback_feasibility.csv",
            "data/processed/reliability_v1_5_split_feasibility.csv",
            "data/processed/reliability_v1_5_full_readiness_summary.csv",
            "data/processed/reliability_v1_5_full_task_readiness.csv",
        ],
        "leakage_policy": "Full-lifetime dates, days_to_last_observation, post-failure rows, future SMART values, and random row split are not prediction features.",
        "stop_conditions": [
            "archive SHA mismatch",
            "valid daily CSV identification fails",
            "serial_number missing",
            "failure values outside {0,1}",
            "source archive overwritten",
            "credential or absolute path leak",
        ],
        "memory_chunk_policy": "Process ZIP one daily member at a time; do not load the full archive into memory.",
        "created_at": timestamp,
    }


def build_full_year_manifest(
    *,
    timestamp: str,
    archive_sha_before: str,
    archive_sha_after: str,
    inventory: pd.DataFrame,
    schema: pd.DataFrame,
    readiness: pd.DataFrame,
    analysis_ready_info: dict[str, Any],
    processing_seconds: float,
) -> dict[str, Any]:
    """Build full-year tracked manifest."""
    return {
        "schema_version": "1.0",
        "case_study_version": CASE_VERSION,
        "processing_timestamp": timestamp,
        "source_archive_sha256_before": archive_sha_before,
        "source_archive_sha256_after": archive_sha_after,
        "source_unchanged": archive_sha_before == archive_sha_after,
        "valid_member_count": int(inventory["valid_daily_csv"].sum()),
        "excluded_member_count": int((~inventory["valid_daily_csv"].astype(bool)).sum()),
        "date_range": str(readiness.loc[0, "date_range"]),
        "total_rows": int(readiness.loc[0, "total_rows"]),
        "total_assets": int(readiness.loc[0, "total_assets"]),
        "event_count": int(readiness.loc[0, "failure_rows"]),
        "schema_signature_count": int(len(schema)),
        "analysis_ready_output_policy": "local_only_not_tracked",
        "analysis_ready_size_bytes": int(analysis_ready_info["analysis_ready_size_bytes"]),
        "normalization_status": "complete",
        "readiness_conclusion": readiness.to_dict(orient="records")[0],
        "processing_seconds": processing_seconds,
    }


def _recommend_horizon(horizon: pd.DataFrame) -> str:
    ready = horizon[horizon["recommended_status"].isin(["ready", "conditionally_ready"])].copy()
    if ready.empty:
        return "none"
    preferred = ready[ready["horizon_days"].eq(7)]
    if not preferred.empty:
        return "7_days"
    row = ready.sort_values(["positive_labels", "horizon_days"], ascending=[False, True]).iloc[0]
    return f"{int(row['horizon_days'])}_days"


def _recommend_lookback(lookback: pd.DataFrame) -> str:
    ready = lookback[lookback["feasibility_status"].isin(["ready", "conditionally_ready"])].copy()
    if ready.empty:
        return "none"
    preferred = ready[ready["lookback_window_days"].astype(str).eq("7")]
    if not preferred.empty:
        return "7_days"
    return str(ready.iloc[0]["lookback_window_days"])


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    """Write a CSV with parent directory creation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON with parent directory creation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    """Run full-year normalization and compact readiness audit."""
    args = parse_args()
    timestamp = utc_now_iso()
    archive_path = PROJECT_ROOT / args.archive
    if not archive_path.exists():
        raise FileNotFoundError(f"Backblaze archive not found: {args.archive}")
    archive_sha_before = calculate_sha256(archive_path)
    if archive_sha_before != EXPECTED_ARCHIVE_SHA:
        raise ValueError(
            "Archive SHA mismatch. Expected "
            f"{EXPECTED_ARCHIVE_SHA}, observed {archive_sha_before}"
        )
    start = time.perf_counter()

    zip_inventory = list_zip_members(archive_path)
    inventory = build_full_archive_inventory(zip_inventory)
    valid_members = select_valid_daily_members(inventory)
    if not valid_members:
        raise ValueError("No valid daily CSV members were identified.")
    schema_drift, schema_extra = build_schema_drift_summary(archive_path, inventory, valid_members)
    member_schema_status = schema_extra["member_schema_status"]
    inventory["schema_status"] = inventory["member_name"].map(member_schema_status).fillna("not_applicable")

    aggregates = first_pass_collect(archive_path, valid_members)
    analysis_ready_info = write_analysis_ready(
        archive_path,
        valid_members,
        aggregates,
        PROJECT_ROOT / args.analysis_ready_output,
        PROJECT_ROOT / args.local_diagnostics_dir,
    )
    trajectory = build_trajectory_summary(aggregates)
    event = build_event_integrity_summary(aggregates)
    censoring = build_censoring_summary(aggregates)
    temporal = build_temporal_coverage_summary(aggregates)
    smart = build_smart_feature_inventory(
        aggregates,
        total_rows=aggregates["total_rows"],
        valid_member_count=len(valid_members),
    )
    leakage = build_full_leakage_audit()
    horizon = build_horizon_feasibility(aggregates)
    lookback = build_lookback_feasibility(aggregates)
    split = build_split_feasibility(aggregates)
    task, selected_task, recommended_horizon, recommended_lookback = build_task_readiness(
        horizon, lookback, split, event
    )
    readiness = build_full_readiness_summary(
        inventory=inventory,
        trajectory=trajectory,
        event=event,
        censoring=censoring,
        temporal=temporal,
        smart=smart,
        horizon=horizon,
        lookback=lookback,
        split=split,
        selected_primary_task=selected_task,
        recommended_horizon=recommended_horizon,
        recommended_lookback=recommended_lookback,
    )
    archive_sha_after = calculate_sha256(archive_path)
    processing_seconds = round(time.perf_counter() - start, 3)
    spec = build_normalization_spec(
        timestamp=timestamp,
        archive_sha=archive_sha_after,
        analysis_ready_output=args.analysis_ready_output,
    )
    manifest = build_full_year_manifest(
        timestamp=timestamp,
        archive_sha_before=archive_sha_before,
        archive_sha_after=archive_sha_after,
        inventory=inventory,
        schema=schema_drift,
        readiness=readiness,
        analysis_ready_info=analysis_ready_info,
        processing_seconds=processing_seconds,
    )

    output_map = {
        args.archive_inventory_output: inventory,
        args.schema_drift_output: schema_drift,
        args.trajectory_output: trajectory,
        args.event_output: event,
        args.censoring_output: censoring,
        args.temporal_output: temporal,
        args.smart_output: smart,
        args.leakage_output: leakage,
        args.horizon_output: horizon,
        args.lookback_output: lookback,
        args.split_output: split,
        args.full_readiness_output: readiness,
        args.task_output: task,
    }
    for relative, frame in output_map.items():
        write_csv(PROJECT_ROOT / relative, frame)
    write_json(PROJECT_ROOT / args.normalization_spec, spec)
    write_json(PROJECT_ROOT / args.full_year_manifest, manifest)

    print("Valid daily CSV files:", int(inventory["valid_daily_csv"].sum()))
    print("Excluded members:", int((~inventory["valid_daily_csv"].astype(bool)).sum()))
    print("Date range:", readiness.loc[0, "date_range"])
    print("Total rows:", int(readiness.loc[0, "total_rows"]))
    print("Total assets:", int(readiness.loc[0, "total_assets"]))
    print("Failure rows:", int(readiness.loc[0, "failure_rows"]))
    print("Failed assets:", int(readiness.loc[0, "failed_assets"]))
    print("Recommended horizon:", recommended_horizon)
    print("Recommended lookback:", recommended_lookback)
    print("Selected primary task:", selected_task)
    print("Overall readiness:", readiness.loc[0, "overall_readiness"])
    print("Analysis-ready local output:", args.analysis_ready_output)
    print("Analysis-ready size bytes:", analysis_ready_info["analysis_ready_size_bytes"])
    print("Source SHA unchanged:", archive_sha_before == archive_sha_after)
    print("Processing seconds:", processing_seconds)


if __name__ == "__main__":
    main()
