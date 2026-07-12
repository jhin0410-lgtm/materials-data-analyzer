from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

SPEC_PATH = PROJECT_ROOT / "data/case_studies/reliability/classification_spec_v1_5.json"


def _spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_classification_spec_parses_and_fixes_7d_contract() -> None:
    spec = _spec()

    assert spec["case_study_version"] == "v1.5.4"
    assert spec["task"]["horizon_days"] == 7
    assert spec["task"]["lookback_days"] == 7
    assert spec["task"]["target_column"] == "target_failure_within_7d"
    assert spec["validation_hierarchy"]["random_reference_policy"].startswith("optimistic")


def test_classification_spec_uses_conservative_smart_candidates() -> None:
    spec = _spec()

    assert spec["feature_policy"]["smart_feature_candidates"] == [
        "smart_194_raw",
        "smart_197_raw",
        "smart_1_raw",
        "smart_5_raw",
        "smart_9_raw",
    ]
    assert "serial_number" in spec["feature_policy"]["prohibited_features"]
    assert "days_to_last_observation" in spec["feature_policy"]["prohibited_features"]


def test_classification_spec_declares_resource_and_prediction_policies() -> None:
    spec = _spec()

    assert spec["resource_budget"]["test_set_subsampling"] == "prohibited"
    assert "training_partition_only" in spec["resource_budget"]["training_subsampling_policy"]
    assert spec["repeated_origin_policy"]["primary_weighting"] == "asset_balanced"
    assert "raw_row" in spec["repeated_origin_policy"]["weighting_policies"]
    assert spec["calibration_boundary"]["calibrated_probability_claim"] == "prohibited"


def test_classification_spec_local_outputs_are_not_tracked_paths() -> None:
    spec = _spec()

    assert spec["local_outputs"]["feature_dataset"].endswith(
        "reliability_v1_5_horizon_7d_lookback_7d_dataset.csv"
    )
    assert spec["local_outputs"]["predictions"].endswith(
        "reliability_v1_5_classification_predictions.csv"
    )
    tracked = "\n".join(spec["tracked_outputs"].values())
    assert "classification_predictions" not in tracked


def test_classification_artifacts_contain_no_credentials_or_absolute_paths() -> None:
    text = SPEC_PATH.read_text(encoding="utf-8")

    assert "KAGGLE_KEY" not in text
    assert "KAGGLE_USERNAME" not in text
    assert "password=" not in text.lower()
    assert "secret=" not in text.lower()
    assert "token=" not in text.lower()
    assert not any(marker in text for marker in ["C:\\\\", "/Users/", "/home/"])


def test_fake_compact_output_schema_has_no_raw_serial_number() -> None:
    metrics = pd.DataFrame(
        [
            {
                "split_id": "combined_asset_disjoint_future_holdout",
                "model_name": "dummy_prior",
                "feature_set": "smart_only_conservative",
                "average_precision": 0.01,
                "source_sha256": "abc",
            }
        ]
    )

    assert "serial_number" not in metrics.columns
    assert "source_sha256" in metrics.columns
