"""Generic reliability schema reconnaissance helpers.

These helpers translate bounded tabular reliability samples into compact
schema, leakage, and readiness inputs. They do not download data, fit models,
or encode a single dataset's full analysis workflow.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from analyzers.reliability_readiness import ReliabilityReadinessConfig


LEAKAGE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("rul", "remaining_useful_life_label"),
    ("remaining_useful_life", "remaining_useful_life_label"),
    ("final_cycle", "final_cycle_count"),
    ("final_life", "final_cycle_count"),
    ("max_cycle", "asset_maximum_cycle"),
    ("future", "future_degradation_windows"),
    ("post_failure", "post_failure_measurements"),
    ("after_failure", "post_failure_measurements"),
    ("replacement", "replacement_indicator"),
    ("teardown", "failure_code_after_teardown"),
    ("full_lifetime", "full_lifetime_normalization"),
)

DAILY_CSV_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\.csv$", re.IGNORECASE)


def infer_reliability_column_metadata(column: str) -> dict[str, object]:
    """Infer a conservative reliability role from a source column name."""
    lower = column.casefold()
    leakage_match = _matching_leakage_pattern(lower)

    if column == "source_member":
        role = "source_metadata"
        requirement = "optional"
        availability = "source_record"
        feature_or_metadata = "metadata"
        leakage_status = "metadata_only"
    elif lower in {"serial_number", "asset_id", "unit_number", "unit_id", "engine_id"}:
        role = "asset_id"
        requirement = "required"
        availability = "observation_time"
        feature_or_metadata = "metadata"
        leakage_status = "metadata_only"
    elif lower in {"date", "timestamp", "observation_timestamp"}:
        role = "observation_timestamp"
        requirement = "required"
        availability = "observation_time"
        feature_or_metadata = "metadata"
        leakage_status = "metadata_only"
    elif lower in {"cycle", "cycle_index", "observation_cycle"}:
        role = "observation_cycle"
        requirement = "preferred"
        availability = "observation_time"
        feature_or_metadata = "metadata"
        leakage_status = "metadata_only"
    elif lower in {"failure", "event_indicator", "target_failure"}:
        role = "event_indicator"
        requirement = "required"
        availability = "outcome_time"
        feature_or_metadata = "target"
        leakage_status = "outcome_not_feature"
    elif lower in {"model", "model_family"}:
        role = "asset_model"
        requirement = "preferred"
        availability = "observation_time"
        feature_or_metadata = "metadata_or_feature"
        leakage_status = "safe_feature"
    elif lower in {"capacity_bytes", "capacity"}:
        role = "static_covariate"
        requirement = "preferred"
        availability = "observation_time"
        feature_or_metadata = "candidate_feature"
        leakage_status = "safe_feature"
    elif lower.startswith("smart_"):
        role = "degradation_feature"
        requirement = "preferred"
        availability = "observation_time"
        feature_or_metadata = "candidate_feature"
        leakage_status = "safe_feature"
    elif leakage_match:
        role = "potential_leakage_field"
        requirement = "unavailable"
        availability = "after_prediction_origin_or_end_of_life"
        feature_or_metadata = "metadata_only"
        leakage_status = "prohibited_feature"
    else:
        role = "unclassified_column"
        requirement = "optional"
        availability = "unknown"
        feature_or_metadata = "metadata_or_candidate_feature"
        leakage_status = "requires_review"

    return {
        "normalized_role": role,
        "requirement_level": requirement,
        "availability_time": availability,
        "feature_or_metadata": feature_or_metadata,
        "leakage_status": leakage_status,
        "notes": f"matched leakage pattern: {leakage_match}" if leakage_match else "",
    }


def build_schema_inventory(
    df: pd.DataFrame,
    *,
    dataset_id: str,
    file_id: str = "bounded_sample",
) -> pd.DataFrame:
    """Build a compact schema inventory for a bounded reliability sample."""
    rows: list[dict[str, object]] = []
    row_count = len(df)
    for column in df.columns:
        metadata = infer_reliability_column_metadata(column)
        missing_count = int(df[column].isna().sum())
        rows.append(
            {
                "dataset_id": dataset_id,
                "file_id": file_id,
                "source_column": column,
                "normalized_role": metadata["normalized_role"],
                "dtype": str(df[column].dtype),
                "requirement_level": metadata["requirement_level"],
                "observed_status": "present",
                "non_missing_count": int(df[column].notna().sum()),
                "missing_count": missing_count,
                "missing_rate": float(missing_count / row_count) if row_count else 0.0,
                "unique_count": int(df[column].nunique(dropna=True)),
                "availability_time": metadata["availability_time"],
                "feature_or_metadata": metadata["feature_or_metadata"],
                "leakage_status": metadata["leakage_status"],
                "readiness_status": _readiness_status(metadata),
                "notes": metadata["notes"],
            }
        )
    return pd.DataFrame(rows)


def build_leakage_schema_audit(
    columns: list[str] | pd.Index,
    leakage_map: pd.DataFrame,
    *,
    dataset_id: str,
) -> pd.DataFrame:
    """Compare actual columns with the generic leakage map."""
    rows: list[dict[str, object]] = []
    lowered = {column: str(column).casefold() for column in columns}
    for _, rule in leakage_map.iterrows():
        pattern = str(rule["field_or_pattern"])
        token = _pattern_token(pattern)
        matches = [
            column
            for column, lower in lowered.items()
            if token in lower or _rule_matches_pattern(pattern, lower)
        ]
        if matches:
            status = (
                "prohibited_feature"
                if str(rule["allowed_as_feature"]).casefold() == "false"
                else "requires_time_cutoff"
            )
            observed = "observed"
        else:
            status = "not_observed"
            observed = "not_observed"
        rows.append(
            {
                "dataset_id": dataset_id,
                "field_or_pattern": pattern,
                "leakage_type": rule["leakage_type"],
                "risk_level": rule["risk_level"],
                "observed_status": observed,
                "matched_columns": ",".join(matches),
                "match_count": len(matches),
                "schema_leakage_status": status,
                "allowed_as_feature": bool(str(rule["allowed_as_feature"]).casefold() == "true"),
                "allowed_as_metadata": bool(str(rule["allowed_as_metadata"]).casefold() == "true"),
                "mitigation": rule["mitigation"],
            }
        )
    return pd.DataFrame(rows)


def build_backblaze_readiness_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Map a Backblaze-style bounded sample into generic readiness columns."""
    required = {"serial_number", "date", "failure"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Backblaze readiness frame requires columns: {', '.join(missing)}")

    working = df.copy()
    working["asset_id"] = working["serial_number"].astype(str)
    working["observation_timestamp"] = pd.to_datetime(working["date"], errors="coerce")
    working["prediction_origin"] = working["observation_timestamp"]
    working["event_indicator"] = pd.to_numeric(working["failure"], errors="coerce")
    invalid_events = working["event_indicator"].notna() & ~working["event_indicator"].isin([0, 1])
    if invalid_events.any():
        examples = sorted(working.loc[invalid_events, "failure"].dropna().astype(str).unique().tolist())
        raise ValueError(f"Backblaze failure values must be limited to {{0, 1}}; found {examples}")

    working = working.sort_values(["asset_id", "observation_timestamp"], kind="mergesort")
    working["observation_cycle"] = working.groupby("asset_id").cumcount() + 1
    working["event_timestamp"] = pd.NaT
    event_rows = working["event_indicator"].eq(1)
    working.loc[event_rows, "event_timestamp"] = working.loc[event_rows, "observation_timestamp"]

    last_seen = working.groupby("asset_id")["observation_timestamp"].transform("max")
    working["censoring_timestamp"] = pd.NaT
    working.loc[working["event_indicator"].eq(0), "censoring_timestamp"] = last_seen

    columns = [
        "asset_id",
        "observation_timestamp",
        "observation_cycle",
        "prediction_origin",
        "event_indicator",
        "event_timestamp",
        "censoring_timestamp",
    ]
    for optional in ["model", "capacity_bytes", "source_member"]:
        if optional in working.columns:
            columns.append(optional)
    columns.extend(select_degradation_feature_columns(working))
    return working[columns].reset_index(drop=True)


def build_reliability_config_from_frame(
    df: pd.DataFrame,
    *,
    min_assets_for_asset_split: int = 5,
    min_events_for_event_model: int = 5,
    min_rows_for_temporal_split: int = 20,
) -> ReliabilityReadinessConfig:
    """Create a generic readiness config for a normalized reliability frame."""
    return ReliabilityReadinessConfig(
        required_columns=[
            "asset_id",
            "observation_timestamp",
            "prediction_origin",
            "event_indicator",
        ],
        asset_id_column="asset_id",
        observation_timestamp_column="observation_timestamp",
        observation_cycle_column="observation_cycle" if "observation_cycle" in df.columns else None,
        prediction_origin_column="prediction_origin",
        event_indicator_column="event_indicator",
        event_timestamp_column="event_timestamp" if "event_timestamp" in df.columns else None,
        censoring_timestamp_column=(
            "censoring_timestamp" if "censoring_timestamp" in df.columns else None
        ),
        degradation_feature_columns=select_degradation_feature_columns(df),
        min_assets_for_asset_split=min_assets_for_asset_split,
        min_events_for_event_model=min_events_for_event_model,
        min_rows_for_temporal_split=min_rows_for_temporal_split,
    )


def select_degradation_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return numeric SMART-style degradation columns."""
    candidates = [
        column
        for column in df.columns
        if str(column).casefold().startswith("smart_")
        and pd.api.types.is_numeric_dtype(df[column])
    ]
    return sorted(candidates)


def classify_archive_member(member_path: str, file_name: str, uncompressed_size: int) -> dict[str, object]:
    """Classify a source archive member for reliability raw inventory."""
    parsed_date = parse_daily_member_date(file_name)
    member_lower = member_path.casefold()
    is_macos = "__macosx" in member_lower or file_name.startswith("._")
    is_hidden = file_name.startswith(".")
    is_empty = int(uncompressed_size) == 0
    if is_macos:
        member_type = "macos_metadata"
        inclusion_status = "excluded"
        exclusion_reason = "macos_metadata"
    elif is_hidden:
        member_type = "hidden_file"
        inclusion_status = "excluded"
        exclusion_reason = "hidden_file"
    elif is_empty:
        member_type = "empty_member"
        inclusion_status = "excluded"
        exclusion_reason = "empty_member"
    elif parsed_date:
        member_type = "valid_daily_csv"
        inclusion_status = "included"
        exclusion_reason = ""
    elif file_name.casefold().endswith(".csv"):
        member_type = "malformed_filename"
        inclusion_status = "excluded"
        exclusion_reason = "csv_filename_does_not_match_yyyy_mm_dd"
    else:
        member_type = "unsupported_member"
        inclusion_status = "excluded"
        exclusion_reason = "unsupported_member_type"
    return {
        "member_type": member_type,
        "parsed_date": parsed_date,
        "valid_daily_csv": bool(member_type == "valid_daily_csv"),
        "inclusion_status": inclusion_status,
        "exclusion_reason": exclusion_reason,
    }


def parse_daily_member_date(file_name: str) -> str:
    """Parse ``YYYY-MM-DD.csv`` file names and return an ISO date string."""
    match = DAILY_CSV_RE.match(Path(file_name).name)
    return match.group("date") if match else ""


def build_full_archive_inventory(zip_inventory: pd.DataFrame) -> pd.DataFrame:
    """Build a classified full archive inventory from ZIP member metadata."""
    rows: list[dict[str, object]] = []
    for _, row in zip_inventory.iterrows():
        classified = classify_archive_member(
            str(row["member_path"]),
            str(row["file_name"]),
            int(row["uncompressed_size_bytes"]),
        )
        rows.append(
            {
                "member_name": row["member_path"],
                "member_type": classified["member_type"],
                "parsed_date": classified["parsed_date"],
                "compressed_size": int(row["compressed_size_bytes"]),
                "uncompressed_size": int(row["uncompressed_size_bytes"]),
                "valid_daily_csv": classified["valid_daily_csv"],
                "inclusion_status": classified["inclusion_status"],
                "exclusion_reason": classified["exclusion_reason"],
                "duplicate_date_status": "not_evaluated",
                "schema_status": "not_checked",
                "notes": "",
            }
        )
    inventory = pd.DataFrame(rows)
    if inventory.empty:
        return inventory
    valid = inventory["valid_daily_csv"].astype(bool)
    duplicate_dates = inventory.loc[valid, "parsed_date"].duplicated(keep=False)
    inventory.loc[valid, "duplicate_date_status"] = "unique_date"
    inventory.loc[inventory.loc[valid].index[duplicate_dates], "duplicate_date_status"] = "duplicate_date"
    inventory.loc[~valid, "duplicate_date_status"] = "not_applicable"
    return inventory.sort_values(["member_name"]).reset_index(drop=True)


def select_valid_daily_members(full_inventory: pd.DataFrame) -> list[str]:
    """Return included daily CSV member names in chronological order."""
    if full_inventory.empty:
        return []
    valid = full_inventory[
        full_inventory["valid_daily_csv"].astype(bool)
        & full_inventory["duplicate_date_status"].isin(["unique_date"])
    ].copy()
    valid = valid.sort_values(["parsed_date", "member_name"])
    return valid["member_name"].astype(str).tolist()


def normalize_backblaze_daily_frame(
    frame: pd.DataFrame,
    *,
    source_member: str,
    source_order_start: int,
) -> pd.DataFrame:
    """Normalize one Backblaze daily CSV frame without using future data."""
    required = {"date", "serial_number", "model", "capacity_bytes", "failure"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Backblaze daily frame missing required columns: {', '.join(missing)}")
    normalized = frame.copy()
    row_count = len(normalized)
    normalized.insert(0, "source_member", source_member)
    normalized.insert(1, "source_row_index", range(row_count))
    normalized["observation_date"] = pd.to_datetime(normalized["date"], errors="coerce").dt.date.astype(str)
    normalized["serial_number"] = normalized["serial_number"].astype(str)
    normalized["failure"] = pd.to_numeric(normalized["failure"], errors="coerce")
    invalid_failure = normalized["failure"].notna() & ~normalized["failure"].isin([0, 1])
    if invalid_failure.any():
        examples = sorted(normalized.loc[invalid_failure, "failure"].dropna().astype(str).unique().tolist())
        raise ValueError(f"Backblaze failure values must be limited to {{0, 1}}; found {examples}")
    normalized["event_indicator"] = normalized["failure"].fillna(0).astype(int)
    normalized["source_order_index"] = range(source_order_start, source_order_start + row_count)
    preferred = [
        "source_member",
        "source_row_index",
        "observation_date",
        "serial_number",
        "model",
        "capacity_bytes",
        "failure",
        "event_indicator",
        "source_order_index",
    ]
    smart_columns = sorted(column for column in normalized.columns if str(column).casefold().startswith("smart_"))
    return normalized[preferred + smart_columns]


def smart_feature_metadata(feature_name: str) -> dict[str, str]:
    """Return SMART id and raw/normalized type from a SMART column name."""
    match = re.match(r"^smart_(?P<id>\d+)_(?P<kind>normalized|raw)$", feature_name, re.IGNORECASE)
    if not match:
        return {"smart_id": "", "feature_type": "unknown"}
    return {"smart_id": match.group("id"), "feature_type": match.group("kind").lower()}


def classify_censoring_status(
    *,
    obs_count: int,
    failure_count: int,
    first_failure_date: str,
    last_observation_date: str,
    archive_last_date: str,
    has_post_failure_observation: bool,
) -> str:
    """Classify asset-level censoring or event status conservatively."""
    if failure_count and has_post_failure_observation:
        return "post_failure_inconsistent"
    if failure_count:
        return "observed_failure"
    if obs_count <= 1:
        return "single_observation_unknown"
    if last_observation_date == archive_last_date:
        return "administrative_end_of_archive"
    if first_failure_date:
        return "observed_failure"
    return "lost_to_observation"


def classify_post_failure_status(
    observation_date: str,
    failure: int,
    first_failure_date: str,
) -> str:
    """Classify a row relative to the asset's first observed failure."""
    if not first_failure_date:
        return "no_observed_failure"
    if observation_date < first_failure_date:
        return "pre_failure_observation"
    if observation_date == first_failure_date and int(failure) == 1:
        return "failure_observation"
    if observation_date == first_failure_date:
        return "same_day_failure_context"
    return "post_failure_observation"


def status_from_bool(condition: bool, ready: str = "ready", not_ready: str = "not_ready") -> str:
    """Convert booleans to machine-readable readiness status labels."""
    return ready if condition else not_ready


def quantile_dict(values: Iterable[int | float], prefix: str) -> dict[str, float]:
    """Return compact quantiles for numeric values."""
    series = pd.Series(list(values), dtype="float64")
    if series.empty:
        return {
            f"{prefix}_p05": 0.0,
            f"{prefix}_p25": 0.0,
            f"{prefix}_p50": 0.0,
            f"{prefix}_p75": 0.0,
            f"{prefix}_p95": 0.0,
        }
    return {
        f"{prefix}_p05": float(series.quantile(0.05)),
        f"{prefix}_p25": float(series.quantile(0.25)),
        f"{prefix}_p50": float(series.quantile(0.50)),
        f"{prefix}_p75": float(series.quantile(0.75)),
        f"{prefix}_p95": float(series.quantile(0.95)),
    }


def summarize_backblaze_assets(readiness_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize asset-level support for a Backblaze-style sample."""
    if readiness_df.empty:
        return pd.DataFrame(
            [
                {
                    "dataset_id": "backblaze_drive_stats",
                    "asset_count": 0,
                    "min_observations_per_asset": 0,
                    "median_observations_per_asset": 0.0,
                    "max_observations_per_asset": 0,
                    "terminal_event_asset_count": 0,
                    "censored_asset_count": 0,
                    "status": "empty_sample",
                }
            ]
        )
    grouped = readiness_df.groupby("asset_id", dropna=True)
    lengths = grouped.size()
    events = grouped["event_indicator"].sum(min_count=1)
    return pd.DataFrame(
        [
            {
                "dataset_id": "backblaze_drive_stats",
                "asset_count": int(lengths.size),
                "min_observations_per_asset": int(lengths.min()),
                "median_observations_per_asset": float(lengths.median()),
                "max_observations_per_asset": int(lengths.max()),
                "terminal_event_asset_count": int(events.fillna(0).gt(0).sum()),
                "censored_asset_count": int(events.fillna(0).eq(0).sum()),
                "status": "asset_longitudinal_ready"
                if lengths.ge(2).any()
                else "limited_repeated_observations",
            }
        ]
    )


def summarize_event_censoring_structure(readiness_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize observed event and inferred administrative censoring support."""
    event = pd.to_numeric(readiness_df.get("event_indicator", pd.Series(dtype=float)), errors="coerce")
    return pd.DataFrame(
        [
            {
                "dataset_id": "backblaze_drive_stats",
                "event_interpretation": "observed_terminal_drive_failure_flag",
                "censoring_interpretation": "administrative_last_observation_in_bounded_sample",
                "row_count": int(len(readiness_df)),
                "event_row_count": int(event.eq(1).sum()),
                "non_event_row_count": int(event.eq(0).sum()),
                "event_asset_count": int(
                    readiness_df.loc[event.eq(1), "asset_id"].nunique()
                    if "asset_id" in readiness_df.columns
                    else 0
                ),
                "censored_asset_count": int(
                    readiness_df.groupby("asset_id")["event_indicator"]
                    .sum(min_count=1)
                    .fillna(0)
                    .eq(0)
                    .sum()
                    if "asset_id" in readiness_df.columns
                    else 0
                ),
                "survival_claim_status": "not_ready_until_full_followup_and_censoring_audit",
                "status": "conditionally_ready" if event.eq(1).any() else "not_ready",
            }
        ]
    )


def _matching_leakage_pattern(lower_column: str) -> str:
    for token, pattern in LEAKAGE_PATTERNS:
        if token in lower_column:
            return pattern
    return ""


def _readiness_status(metadata: dict[str, object]) -> str:
    if metadata["leakage_status"] == "prohibited_feature":
        return "metadata_only_or_exclude"
    if metadata["normalized_role"] in {"asset_id", "observation_timestamp", "event_indicator"}:
        return "required_available"
    if metadata["normalized_role"] == "degradation_feature":
        return "candidate_feature_available"
    return "requires_review"


def _pattern_token(pattern: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", pattern.casefold()).strip("_")


def _rule_matches_pattern(pattern: str, lower_column: str) -> bool:
    token = _pattern_token(pattern)
    pieces = [piece for piece in token.split("_") if len(piece) >= 3]
    return bool(pieces and all(piece in lower_column for piece in pieces[:2]))


def is_relative_safe_path(value: str) -> bool:
    """Return True when a path-like value does not look local or absolute."""
    path = Path(value)
    return not path.is_absolute() and not re.search(r"^[A-Za-z]:\\", value)
