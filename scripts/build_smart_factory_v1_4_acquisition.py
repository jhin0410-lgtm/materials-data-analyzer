"""Build Smart Factory v1.4.2 acquisition and readiness artifacts.

The script checks the Bosch Kaggle access gate without printing credentials. If
Bosch is blocked or unresolved, it activates the UCI SECOM fallback, downloads
the compact official raw archive, extracts only the required raw files into
``data/raw/``, and writes compact tracked provenance/readiness artifacts.

No model training, feature selection, SPC charting, or dashboard generation is
performed here.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analyzers.process_quality_readiness import (  # noqa: E402
    ProcessQualityReadinessConfig,
    build_process_quality_readiness_report,
)
from connectors.smart_factory import (  # noqa: E402
    build_schema_inventory,
    build_secom_aligned_frame,
    discover_local_files,
    extract_zip_members,
    sha256_file,
)


BOSCH_COMPETITION_SLUG = "bosch-production-line-performance"
SECOM_DATASET_URL = "https://archive.ics.uci.edu/dataset/179/secom"
SECOM_DOWNLOAD_URL = "https://archive.ics.uci.edu/static/public/179/secom.zip"
SECOM_DOI = "10.24432/C54305"
SECOM_LICENSE = "CC BY 4.0"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Build Smart Factory v1.4.2 acquisition/readiness artifacts."
    )
    parser.add_argument(
        "--raw-dir",
        default="data/raw/smart_factory/secom",
        help="Local-only raw SECOM directory.",
    )
    parser.add_argument(
        "--acquisition-spec",
        default="data/case_studies/smart_factory/acquisition_spec_v1_4.json",
    )
    parser.add_argument(
        "--manifest-output",
        default="data/case_studies/smart_factory/acquisition_manifest_v1_4.json",
    )
    parser.add_argument(
        "--schema-output",
        default="data/processed/smart_factory_v1_4_schema_inventory.csv",
    )
    parser.add_argument(
        "--readiness-output",
        default="data/processed/smart_factory_v1_4_readiness_summary.csv",
    )
    return parser.parse_args()


def utc_now_iso() -> str:
    """Return a UTC timestamp for provenance records."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def detect_kaggle_environment() -> dict[str, bool]:
    """Detect Kaggle CLI and credential presence without returning secret values."""
    return {
        "kaggle_cli_present": shutil.which("kaggle") is not None,
        "env_username_present": bool(_env_present("KAGGLE_USERNAME")),
        "env_key_present": bool(_env_present("KAGGLE_KEY")),
        "kaggle_json_present": (Path.home() / ".kaggle" / "kaggle.json").exists(),
    }


def build_bosch_gate_status(kaggle_environment: dict[str, bool]) -> dict[str, object]:
    """Build a conservative Bosch access-gate status record."""
    cli_present = bool(kaggle_environment.get("kaggle_cli_present"))
    credential_present = bool(
        (
            kaggle_environment.get("env_username_present")
            and kaggle_environment.get("env_key_present")
        )
        or kaggle_environment.get("kaggle_json_present")
    )
    if not cli_present:
        reason = "kaggle_cli_missing"
    elif not credential_present:
        reason = "kaggle_credentials_missing"
    else:
        reason = "not_checked_by_this_script"
    if not cli_present or not credential_present:
        return {
            "candidate": "Bosch Production Line Performance",
            "competition_slug": BOSCH_COMPETITION_SLUG,
            "candidate_status": "conditional_primary_candidate",
            "access_status": "blocked_pending_user_action",
            "terms_status": "unresolved",
            "redistribution_status": "unresolved",
            "download_status": "not_attempted",
            "file_inventory_status": "not_attempted",
            "schema_status": "not_attempted",
            "block_reason": reason,
            "credential_values_logged": False,
        }
    return {
        "candidate": "Bosch Production Line Performance",
        "competition_slug": BOSCH_COMPETITION_SLUG,
        "candidate_status": "conditional_primary_candidate",
        "access_status": "unresolved",
        "terms_status": "unresolved",
        "redistribution_status": "unresolved",
        "download_status": "not_attempted",
        "file_inventory_status": "not_attempted",
        "schema_status": "not_attempted",
        "block_reason": "manual_kaggle_terms_and_file_inventory_check_required",
        "credential_values_logged": False,
    }


def download_file_if_missing(url: str, output_path: Path) -> bool:
    """Download ``url`` to ``output_path`` only when the file is absent."""
    if output_path.exists():
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, output_path)  # noqa: S310 - explicit public URL
    return True


def build_acquisition_spec(
    timestamp: str,
    bosch_gate: dict[str, object],
    active_candidate: str,
    fallback_activated: bool,
) -> dict[str, object]:
    """Build the v1.4 acquisition specification."""
    return {
        "schema_version": "1.0",
        "case_study_version": "v1.4.2",
        "candidate": "smart_factory_process_quality",
        "source_type": "public_manufacturing_dataset",
        "source_url": {
            "bosch": "https://www.kaggle.com/competitions/bosch-production-line-performance",
            "secom": SECOM_DATASET_URL,
        },
        "access_method": {
            "bosch": "kaggle_cli_metadata_only_if_authenticated",
            "secom": "official_uci_static_zip_download",
        },
        "access_status": {
            "bosch": bosch_gate["access_status"],
            "secom": "downloaded" if active_candidate == "uci_secom" else "not_attempted",
        },
        "terms_status": {
            "bosch": bosch_gate["terms_status"],
            "secom": "cc_by_4_0",
        },
        "redistribution_status": {
            "bosch": bosch_gate["redistribution_status"],
            "secom": "tracked_artifacts_only_raw_local",
        },
        "retrieval_timestamp": timestamp,
        "expected_files": {
            "bosch": [
                "train_numeric.csv.zip",
                "train_categorical.csv.zip",
                "train_date.csv.zip",
                "train_labels.csv.zip",
                "test_numeric.csv.zip",
                "test_categorical.csv.zip",
                "test_date.csv.zip",
            ],
            "secom": [
                "secom.data",
                "secom_labels.data",
                "secom.names",
            ],
        },
        "observed_files": {
            "bosch": [],
            "secom": [
                "secom.data",
                "secom_labels.data",
                "secom.names",
            ],
        },
        "file_sizes": {
            "bosch": "not_attempted",
            "secom": "recorded_in_acquisition_manifest_v1_4_json",
        },
        "checksum_policy": "Compute SHA256 for local raw files and store only digests in tracked manifest.",
        "raw_local_paths": [
            "data/raw/smart_factory/secom/secom.data",
            "data/raw/smart_factory/secom/secom_labels.data",
            "data/raw/smart_factory/secom/secom.names",
        ],
        "tracked_manifest_paths": [
            "data/case_studies/smart_factory/acquisition_manifest_v1_4.json",
            "data/processed/smart_factory_v1_4_schema_inventory.csv",
            "data/processed/smart_factory_v1_4_readiness_summary.csv",
        ],
        "fallback_policy": {
            "fallback_activated": fallback_activated,
            "active_candidate": active_candidate,
            "rule": "If Bosch access, terms, or schema verification is blocked or unresolved, use UCI SECOM as the operational fallback.",
        },
        "stop_conditions": [
            "Kaggle authentication unavailable",
            "competition rules not accepted",
            "terms or redistribution unresolved",
            "download volume exceeds practical local budget",
            "target missing",
            "ID and feature files cannot be aligned",
            "timestamp cannot be interpreted",
            "source checksum changes unexpectedly",
            "SECOM feature and label row counts mismatch",
        ],
        "credential_policy": {
            "store_credentials": False,
            "log_credentials": False,
            "tracked_artifacts_must_not_include": [
                "KAGGLE_USERNAME",
                "KAGGLE_KEY",
                "kaggle.json",
                "absolute local paths",
            ],
        },
    }


def build_acquisition_manifest(
    timestamp: str,
    bosch_gate: dict[str, object],
    raw_dir: Path,
    aligned_df: pd.DataFrame,
    schema_inventory: pd.DataFrame,
    readiness_result: str,
) -> dict[str, object]:
    """Build compact provenance and acquisition manifest."""
    raw_files = discover_local_files(raw_dir, patterns=("secom.data", "secom_labels.data", "secom.names"))
    raw_records = raw_files.to_dict(orient="records")
    target_counts = {
        str(key): int(value)
        for key, value in aligned_df["target_pass_fail"].value_counts(dropna=False).sort_index().items()
    }
    feature_columns = [column for column in aligned_df.columns if column.startswith("feature_")]
    timestamp_parseable_count = int(aligned_df["observation_timestamp"].notna().sum())
    timestamp_duplicate_count = int(
        aligned_df["observation_timestamp"].duplicated(keep=False).sum()
    )
    source_order_timestamp_monotonic = bool(
        aligned_df.sort_values("source_sample_index")["observation_timestamp"]
        .dropna()
        .is_monotonic_increasing
    )
    return {
        "schema_version": "1.0",
        "case_study_version": "v1.4.2",
        "retrieval_timestamp": timestamp,
        "bosch_gate": bosch_gate,
        "fallback_activated": bosch_gate["access_status"] != "access_verified",
        "active_candidate": "uci_secom",
        "source": {
            "name": "SECOM",
            "url": SECOM_DATASET_URL,
            "download_url": SECOM_DOWNLOAD_URL,
            "doi": SECOM_DOI,
            "license": SECOM_LICENSE,
            "citation": "McCann, M. & Johnston, A. (2008). SECOM [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C54305.",
        },
        "raw_files": raw_records,
        "row_count": int(len(aligned_df)),
        "feature_count": int(len(feature_columns)),
        "column_count": int(aligned_df.shape[1]),
        "target_column": "target_pass_fail",
        "target_mapping": {
            "-1": "pass -> target_pass_fail=0",
            "1": "fail -> target_pass_fail=1",
        },
        "target_counts": target_counts,
        "label_join_policy": "Join SECOM feature matrix and label/timestamp file by row order after verifying equal row counts.",
        "timestamp_parse_policy": "Parse labels date and time columns with day-first format %d/%m/%Y %H:%M:%S.",
        "timestamp_parseable_count": timestamp_parseable_count,
        "timestamp_duplicate_count": timestamp_duplicate_count,
        "source_order_timestamp_monotonic": source_order_timestamp_monotonic,
        "schema_inventory_columns": list(schema_inventory.columns),
        "readiness_result": readiness_result,
        "raw_data_policy": "Raw SECOM files remain local-only under data/raw/ and are not tracked.",
    }


def build_readiness_summary(
    aligned_df: pd.DataFrame,
    readiness_report: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Create a compact v1.4 readiness summary table."""
    feature_columns = [column for column in aligned_df.columns if column.startswith("feature_")]
    missing_values = int(aligned_df[feature_columns].isna().sum().sum())
    total_feature_values = int(len(aligned_df) * len(feature_columns))
    timestamp_parseable = int(aligned_df["observation_timestamp"].notna().sum())
    timestamp_monotonic = bool(
        aligned_df["observation_timestamp"].dropna().is_monotonic_increasing
    )
    timestamp_duplicate_count = int(
        aligned_df["observation_timestamp"].duplicated(keep=False).sum()
    )
    source_order_timestamp_monotonic = bool(
        aligned_df.sort_values("source_sample_index")["observation_timestamp"]
        .dropna()
        .is_monotonic_increasing
    )
    target_counts = aligned_df["target_pass_fail"].value_counts(dropna=False)
    fail_count = int(target_counts.get(1, 0))
    pass_count = int(target_counts.get(0, 0))
    duplicate_sample_count = int(aligned_df.duplicated(subset=["sample_id"]).sum())
    rows = [
        {
            "check": "overall_readiness",
            "value": "conditioned_on_SECOM_fallback",
            "status": "conditionally_ready",
            "note": "SECOM is usable for compact process-quality readiness and time-aware classification exploration, but lacks explicit equipment/lot/product groups and spec limits.",
        },
        {
            "check": "row_count",
            "value": len(aligned_df),
            "status": "ready",
            "note": "UCI metadata states 1567 examples.",
        },
        {
            "check": "feature_count",
            "value": len(feature_columns),
            "status": "ready",
            "note": "Whitespace-separated SECOM process measurement matrix.",
        },
        {
            "check": "target_availability",
            "value": int(aligned_df["target_pass_fail"].notna().sum()),
            "status": "ready",
            "note": "Pass/fail labels loaded from secom_labels.data.",
        },
        {
            "check": "target_imbalance",
            "value": f"pass={pass_count}; fail={fail_count}",
            "status": "conditionally_ready",
            "note": "Failure class is small and must be reported in any future modeling.",
        },
        {
            "check": "missingness",
            "value": f"{missing_values}/{total_feature_values}",
            "status": "conditionally_ready" if missing_values else "ready",
            "note": "Missing feature values are expected in SECOM and must be handled train-only.",
        },
        {
            "check": "timestamp_parseability",
            "value": f"{timestamp_parseable}/{len(aligned_df)}",
            "status": "ready" if timestamp_parseable == len(aligned_df) else "not_ready",
            "note": "Labels file provides date and time for the test point.",
        },
        {
            "check": "timestamp_duplicate_count",
            "value": timestamp_duplicate_count,
            "status": "ready" if timestamp_duplicate_count == 0 else "conditionally_ready",
            "note": "Duplicate timestamps are counted in source order and retained for audit.",
        },
        {
            "check": "source_order_timestamp_monotonicity",
            "value": str(source_order_timestamp_monotonic),
            "status": "ready" if source_order_timestamp_monotonic else "conditionally_ready",
            "note": "Timestamp monotonicity is evaluated in original source row order without sorting before feature-label alignment.",
        },
        {
            "check": "chronological_ordering",
            "value": str(timestamp_monotonic),
            "status": "ready" if timestamp_monotonic else "conditionally_ready",
            "note": "Rows can be sorted by parsed timestamp before time-aware validation.",
        },
        {
            "check": "explicit_group_ids",
            "value": "none",
            "status": "not_ready",
            "note": "SECOM does not provide explicit equipment, lot, batch, product, or recipe IDs.",
        },
        {
            "check": "derived_group_proxies",
            "value": "timestamp_blocks_only",
            "status": "conditionally_ready",
            "note": "Time blocks may be used as drift proxies, not as equipment or lot IDs.",
        },
        {
            "check": "delayed_quality_interpretation",
            "value": "same_test_point_timestamp",
            "status": "conditionally_ready",
            "note": "The timestamp belongs to the labeled test point; no separate quality measurement timestamp is available.",
        },
        {
            "check": "duplicate_risk",
            "value": duplicate_sample_count,
            "status": "ready" if duplicate_sample_count == 0 else "conditionally_ready",
            "note": "Synthetic sample_id is unique by row order.",
        },
        {
            "check": "group_split_feasibility",
            "value": "no_explicit_groups",
            "status": "not_ready",
            "note": "Group-aware validation by lot/equipment/product is not supported by SECOM.",
        },
        {
            "check": "time_split_feasibility",
            "value": "timestamp_available",
            "status": "conditionally_ready",
            "note": "Forward chronological split is possible after sorting by timestamp.",
        },
        {
            "check": "combined_validation_feasibility",
            "value": "time_only_no_groups",
            "status": "not_ready",
            "note": "Combined future-group validation is not feasible without explicit groups.",
        },
        {
            "check": "spc_readiness",
            "value": "numeric_features_and_timestamp",
            "status": "conditionally_ready",
            "note": "Individuals/moving-range style checks may be explored descriptively; rational subgroups are absent.",
        },
        {
            "check": "capability_readiness",
            "value": "spec_limits_absent",
            "status": "not_ready",
            "note": "Cp/Cpk/Pp/Ppk must not be calculated without external specification limits.",
        },
        {
            "check": "drift_readiness",
            "value": "timestamp_blocks_possible",
            "status": "conditionally_ready",
            "note": "Feature stability and drift proxies can be summarized by time block.",
        },
        {
            "check": "anomaly_readiness",
            "value": "numeric_features_available",
            "status": "conditionally_ready",
            "note": "Transparent rule-based anomaly screening is possible; no anomaly model is trained here.",
        },
    ]
    # Keep a trace that the generic readiness framework was actually executed.
    rows.append(
        {
            "check": "generic_readiness_tables",
            "value": ",".join(sorted(readiness_report)),
            "status": "ready",
            "note": "Built with process_quality_readiness.py using dataset-specific config outside the generic module.",
        }
    )
    return pd.DataFrame(rows)


def _env_present(name: str) -> bool:
    return bool(__import__("os").environ.get(name))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    """Run acquisition gate and SECOM fallback readiness generation."""
    args = parse_args()
    timestamp = utc_now_iso()
    raw_dir = PROJECT_ROOT / args.raw_dir
    zip_path = raw_dir / "secom.zip"
    feature_path = raw_dir / "secom.data"
    label_path = raw_dir / "secom_labels.data"

    kaggle_environment = detect_kaggle_environment()
    bosch_gate = build_bosch_gate_status(kaggle_environment)
    fallback_activated = bosch_gate["access_status"] != "access_verified"
    active_candidate = "uci_secom" if fallback_activated else "bosch"

    if fallback_activated:
        downloaded = download_file_if_missing(SECOM_DOWNLOAD_URL, zip_path)
        extract_zip_members(
            zip_path,
            raw_dir,
            ["secom.data", "secom_labels.data", "secom.names"],
            overwrite=False,
        )
    else:
        downloaded = False

    aligned_df = build_secom_aligned_frame(feature_path, label_path)
    feature_columns = [column for column in aligned_df.columns if column.startswith("feature_")]
    schema_inventory = build_schema_inventory(aligned_df, dataset_name="uci_secom")

    readiness_config = ProcessQualityReadinessConfig(
        required_columns=["sample_id", "observation_timestamp", "target_pass_fail"],
        observation_timestamp_column="observation_timestamp",
        quality_timestamp_column=None,
        group_columns=[],
        target_columns=["target_pass_fail"],
        process_feature_columns=feature_columns,
        specification_limit_columns=[],
        forbidden_feature_columns=["target_raw"],
        duplicate_key_columns=["sample_id"],
        min_groups_for_group_split=3,
        min_rows_for_time_split=20,
    )
    readiness_report = build_process_quality_readiness_report(aligned_df, readiness_config)
    readiness_summary = build_readiness_summary(aligned_df, readiness_report)
    readiness_result = str(
        readiness_summary.loc[
            readiness_summary["check"] == "overall_readiness", "status"
        ].iloc[0]
    )

    acquisition_spec = build_acquisition_spec(
        timestamp=timestamp,
        bosch_gate=bosch_gate,
        active_candidate=active_candidate,
        fallback_activated=fallback_activated,
    )
    manifest = build_acquisition_manifest(
        timestamp=timestamp,
        bosch_gate=bosch_gate,
        raw_dir=raw_dir,
        aligned_df=aligned_df,
        schema_inventory=schema_inventory,
        readiness_result=readiness_result,
    )
    manifest["secom_zip_downloaded_this_run"] = downloaded
    manifest["secom_zip_sha256"] = sha256_file(zip_path)

    spec_path = PROJECT_ROOT / args.acquisition_spec
    manifest_path = PROJECT_ROOT / args.manifest_output
    schema_path = PROJECT_ROOT / args.schema_output
    readiness_path = PROJECT_ROOT / args.readiness_output

    _write_json(spec_path, acquisition_spec)
    _write_json(manifest_path, manifest)
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    readiness_path.parent.mkdir(parents=True, exist_ok=True)
    schema_inventory.to_csv(schema_path, index=False)
    readiness_summary.to_csv(readiness_path, index=False)

    print("Bosch access status:", bosch_gate["access_status"])
    print("Bosch terms status:", bosch_gate["terms_status"])
    print("Active candidate:", active_candidate)
    print("Fallback activated:", fallback_activated)
    print("SECOM rows:", len(aligned_df))
    print("SECOM features:", len(feature_columns))
    print("Readiness result:", readiness_result)
    print("Tracked acquisition spec:", args.acquisition_spec)
    print("Tracked acquisition manifest:", args.manifest_output)
    print("Tracked schema inventory:", args.schema_output)
    print("Tracked readiness summary:", args.readiness_output)


if __name__ == "__main__":
    main()
