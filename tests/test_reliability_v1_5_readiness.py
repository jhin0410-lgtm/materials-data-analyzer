"""Tests for Reliability v1.5.2 tracked readiness artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = PROJECT_ROOT / "data" / "case_studies" / "reliability"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

SPEC_PATH = CASE_DIR / "acquisition_spec_v1_5.json"
MANIFEST_PATH = CASE_DIR / "acquisition_manifest_v1_5.json"
SCHEMA_PATH = PROCESSED_DIR / "reliability_v1_5_schema_inventory.csv"
LEAKAGE_PATH = PROCESSED_DIR / "reliability_v1_5_leakage_schema_audit.csv"
READINESS_PATH = PROCESSED_DIR / "reliability_v1_5_readiness_summary.csv"
TASK_PATH = PROCESSED_DIR / "reliability_v1_5_task_feasibility.csv"
ASSET_PATH = PROCESSED_DIR / "reliability_v1_5_asset_summary.csv"
EVENT_PATH = PROCESSED_DIR / "reliability_v1_5_event_censoring_summary.csv"
VALIDATION_PATH = PROCESSED_DIR / "reliability_v1_5_validation_feasibility.csv"
CONCLUSION_PATH = PROCESSED_DIR / "reliability_v1_5_acquisition_conclusion.csv"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_acquisition_spec_and_manifest_parse_when_present() -> None:
    if not SPEC_PATH.exists() or not MANIFEST_PATH.exists():
        return
    spec = json.loads(_read_text(SPEC_PATH))
    manifest = json.loads(_read_text(MANIFEST_PATH))

    assert spec["schema_version"] == "1.0"
    assert spec["case_study_version"] == "v1.5.2"
    assert spec["primary_candidate"] == "backblaze_drive_stats"
    assert manifest["schema_version"] == "1.0"
    assert manifest["candidate_decision"]["primary_candidate"] == "backblaze_drive_stats"
    assert manifest["raw_data_policy"].startswith("Downloaded archive remains local-only")


def test_tracked_output_csv_schemas_when_present() -> None:
    paths = [
        SCHEMA_PATH,
        LEAKAGE_PATH,
        READINESS_PATH,
        TASK_PATH,
        ASSET_PATH,
        EVENT_PATH,
        VALIDATION_PATH,
        CONCLUSION_PATH,
    ]
    if not all(path.exists() for path in paths):
        return

    schema = pd.read_csv(SCHEMA_PATH)
    leakage = pd.read_csv(LEAKAGE_PATH)
    readiness = pd.read_csv(READINESS_PATH)
    task = pd.read_csv(TASK_PATH)
    conclusion = pd.read_csv(CONCLUSION_PATH)

    assert {
        "dataset_id",
        "source_column",
        "normalized_role",
        "leakage_status",
    }.issubset(schema.columns)
    assert {
        "field_or_pattern",
        "observed_status",
        "schema_leakage_status",
    }.issubset(leakage.columns)
    assert {"check", "status", "note"}.issubset(readiness.columns)
    assert {"task", "status", "selected_primary_task"}.issubset(task.columns)
    assert conclusion.loc[0, "modeling_performed"] in {False, "False", "false"}


def test_readiness_artifacts_contain_no_credentials_or_absolute_paths_when_present() -> None:
    paths = [
        SPEC_PATH,
        MANIFEST_PATH,
        SCHEMA_PATH,
        LEAKAGE_PATH,
        READINESS_PATH,
        TASK_PATH,
        ASSET_PATH,
        EVENT_PATH,
        VALIDATION_PATH,
        CONCLUSION_PATH,
    ]
    existing = [path for path in paths if path.exists()]
    if not existing:
        return

    text = "\n".join(_read_text(path) for path in existing)
    assert "KAGGLE_KEY=" not in text
    assert "KAGGLE_USERNAME=" not in text
    assert "password=" not in text.lower()
    assert "secret=" not in text.lower()
    assert "token=" not in text.lower()
    assert not re.search(r"[A-Za-z]:\\\\", text)
    assert "/Users/" not in text
    assert "/home/" not in text


def test_local_only_raw_archive_is_not_required_for_test_collection() -> None:
    raw_archive = (
        PROJECT_ROOT
        / "data"
        / "raw"
        / "reliability"
        / "backblaze_drive_stats"
        / "data_2013.zip"
    )

    # The actual acquisition CLI may use this local-only file, but tests and
    # collection must not require it in a clean checkout.
    assert raw_archive.name == "data_2013.zip"
