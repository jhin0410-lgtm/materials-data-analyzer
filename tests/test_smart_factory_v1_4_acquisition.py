"""Tests for Smart Factory v1.4 acquisition gate artifacts."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_smart_factory_v1_4_acquisition.py"
SPEC_PATH = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "smart_factory"
    / "acquisition_spec_v1_4.json"
)
MANIFEST_PATH = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "smart_factory"
    / "acquisition_manifest_v1_4.json"
)
SCHEMA_INVENTORY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "smart_factory_v1_4_schema_inventory.csv"
)
READINESS_SUMMARY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "smart_factory_v1_4_readiness_summary.csv"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("smart_factory_v14_acquisition", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_bosch_gate_blocks_without_credentials_without_network() -> None:
    module = _load_script_module()

    status = module.build_bosch_gate_status(
        {
            "kaggle_cli_present": True,
            "env_username_present": False,
            "env_key_present": False,
            "kaggle_json_present": False,
        }
    )

    assert status["access_status"] == "blocked_pending_user_action"
    assert status["terms_status"] == "unresolved"
    assert status["download_status"] == "not_attempted"
    assert status["credential_values_logged"] is False


def test_acquisition_spec_and_manifest_parse() -> None:
    spec = _load_json(SPEC_PATH)
    manifest = _load_json(MANIFEST_PATH)

    assert spec["schema_version"] == "1.0"
    assert spec["case_study_version"] == "v1.4.2"
    assert manifest["schema_version"] == "1.0"
    assert manifest["active_candidate"] == "uci_secom"
    assert manifest["bosch_gate"]["access_status"] == "blocked_pending_user_action"
    assert manifest["fallback_activated"] is True


def test_acquisition_artifacts_do_not_contain_credentials_or_absolute_paths() -> None:
    text = "\n".join(
        [
            SPEC_PATH.read_text(encoding="utf-8"),
            MANIFEST_PATH.read_text(encoding="utf-8"),
        ]
    )

    assert "KAGGLE_KEY=" not in text
    assert "KAGGLE_USERNAME=" not in text
    assert "kaggle.json" in text
    assert not re.search(r"[A-Za-z]:\\\\", text)
    assert "/Users/" not in text
    assert "/home/" not in text


def test_secom_manifest_records_source_and_raw_hashes() -> None:
    manifest = _load_json(MANIFEST_PATH)
    raw_files = manifest["raw_files"]

    assert manifest["source"]["doi"] == "10.24432/C54305"
    assert manifest["source"]["license"] == "CC BY 4.0"
    assert manifest["target_mapping"]["-1"] == "pass -> target_pass_fail=0"
    assert manifest["target_mapping"]["1"] == "fail -> target_pass_fail=1"
    assert manifest["timestamp_parseable_count"] == manifest["row_count"]
    assert {record["file_name"] for record in raw_files}.issuperset(
        {"secom.data", "secom_labels.data"}
    )
    for record in raw_files:
        assert len(record["sha256"]) == 64
        assert not Path(record["relative_path"]).is_absolute()


def test_schema_inventory_contains_expected_roles() -> None:
    inventory = pd.read_csv(SCHEMA_INVENTORY_PATH)

    roles = set(inventory["role"])
    assert {
        "source_row_order",
        "unit_id",
        "observation_timestamp",
        "target",
        "process_feature",
    }.issubset(roles)
    assert (inventory["column_name"] == "source_sample_index").any()
    assert (inventory["column_name"] == "target_pass_fail").any()
    assert (inventory["column_name"].str.startswith("feature_")).any()


def test_readiness_summary_records_fallback_limitations() -> None:
    readiness = pd.read_csv(READINESS_SUMMARY_PATH)
    rows = readiness.set_index("check")

    assert rows.loc["overall_readiness", "status"] == "conditionally_ready"
    assert rows.loc["group_split_feasibility", "status"] == "not_ready"
    assert rows.loc["capability_readiness", "status"] == "not_ready"
    assert rows.loc["time_split_feasibility", "status"] == "conditionally_ready"
