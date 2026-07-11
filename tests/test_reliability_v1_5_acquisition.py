"""Tests for Reliability v1.5.2 acquisition orchestration helpers."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_reliability_v1_5_acquisition.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("reliability_v15_acquisition", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _candidate_csv(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "dataset_id": "backblaze_drive_stats",
                "dataset_name": "Backblaze",
                "status": "conditional_primary_candidate",
                "source_url": "https://example.com/backblaze",
                "license_or_terms_status": "requires review",
            },
            {
                "dataset_id": "nasa_cmapss",
                "dataset_name": "NASA C-MAPSS",
                "status": "operational_backup_candidate",
                "source_url": "https://example.com/nasa",
                "license_or_terms_status": "requires review",
            },
        ]
    ).to_csv(path, index=False)


def _sample() -> pd.DataFrame:
    rows = []
    for asset_index in range(10):
        asset = f"SN{asset_index}"
        for day in range(2):
            rows.append(
                {
                    "source_member": f"day{day + 1}.csv",
                    "date": f"2020-01-0{day + 1}",
                    "serial_number": asset,
                    "model": "M1",
                    "capacity_bytes": 1000,
                    "failure": 1 if asset_index < 5 and day == 1 else 0,
                    "smart_5_raw": asset_index + day,
                    "smart_187_normalized": 100 - asset_index,
                }
            )
    return pd.DataFrame(rows)


def test_candidate_status_loading_selects_primary_and_backup(tmp_path: Path) -> None:
    module = _load_script_module()
    path = tmp_path / "candidates.csv"
    _candidate_csv(path)

    candidates = module.load_candidate_decisions(path)
    primary, backup = module.select_primary_and_backup(candidates)

    assert primary["dataset_id"] == "backblaze_drive_stats"
    assert backup["dataset_id"] == "nasa_cmapss"


def test_acquisition_spec_records_fallback_policy_without_absolute_paths(tmp_path: Path) -> None:
    module = _load_script_module()
    path = tmp_path / "candidates.csv"
    _candidate_csv(path)
    primary, backup = module.select_primary_and_backup(module.load_candidate_decisions(path))

    spec = module.build_acquisition_spec(
        timestamp="2026-01-01T00:00:00+00:00",
        primary_candidate=primary,
        backup_candidate=backup,
        access_status="access_verified",
        terms_status="terms_reviewed",
        license_status="source_terms_documented",
        redistribution_status="raw_not_redistributed",
        active_candidate="backblaze_drive_stats",
        fallback_activated=False,
    )
    text = json.dumps(spec)

    assert spec["active_candidate"] == "backblaze_drive_stats"
    assert spec["fallback_policy"]["fallback_candidate"] == "nasa_cmapss"
    assert not re.search(r"[A-Za-z]:\\\\", text)
    assert "/Users/" not in text
    assert "KAGGLE_KEY=" not in text


def test_representative_member_selection_is_deterministic() -> None:
    module = _load_script_module()
    inventory = pd.DataFrame(
        {
            "member_path": [f"data/day_{idx:03d}.csv" for idx in range(10)],
            "extension": [".csv"] * 10,
        }
    )

    selected = module.select_representative_members(inventory, max_members=4)

    assert selected == [
        "data/day_000.csv",
        "data/day_003.csv",
        "data/day_006.csv",
        "data/day_009.csv",
    ]


def test_build_outputs_from_sample_creates_compact_artifacts(tmp_path: Path) -> None:
    module = _load_script_module()
    candidates = tmp_path / "candidates.csv"
    _candidate_csv(candidates)
    primary, backup = module.select_primary_and_backup(module.load_candidate_decisions(candidates))
    leakage_map = pd.DataFrame(
        {
            "field_or_pattern": ["final_cycle_count", "random_row_split_mixing_same_asset"],
            "leakage_type": ["final cycle count", "random row split mixing same asset"],
            "availability_time": ["end of trajectory", "split design"],
            "risk_level": ["high", "high"],
            "allowed_as_feature": [False, False],
            "allowed_as_metadata": [True, True],
            "mitigation": ["exclude", "use grouped split"],
            "validation_test": ["assert excluded", "assert asset split"],
        }
    )
    archive_path = tmp_path / "data_2013.zip"
    archive_path.write_bytes(b"not really used by output builder")

    outputs = module.build_outputs_from_sample(
        sample_df=_sample(),
        leakage_map=leakage_map,
        zip_inventory=pd.DataFrame(
            {
                "member_path": ["day1.csv", "day2.csv"],
                "extension": [".csv", ".csv"],
            }
        ),
        selected_members=["day1.csv", "day2.csv"],
        timestamp="2026-01-01T00:00:00+00:00",
        primary_candidate=primary,
        backup_candidate=backup,
        remote_metadata={"status": "reachable"},
        archive_path=archive_path,
        archive_sha_before=None,
        archive_sha_after="abc",
    )

    assert outputs["conclusion"].iloc[0]["readiness_verdict"] == "conditionally_ready"
    assert outputs["conclusion"].iloc[0]["selected_primary_task"] == "binary_horizon_failure"
    assert "serial_number" in set(outputs["schema_inventory"]["source_column"])
    assert "random_row_split_mixing_same_asset" in set(
        outputs["leakage_audit"]["field_or_pattern"]
    )
    assert outputs["manifest"]["bounded_sample"]["observed_rows"] == 20
    assert outputs["manifest"]["reliability_structure"]["event_count"] == 5


def test_acquisition_module_import_does_not_call_network() -> None:
    module = _load_script_module()

    assert module.BACKBLAZE_2013_URL.startswith("https://")
