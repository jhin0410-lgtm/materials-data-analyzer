"""Tests for Smart Factory v1.4.4 classification specification."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "smart_factory"
    / "classification_spec_v1_4.json"
)
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_smart_factory_v1_4_classification.py"
GITIGNORE_PATH = PROJECT_ROOT / ".gitignore"


def _load_spec() -> dict:
    with SPEC_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("smart_factory_v14_classification", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_classification_spec_records_validation_hierarchy_and_non_goals() -> None:
    spec = _load_spec()

    assert spec["case_study_version"] == "v1.4.4"
    assert "chronological blocked splits" in spec["validation_hierarchy"]["primary"]
    assert "stratified random split" in spec["validation_hierarchy"]["secondary_reference"]
    assert spec["validation_hierarchy"]["group_validation"].startswith("not_ready")
    assert "SHAP-based physical interpretation" in spec["prohibited_claims"]
    assert "SMOTE_or_synthetic_oversampling" in spec["preprocessing_policy"]["prohibited"]


def test_model_configurations_are_fixed_classical_baselines() -> None:
    spec = _load_spec()
    names = [item["name"] for item in spec["model_configurations"]]

    assert names == [
        "dummy_prior",
        "logistic_regression_balanced",
        "random_forest_balanced",
        "hist_gradient_boosting_balanced",
    ]
    assert spec["metrics"]["primary"] == "average_precision"
    assert spec["threshold_policy"]["test_label_threshold_tuning"] is False


def test_local_prediction_output_is_not_a_tracked_output() -> None:
    spec = _load_spec()
    gitignore = GITIGNORE_PATH.read_text(encoding="utf-8")

    assert "classification_predictions" in spec["local_output_paths"]
    assert "classification_predictions" not in spec["tracked_output_paths"]
    assert "smart_factory_v1_4_classification_predictions.csv" in gitignore


def test_classification_script_does_not_import_network_clients() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "urllib" not in source
    assert "requests" not in source
    assert "httpx" not in source
    assert "socket" not in source


def test_output_path_contract_is_relative_and_credential_free() -> None:
    spec = _load_spec()
    paths = list(spec["local_output_paths"].values()) + list(spec["tracked_output_paths"].values())

    for path in paths:
        assert not Path(path).is_absolute()
        assert "credential" not in path.lower()
        assert "token" not in path.lower()


def test_script_output_path_mapping_matches_spec() -> None:
    module = _load_script_module()
    paths = module._output_paths(_load_spec())

    assert paths["predictions_path"].endswith("classification_predictions.csv")
    assert paths["metrics_path"].endswith("classification_metrics.csv")
    assert paths["conclusion_path"].endswith("classification_conclusion.csv")
