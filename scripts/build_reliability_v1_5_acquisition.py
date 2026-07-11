"""Run Reliability v1.5.2 dataset access gate and readiness audit.

The script uses the v1.5.1 candidate table as the source of truth, performs a
bounded Backblaze access gate when explicitly allowed, and writes compact
tracked provenance/readiness artifacts. It does not train models, fit survival
curves, or create row-level normalized trajectory tables.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analyzers.reliability_readiness import build_reliability_readiness_report  # noqa: E402
from connectors.reliability import (  # noqa: E402
    calculate_sha256,
    discover_local_files,
    download_file,
    get_remote_file_metadata,
    list_zip_members,
    read_bounded_csv_sample_from_zip,
)
from loaders.reliability import (  # noqa: E402
    build_backblaze_readiness_frame,
    build_leakage_schema_audit,
    build_reliability_config_from_frame,
    build_schema_inventory,
    summarize_backblaze_assets,
    summarize_event_censoring_structure,
)


BACKBLAZE_2013_URL = (
    "https://f001.backblazeb2.com/file/Backblaze-Hard-Drive-Data/data_2013.zip"
)
BACKBLAZE_SOURCE_URL = "https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data"
CASE_VERSION = "v1.5.2"
DATASET_ID = "backblaze_drive_stats"
BACKUP_DATASET_ID = "nasa_cmapss"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Build Reliability v1.5.2 acquisition/readiness artifacts."
    )
    parser.add_argument(
        "--candidate-csv",
        default="data/case_studies/reliability/dataset_candidates_v1_5.csv",
    )
    parser.add_argument(
        "--leakage-map",
        default="data/case_studies/reliability/leakage_map_v1_5.csv",
    )
    parser.add_argument(
        "--raw-dir",
        default="data/raw/reliability",
        help="Local-only reliability raw-data root.",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow official-source metadata/download calls.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download the bounded Backblaze 2013 archive if missing.",
    )
    parser.add_argument(
        "--max-download-mb",
        type=int,
        default=120,
        help="Hard byte budget for the bounded archive download.",
    )
    parser.add_argument(
        "--max-members",
        type=int,
        default=5,
        help="Number of daily CSV members to read for bounded readiness.",
    )
    parser.add_argument(
        "--max-rows-per-member",
        type=int,
        default=0,
        help="Rows per selected member; 0 reads full selected members.",
    )
    parser.add_argument(
        "--acquisition-spec",
        default="data/case_studies/reliability/acquisition_spec_v1_5.json",
    )
    parser.add_argument(
        "--manifest-output",
        default="data/case_studies/reliability/acquisition_manifest_v1_5.json",
    )
    parser.add_argument(
        "--schema-output",
        default="data/processed/reliability_v1_5_schema_inventory.csv",
    )
    parser.add_argument(
        "--leakage-output",
        default="data/processed/reliability_v1_5_leakage_schema_audit.csv",
    )
    parser.add_argument(
        "--readiness-output",
        default="data/processed/reliability_v1_5_readiness_summary.csv",
    )
    parser.add_argument(
        "--task-output",
        default="data/processed/reliability_v1_5_task_feasibility.csv",
    )
    parser.add_argument(
        "--asset-output",
        default="data/processed/reliability_v1_5_asset_summary.csv",
    )
    parser.add_argument(
        "--event-output",
        default="data/processed/reliability_v1_5_event_censoring_summary.csv",
    )
    parser.add_argument(
        "--validation-output",
        default="data/processed/reliability_v1_5_validation_feasibility.csv",
    )
    parser.add_argument(
        "--conclusion-output",
        default="data/processed/reliability_v1_5_acquisition_conclusion.csv",
    )
    return parser.parse_args()


def utc_now_iso() -> str:
    """Return a compact UTC timestamp string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_candidate_decisions(candidate_csv: str | Path) -> pd.DataFrame:
    """Load and validate v1.5 candidate decisions."""
    path = Path(candidate_csv)
    if not path.exists():
        raise FileNotFoundError(f"Reliability candidate decision CSV not found: {path}")
    candidates = pd.read_csv(path)
    required = {"dataset_id", "dataset_name", "status", "source_url"}
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise ValueError(f"Candidate decision CSV missing columns: {', '.join(missing)}")
    return candidates


def select_primary_and_backup(candidates: pd.DataFrame) -> tuple[dict[str, object], dict[str, object]]:
    """Select one primary and one backup from the candidate table."""
    primary = candidates[candidates["status"] == "conditional_primary_candidate"]
    backup = candidates[candidates["status"] == "operational_backup_candidate"]
    if len(primary) != 1:
        raise ValueError(
            "Expected exactly one conditional_primary_candidate in dataset_candidates_v1_5.csv"
        )
    if len(backup) != 1:
        raise ValueError(
            "Expected exactly one operational_backup_candidate in dataset_candidates_v1_5.csv"
        )
    return primary.iloc[0].to_dict(), backup.iloc[0].to_dict()


def build_acquisition_spec(
    *,
    timestamp: str,
    primary_candidate: dict[str, object],
    backup_candidate: dict[str, object],
    access_status: str,
    terms_status: str,
    license_status: str,
    redistribution_status: str,
    active_candidate: str,
    fallback_activated: bool,
) -> dict[str, object]:
    """Build the tracked v1.5.2 acquisition specification."""
    return {
        "schema_version": "1.0",
        "case_study_version": CASE_VERSION,
        "status": "access_gate_complete",
        "primary_candidate": primary_candidate["dataset_id"],
        "backup_candidate": backup_candidate["dataset_id"],
        "active_candidate": active_candidate,
        "source_type": "public_reliability_asset_history",
        "official_source": BACKBLAZE_SOURCE_URL,
        "source_url": BACKBLAZE_2013_URL,
        "access_method": "official_backblaze_2013_zip_bounded_sample",
        "authentication_requirement": "none_observed_for_2013_public_zip",
        "access_status": access_status,
        "terms_status": terms_status,
        "license_status": license_status,
        "redistribution_status": redistribution_status,
        "retrieval_timestamp": timestamp,
        "expected_files": ["data_2013.zip"],
        "observed_files": ["data_2013.zip"] if active_candidate == DATASET_ID else [],
        "expected_size": "about 81 MB for data_2013.zip",
        "observed_file_sizes": "recorded_in_acquisition_manifest_v1_5_json",
        "archive_policy": "Raw archive stays under data/raw/reliability and is not tracked.",
        "checksum_policy": "Compute SHA256 before and after script execution without overwriting existing raw source.",
        "extraction_policy": "Do not extract full archive; list members and read bounded selected CSV members.",
        "raw_local_paths": [
            "data/raw/reliability/backblaze_drive_stats/data_2013.zip",
        ],
        "tracked_manifest_paths": [
            "data/case_studies/reliability/acquisition_manifest_v1_5.json",
            "data/processed/reliability_v1_5_schema_inventory.csv",
            "data/processed/reliability_v1_5_leakage_schema_audit.csv",
            "data/processed/reliability_v1_5_readiness_summary.csv",
            "data/processed/reliability_v1_5_task_feasibility.csv",
            "data/processed/reliability_v1_5_asset_summary.csv",
            "data/processed/reliability_v1_5_event_censoring_summary.csv",
            "data/processed/reliability_v1_5_validation_feasibility.csv",
            "data/processed/reliability_v1_5_acquisition_conclusion.csv",
        ],
        "fallback_policy": {
            "fallback_activated": fallback_activated,
            "fallback_candidate": backup_candidate["dataset_id"],
            "fallback_rule": "Activate backup when access, terms, license, file inventory, or readiness gate fails.",
        },
        "credential_policy": {
            "credential_values_logged": False,
            "repository_credentials_allowed": False,
            "environment_variable_values_allowed": False,
        },
        "allowed_network_operations": [
            "HEAD official Backblaze 2013 ZIP when --allow-network is set",
            "GET official Backblaze 2013 ZIP when --allow-network --download is set",
        ],
        "prohibited_operations": [
            "model_training",
            "survival_modeling",
            "RUL_regression",
            "Weibull_fitting",
            "full_archive_extraction",
            "raw_data_commit",
            "credential_logging",
        ],
        "stop_conditions": [
            "candidate_decision_inconsistent",
            "official_source_unavailable",
            "terms_unresolved",
            "license_unresolved",
            "download_exceeds_budget",
            "archive_malformed",
            "no_asset_id",
            "no_repeated_measurements",
            "no_usable_event",
            "no_timestamp_or_cycle",
            "raw_source_overwritten",
            "credential_or_absolute_path_leak",
        ],
    }


def build_manifest(
    *,
    timestamp: str,
    primary_candidate: dict[str, object],
    backup_candidate: dict[str, object],
    remote_metadata: dict[str, object],
    archive_path: Path,
    archive_sha_before: str | None,
    archive_sha_after: str | None,
    zip_inventory: pd.DataFrame,
    selected_members: list[str],
    sample_df: pd.DataFrame,
    readiness_df: pd.DataFrame,
    readiness_status: str,
    task_decision: str,
    fallback_activated: bool,
) -> dict[str, object]:
    """Build compact source provenance and readiness manifest."""
    event = pd.to_numeric(readiness_df.get("event_indicator", pd.Series(dtype=float)), errors="coerce")
    asset_count = int(readiness_df["asset_id"].nunique()) if "asset_id" in readiness_df else 0
    local_file = _relative_path(archive_path) if archive_path.exists() else ""
    local_inventory = discover_local_files(archive_path.parent) if archive_path.parent.exists() else pd.DataFrame()
    return {
        "schema_version": "1.0",
        "case_study_version": CASE_VERSION,
        "retrieval_timestamp": timestamp,
        "candidate_decision": {
            "primary_candidate": primary_candidate["dataset_id"],
            "primary_candidate_status": primary_candidate["status"],
            "backup_candidate": backup_candidate["dataset_id"],
            "backup_candidate_status": backup_candidate["status"],
            "fallback_activated": fallback_activated,
            "active_candidate": DATASET_ID if not fallback_activated else backup_candidate["dataset_id"],
        },
        "source": {
            "name": "Backblaze Hard Drive Test Data",
            "official_source": BACKBLAZE_SOURCE_URL,
            "bounded_download_url": BACKBLAZE_2013_URL,
            "license_or_terms_status": primary_candidate.get("license_or_terms_status", "requires_review"),
            "redistribution_status": "raw_not_redistributed_tracked_compact_artifacts_only",
            "source_attribution": "Backblaze Hard Drive Test Data public resource page.",
        },
        "remote_metadata": remote_metadata,
        "raw_archive": {
            "local_path": local_file,
            "exists": archive_path.exists(),
            "size_bytes": int(archive_path.stat().st_size) if archive_path.exists() else 0,
            "sha256_before": archive_sha_before,
            "sha256_after": archive_sha_after,
            "source_sha_unchanged": archive_sha_before in {None, archive_sha_after},
            "local_file_inventory": local_inventory.to_dict(orient="records"),
        },
        "archive_file_inventory": {
            "member_count": int(len(zip_inventory)),
            "csv_member_count": int(zip_inventory["extension"].eq(".csv").sum()) if not zip_inventory.empty else 0,
            "selected_members": selected_members,
        },
        "bounded_sample": {
            "observed_rows": int(len(sample_df)),
            "observed_columns": int(sample_df.shape[1]),
            "selected_member_count": int(len(selected_members)),
            "row_level_data_tracked": False,
        },
        "reliability_structure": {
            "asset_count": asset_count,
            "event_count": int(event.eq(1).sum()),
            "censored_row_count": int(event.eq(0).sum()),
            "recurrent_event_count": int(
                readiness_df.groupby("asset_id")["event_indicator"]
                .sum(min_count=1)
                .fillna(0)
                .gt(1)
                .sum()
                if "asset_id" in readiness_df.columns and "event_indicator" in readiness_df.columns
                else 0
            ),
            "timestamp_or_cycle_coverage": "date column parsed as observation_timestamp",
            "event_interpretation": "failure=1 is treated as observed terminal drive failure flag",
            "censoring_interpretation": "failure=0 rows use last observation in bounded sample as administrative censoring metadata",
        },
        "readiness": {
            "overall_status": readiness_status,
            "selected_primary_task": task_decision,
            "status_vocabulary": ["ready", "conditionally_ready", "not_ready", "unavailable"],
        },
        "raw_data_policy": "Downloaded archive remains local-only under data/raw/** and is not tracked.",
        "limitations": [
            "Only the 2013 Backblaze archive is used for this bounded gate.",
            "Censoring is inferred from last observation in the bounded sample, not a full operational censoring audit.",
            "No reliability model, survival model, RUL regression, or feature selection is performed.",
        ],
    }


def build_readiness_summary(
    report: dict[str, pd.DataFrame],
    *,
    dataset_id: str,
    selected_primary_task: str,
) -> pd.DataFrame:
    """Create a compact readiness summary from generic report tables."""
    asset = report["asset_summary"].iloc[0].to_dict()
    event = report["event_indicator"].iloc[0].to_dict()
    temporal_status = ";".join(report["temporal_order"]["status"].astype(str).tolist())
    validation = report["validation_readiness"]
    rows = [
        {
            "dataset_id": dataset_id,
            "check": "overall_readiness",
            "value": "bounded_access_gate",
            "status": _overall_readiness_status(report),
            "note": "Backblaze 2013 bounded schema/readiness gate; not model training.",
        },
        {
            "dataset_id": dataset_id,
            "check": "asset_identity",
            "value": asset.get("asset_count", 0),
            "status": asset.get("status", "unknown"),
            "note": "serial_number mapped to asset_id.",
        },
        {
            "dataset_id": dataset_id,
            "check": "event_definition",
            "value": event.get("event_count", 0),
            "status": event.get("status", "unknown"),
            "note": "failure column mapped to binary event_indicator.",
        },
        {
            "dataset_id": dataset_id,
            "check": "temporal_order",
            "value": temporal_status,
            "status": "ready" if "ordered" in temporal_status else "conditionally_ready",
            "note": "date mapped to observation_timestamp; cycle is derived per asset.",
        },
        {
            "dataset_id": dataset_id,
            "check": "censoring_support",
            "value": "administrative_last_observation_in_bounded_sample",
            "status": "conditionally_ready",
            "note": "Survival claims require a fuller follow-up and censoring audit.",
        },
        {
            "dataset_id": dataset_id,
            "check": "selected_primary_task",
            "value": selected_primary_task,
            "status": "conditionally_ready",
            "note": "Selected for future horizon-style failure risk readiness, not survival modeling.",
        },
    ]
    for _, row in validation.iterrows():
        rows.append(
            {
                "dataset_id": dataset_id,
                "check": row["validation_type"],
                "value": str(row["ready"]),
                "status": "conditionally_ready" if bool(row["ready"]) else "not_ready",
                "note": row["basis"],
            }
        )
    return pd.DataFrame(rows)


def build_task_feasibility(
    report: dict[str, pd.DataFrame],
    *,
    dataset_id: str,
) -> pd.DataFrame:
    """Decide task feasibility without fitting any model."""
    event_count = int(report["event_indicator"].iloc[0]["event_count"])
    asset_ready = bool(
        report["validation_readiness"]
        .set_index("validation_type")
        .loc["asset_disjoint_split", "ready"]
    )
    time_ready = bool(
        report["validation_readiness"]
        .set_index("validation_type")
        .loc["forward_time_split", "ready"]
    )
    enough_event = event_count >= 5
    rows = [
        {
            "dataset_id": dataset_id,
            "task": "binary_horizon_failure",
            "status": "conditionally_ready" if enough_event and time_ready else "not_ready",
            "selected_primary_task": bool(enough_event and time_ready),
            "basis": "failure event and date support exist; horizon labels require v1.5.3 construction.",
        },
        {
            "dataset_id": dataset_id,
            "task": "terminal_event_prediction",
            "status": "conditionally_ready" if enough_event and asset_ready else "not_ready",
            "selected_primary_task": False,
            "basis": "terminal failure flag exists but no modeling is performed in v1.5.2.",
        },
        {
            "dataset_id": dataset_id,
            "task": "survival_time_to_event",
            "status": "not_ready",
            "selected_primary_task": False,
            "basis": "censoring is inferred from bounded sample; full follow-up audit is required.",
        },
        {
            "dataset_id": dataset_id,
            "task": "rul_regression",
            "status": "not_ready",
            "selected_primary_task": False,
            "basis": "RUL target is not provided and final-life target construction is not implemented.",
        },
        {
            "dataset_id": dataset_id,
            "task": "degradation_trajectory",
            "status": "conditionally_ready",
            "selected_primary_task": False,
            "basis": "SMART attributes provide condition trajectories, but feature engineering is deferred.",
        },
        {
            "dataset_id": dataset_id,
            "task": "recurrent_event_analysis",
            "status": "not_ready",
            "selected_primary_task": False,
            "basis": "Drive failure is terminal; no repair or recurrent event policy exists.",
        },
    ]
    return pd.DataFrame(rows)


def build_validation_feasibility(
    report: dict[str, pd.DataFrame],
    *,
    dataset_id: str,
) -> pd.DataFrame:
    """Create claim-aware validation feasibility output."""
    validation = report["validation_readiness"].copy()
    validation.insert(0, "dataset_id", dataset_id)
    validation["claim_scope"] = validation["validation_type"].map(
        {
            "asset_disjoint_split": "unseen_asset_generalization",
            "forward_time_split": "future_known_population_prediction",
            "combined_asset_time_split": "future_unseen_asset_generalization",
        }
    )
    validation["status"] = validation["ready"].map(
        {True: "conditionally_ready", False: "not_ready"}
    )
    validation["random_row_split_policy"] = "prohibited_as_primary_evidence"
    return validation


def build_conclusion(
    *,
    readiness_status: str,
    selected_primary_task: str,
    fallback_activated: bool,
    event_count: int,
    asset_count: int,
) -> pd.DataFrame:
    """Build a one-row acquisition conclusion artifact."""
    return pd.DataFrame(
        [
            {
                "case_study_version": CASE_VERSION,
                "active_dataset": DATASET_ID if not fallback_activated else BACKUP_DATASET_ID,
                "access_gate_status": "access_verified" if not fallback_activated else "fallback_activated",
                "readiness_verdict": readiness_status,
                "selected_primary_task": selected_primary_task,
                "asset_count": asset_count,
                "event_count": event_count,
                "modeling_performed": False,
                "next_step": "v1.5.3 analysis-ready normalization and event/censoring audit",
                "claim_boundary": "readiness_stage_only_no_reliability_model",
            }
        ]
    )


def select_representative_members(zip_inventory: pd.DataFrame, max_members: int) -> list[str]:
    """Select deterministic CSV members across the archive span."""
    working = zip_inventory.copy()
    if "file_name" not in working.columns:
        working["file_name"] = working["member_path"].map(lambda value: Path(str(value)).name)
    csv_members = (
        working[
            working["extension"].astype(str).str.casefold().eq(".csv")
            & ~working["member_path"].astype(str).str.contains("__MACOSX", case=False, regex=False)
            & ~working["file_name"].astype(str).str.startswith("._")
            & ~working["file_name"].astype(str).str.startswith(".")
        ]["member_path"]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    if max_members <= 0 or len(csv_members) <= max_members:
        return csv_members
    if max_members == 1:
        return [csv_members[0]]
    positions = [
        round(index * (len(csv_members) - 1) / (max_members - 1))
        for index in range(max_members)
    ]
    return [csv_members[position] for position in sorted(set(positions))]


def write_csv(path: str | Path, frame: pd.DataFrame) -> None:
    """Write a CSV with parent directories created."""
    target = PROJECT_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    """Write pretty JSON with parent directories created."""
    target = PROJECT_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_outputs_from_sample(
    *,
    sample_df: pd.DataFrame,
    leakage_map: pd.DataFrame,
    zip_inventory: pd.DataFrame,
    selected_members: list[str],
    timestamp: str,
    primary_candidate: dict[str, object],
    backup_candidate: dict[str, object],
    remote_metadata: dict[str, object],
    archive_path: Path,
    archive_sha_before: str | None,
    archive_sha_after: str | None,
) -> dict[str, object]:
    """Build all compact v1.5.2 output tables from a bounded sample."""
    schema_inventory = build_schema_inventory(
        sample_df,
        dataset_id=DATASET_ID,
        file_id="backblaze_2013_bounded_sample",
    )
    leakage_audit = build_leakage_schema_audit(
        list(sample_df.columns),
        leakage_map,
        dataset_id=DATASET_ID,
    )
    readiness_df = build_backblaze_readiness_frame(sample_df)
    config = build_reliability_config_from_frame(readiness_df)
    report = build_reliability_readiness_report(readiness_df, config)
    task_feasibility = build_task_feasibility(report, dataset_id=DATASET_ID)
    selected = task_feasibility.loc[
        task_feasibility["selected_primary_task"], "task"
    ].tolist()
    selected_primary_task = selected[0] if selected else "none"
    readiness_status = _overall_readiness_status(report)
    readiness_summary = build_readiness_summary(
        report,
        dataset_id=DATASET_ID,
        selected_primary_task=selected_primary_task,
    )
    asset_summary = summarize_backblaze_assets(readiness_df)
    event_summary = summarize_event_censoring_structure(readiness_df)
    validation_feasibility = build_validation_feasibility(report, dataset_id=DATASET_ID)
    event_count = int(event_summary.iloc[0]["event_row_count"])
    asset_count = int(asset_summary.iloc[0]["asset_count"])
    fallback_activated = selected_primary_task == "none"
    conclusion = build_conclusion(
        readiness_status=readiness_status,
        selected_primary_task=selected_primary_task,
        fallback_activated=fallback_activated,
        event_count=event_count,
        asset_count=asset_count,
    )
    spec = build_acquisition_spec(
        timestamp=timestamp,
        primary_candidate=primary_candidate,
        backup_candidate=backup_candidate,
        access_status="access_verified",
        terms_status="public_source_terms_reviewed_for_tracked_compact_artifacts",
        license_status="public_terms_documented_by_source_reuse_scope_requires_attribution",
        redistribution_status="raw_not_redistributed_tracked_compact_artifacts_only",
        active_candidate=DATASET_ID if not fallback_activated else BACKUP_DATASET_ID,
        fallback_activated=fallback_activated,
    )
    manifest = build_manifest(
        timestamp=timestamp,
        primary_candidate=primary_candidate,
        backup_candidate=backup_candidate,
        remote_metadata=remote_metadata,
        archive_path=archive_path,
        archive_sha_before=archive_sha_before,
        archive_sha_after=archive_sha_after,
        zip_inventory=zip_inventory,
        selected_members=selected_members,
        sample_df=sample_df,
        readiness_df=readiness_df,
        readiness_status=readiness_status,
        task_decision=selected_primary_task,
        fallback_activated=fallback_activated,
    )
    return {
        "schema_inventory": schema_inventory,
        "leakage_audit": leakage_audit,
        "readiness_summary": readiness_summary,
        "task_feasibility": task_feasibility,
        "asset_summary": asset_summary,
        "event_summary": event_summary,
        "validation_feasibility": validation_feasibility,
        "conclusion": conclusion,
        "spec": spec,
        "manifest": manifest,
    }


def _overall_readiness_status(report: dict[str, pd.DataFrame]) -> str:
    event_count = int(report["event_indicator"].iloc[0].get("event_count", 0))
    validation_ready = report["validation_readiness"]["ready"].astype(bool).any()
    if event_count <= 0:
        return "not_ready"
    if validation_ready:
        return "conditionally_ready"
    return "not_ready"


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _assert_no_sensitive_values(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    forbidden = [
        "KAGGLE_KEY=",
        "KAGGLE_USERNAME=",
        "password=",
        "secret=",
        "token=",
    ]
    lowered = text.casefold()
    for term in forbidden:
        if term.casefold() in lowered:
            raise ValueError(f"Sensitive term found in output: {path}")
    if re.search(r"[A-Za-z]:\\", text) or "/Users/" in text or "/home/" in text:
        raise ValueError(f"Absolute local path found in output: {path}")


def main() -> None:
    """Execute v1.5.2 acquisition/readiness workflow."""
    args = parse_args()
    timestamp = utc_now_iso()
    candidates = load_candidate_decisions(PROJECT_ROOT / args.candidate_csv)
    primary, backup = select_primary_and_backup(candidates)
    if primary["dataset_id"] != DATASET_ID:
        raise ValueError(f"Unexpected primary candidate: {primary['dataset_id']}")

    raw_root = PROJECT_ROOT / args.raw_dir / DATASET_ID
    archive_path = raw_root / "data_2013.zip"
    archive_sha_before = calculate_sha256(archive_path) if archive_path.exists() else None

    remote_metadata: dict[str, object]
    if args.allow_network:
        remote_metadata = get_remote_file_metadata(BACKBLAZE_2013_URL)
    else:
        remote_metadata = {
            "url": BACKBLAZE_2013_URL,
            "status": "not_checked_network_not_allowed",
        }

    if not archive_path.exists():
        if not (args.allow_network and args.download):
            raise FileNotFoundError(
                "Backblaze 2013 archive is missing. Re-run with --allow-network --download "
                "or place data_2013.zip under data/raw/reliability/backblaze_drive_stats/."
            )
        download_file(
            BACKBLAZE_2013_URL,
            archive_path,
            max_bytes=args.max_download_mb * 1024 * 1024,
        )
    archive_sha_after = calculate_sha256(archive_path)

    zip_inventory = list_zip_members(archive_path)
    selected_members = select_representative_members(zip_inventory, args.max_members)
    if not selected_members:
        raise ValueError("No CSV members found in Backblaze archive.")
    sample_df = read_bounded_csv_sample_from_zip(
        archive_path,
        selected_members,
        max_rows_per_member=args.max_rows_per_member,
    )
    leakage_map = pd.read_csv(PROJECT_ROOT / args.leakage_map)
    outputs = build_outputs_from_sample(
        sample_df=sample_df,
        leakage_map=leakage_map,
        zip_inventory=zip_inventory,
        selected_members=selected_members,
        timestamp=timestamp,
        primary_candidate=primary,
        backup_candidate=backup,
        remote_metadata=remote_metadata,
        archive_path=archive_path,
        archive_sha_before=archive_sha_before,
        archive_sha_after=archive_sha_after,
    )

    write_json(args.acquisition_spec, outputs["spec"])
    write_json(args.manifest_output, outputs["manifest"])
    write_csv(args.schema_output, outputs["schema_inventory"])
    write_csv(args.leakage_output, outputs["leakage_audit"])
    write_csv(args.readiness_output, outputs["readiness_summary"])
    write_csv(args.task_output, outputs["task_feasibility"])
    write_csv(args.asset_output, outputs["asset_summary"])
    write_csv(args.event_output, outputs["event_summary"])
    write_csv(args.validation_output, outputs["validation_feasibility"])
    write_csv(args.conclusion_output, outputs["conclusion"])

    output_paths = [
        args.acquisition_spec,
        args.manifest_output,
        args.schema_output,
        args.leakage_output,
        args.readiness_output,
        args.task_output,
        args.asset_output,
        args.event_output,
        args.validation_output,
        args.conclusion_output,
    ]
    for path in output_paths:
        _assert_no_sensitive_values(PROJECT_ROOT / path)

    print("Primary candidate:", primary["dataset_id"])
    print("Backup candidate:", backup["dataset_id"])
    print("Remote status:", remote_metadata.get("status"))
    print("Archive members:", len(zip_inventory))
    print("Selected members:", len(selected_members))
    print("Observed sample rows:", len(sample_df))
    print("Observed sample columns:", sample_df.shape[1])
    print("Readiness verdict:", outputs["conclusion"].iloc[0]["readiness_verdict"])
    print("Selected primary task:", outputs["conclusion"].iloc[0]["selected_primary_task"])
    print("Archive SHA unchanged:", archive_sha_before in {None, archive_sha_after})


if __name__ == "__main__":
    main()
