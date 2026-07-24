import json
from pathlib import Path

import pytest

from src.platform_core.battery_forecasting import (
    BENCHMARK_ID,
    BatteryForecastConfig,
    resolve_repo_path,
)


def _payload():
    return {
        "schema_version": "2.6.1",
        "benchmark_id": BENCHMARK_ID,
        "case_study_id": "kaggle_battery",
        "input_path": "data/input.csv",
        "source_lineage_path": "data/lineage.json",
        "group_column": "battery_id",
        "time_column": "cycle_index",
        "target_column": "capacity_retention_percent",
        "target_unit": "percent",
        "horizon": 5,
        "lags": [1, 2, 3],
        "rolling_window": 5,
        "minimum_history": 5,
        "split_method": "group_kfold",
        "n_splits": 3,
        "random_seed": 42,
        "models": ["persistence", "ridge"],
        "ridge_alpha": 1.0,
        "plausibility_min": 0.0,
        "plausibility_max": 150.0,
        "large_change_threshold": 25.0,
        "duplicate_cycle_policy": "reject_trajectory",
        "unordered_cycle_policy": "stable_sort_with_audit",
        "credential_policy": {
            "store_credentials": False,
            "network_access_required": False,
        },
        "output_root": "outputs/v2_6_battery_generalization",
        "output_policy": "local_details_and_tracked_compact_summary",
    }


@pytest.mark.parametrize("field", ["module_path", "callable_name"])
def test_arbitrary_import_and_callable_fields_are_rejected(field):
    payload = _payload()
    payload[field] = "package.module.function"

    with pytest.raises(ValueError, match="unknown config field"):
        BatteryForecastConfig.from_mapping(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_path", "C:/private/input.csv"),
        ("input_path", "../private/input.csv"),
        ("source_lineage_path", "/private/lineage.json"),
        ("output_root", "../../outputs"),
    ],
)
def test_absolute_and_traversal_paths_are_rejected(field, value):
    payload = _payload()
    payload[field] = value

    with pytest.raises(ValueError, match="repository-relative"):
        BatteryForecastConfig.from_mapping(payload)


def test_secret_like_fields_and_values_are_rejected():
    field_payload = _payload()
    field_payload["api_key"] = "not-allowed"
    with pytest.raises(ValueError, match="unknown config field"):
        BatteryForecastConfig.from_mapping(field_payload)

    value_payload = _payload()
    value_payload["source_lineage_path"] = "api" + "_key=fixture-value"
    with pytest.raises(ValueError, match="secret-like value"):
        BatteryForecastConfig.from_mapping(value_payload)


def test_model_and_split_allowlists_reject_unregistered_execution():
    model_payload = _payload()
    model_payload["models"] = ["persistence", "xgboost"]
    with pytest.raises(ValueError, match="fixed ordered baselines"):
        BatteryForecastConfig.from_mapping(model_payload)

    split_payload = _payload()
    split_payload["split_method"] = "random_row"
    with pytest.raises(ValueError, match="group_kfold"):
        BatteryForecastConfig.from_mapping(split_payload)


def test_resolver_rejects_paths_outside_repository(tmp_path):
    with pytest.raises(ValueError, match="repository-relative"):
        resolve_repo_path(tmp_path, "C:/outside/result.json")
    with pytest.raises(ValueError, match="non-traversing"):
        resolve_repo_path(tmp_path, "../outside/result.json")


def test_module_has_no_network_dynamic_execution_or_pickle():
    text = Path("src/platform_core/battery_forecasting.py").read_text(
        encoding="utf-8"
    )

    assert "import requests" not in text
    assert "import urllib" not in text
    assert "import socket" not in text
    assert "import subprocess" not in text
    assert "import importlib" not in text
    assert "pickle" not in text
    assert "eval(" not in text
    assert "exec(" not in text
    assert "center=True" not in text
    assert "train_test_split" not in text
    assert "ShuffleSplit" not in text
    assert '"random_row_split_used": False' in text
