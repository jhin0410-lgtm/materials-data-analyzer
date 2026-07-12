"""Tests for Reliability v1.5 contract-stage artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = PROJECT_ROOT / "data" / "case_studies" / "reliability"
CONTRACT_PATH = CASE_DIR / "reliability_contract_v1_5.json"
LEAKAGE_PATH = CASE_DIR / "leakage_map_v1_5.csv"
CANDIDATES_PATH = CASE_DIR / "dataset_candidates_v1_5.csv"
PLAN_PATH = PROJECT_ROOT / "docs" / "RELIABILITY_V1_5_PLAN.md"
README_PATH = CASE_DIR / "README.md"
READINESS_MODULE_PATH = PROJECT_ROOT / "src" / "analyzers" / "reliability_readiness.py"


ALLOWED_REQUIREMENTS = {"required", "preferred", "optional", "unavailable"}
REQUIRED_LEAKAGE_PATTERNS = {
    "post_failure_measurements",
    "maintenance_action_after_diagnosis",
    "replacement_indicator",
    "final_cycle_count",
    "future_degradation_windows",
    "full_lifetime_normalization",
    "asset_maximum_cycle",
    "target_derived_health_index",
    "test_asset_statistics_in_preprocessing",
    "random_row_split_mixing_same_asset",
    "future_observation_in_rolling_features",
    "failure_code_after_teardown",
    "censoring_timestamp_as_feature",
    "remaining_useful_life_label",
    "survivor_only_selection",
    "repaired_asset_history_crossing_origin",
    "duplicated_trajectories",
    "operating_regime_hidden_asset_identity",
    "globally_fitted_smoothing",
    "future_sample_interpolation",
}


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_reliability_contract_json_parses_and_declares_contract_stage() -> None:
    contract = _contract()

    assert contract["schema_version"] == "1.0"
    assert contract["case_study_version"] == "v1.5.1-contract-stage"
    assert contract["status"] == "contract_stage"
    assert contract["primary_task"]["name"] == "future_failure_risk_or_time_to_event_readiness"
    assert "production-ready maintenance schedule" in contract["prohibited_claims"]


def test_reliability_contract_field_requirements_are_explicit() -> None:
    contract = _contract()
    fields = contract["fields"]

    required_fields = {
        "asset_id",
        "component_id",
        "fleet_id",
        "operating_regime",
        "observation_timestamp",
        "observation_cycle",
        "prediction_origin",
        "prediction_horizon",
        "event_timestamp",
        "event_indicator",
        "censoring_type",
        "censoring_timestamp",
        "failure_mode",
        "maintenance_timestamp",
        "maintenance_type",
        "repair_replacement_policy",
    }
    assert required_fields.issubset(fields)
    for name, spec in fields.items():
        assert spec["requirement"] in ALLOWED_REQUIREMENTS, name


def test_contract_defines_validation_metrics_and_trust_vocabulary() -> None:
    contract = _contract()

    assert "asset_disjoint_validation" in contract["validation_hierarchy"]["primary"]
    assert "combined_asset_disjoint_future_validation" in contract["validation_hierarchy"]["primary"]
    assert "PR-AUC" in contract["metrics_contract"]["binary_horizon_risk"]
    assert "concordance index" in contract["metrics_contract"]["survival"]
    assert contract["model_status_vocabulary"] == [
        "descriptive_only",
        "diagnostic_only",
        "limited_predictive_evidence",
        "candidate_for_further_validation",
    ]
    assert "production_ready" not in json.dumps(contract)


def test_leakage_map_has_required_columns_and_patterns() -> None:
    leakage = pd.read_csv(LEAKAGE_PATH)

    assert leakage.columns.tolist() == [
        "field_or_pattern",
        "leakage_type",
        "availability_time",
        "risk_level",
        "allowed_as_feature",
        "allowed_as_metadata",
        "mitigation",
        "validation_test",
    ]
    assert REQUIRED_LEAKAGE_PATTERNS.issubset(set(leakage["field_or_pattern"]))


def test_high_risk_leakage_rows_are_not_allowed_as_features() -> None:
    leakage = pd.read_csv(LEAKAGE_PATH)
    high_risk = leakage[leakage["risk_level"] == "high"]

    assert not high_risk.empty
    assert set(high_risk["allowed_as_feature"].astype(str).str.lower()) == {"false"}


def test_dataset_candidate_assessment_has_minimum_public_candidates() -> None:
    candidates = pd.read_csv(CANDIDATES_PATH)

    assert len(candidates) >= 6
    assert candidates["dataset_id"].is_unique
    statuses = set(candidates["status"])
    assert "conditional_primary_candidate" in statuses
    assert "operational_backup_candidate" in statuses
    assert "secondary_fixture" in statuses
    assert "rejected" in statuses
    primary = candidates.set_index("dataset_id").loc["backblaze_drive_stats"]
    assert primary["status"] == "conditional_primary_candidate"
    assert "asset" in primary["decision_rationale"].lower()


def test_candidate_assessment_keeps_uncertain_facts_explicit() -> None:
    candidates = pd.read_csv(CANDIDATES_PATH)

    uncertain = candidates["uncertain_facts"].fillna("").str.lower()
    assert uncertain.str.contains("verify|verification|unclear|terms").any()
    assert "real operational" in set(candidates["real_vs_synthetic"])
    assert "synthetic simulation benchmark" in set(candidates["real_vs_synthetic"])


def test_docs_mark_v1_5_as_contract_stage_not_completed_case_study() -> None:
    plan = PLAN_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")

    assert "Status: `contract_stage`" in plan
    assert "Status: `contract_stage`" in readme
    assert "tracked repository does not contain raw downloads" in plan.lower()
    assert "does not contain downloaded raw data" in readme
    assert "Backblaze" in plan
    assert "NASA C-MAPSS" in plan


def test_reliability_artifacts_contain_no_credentials_or_absolute_paths() -> None:
    for path in [CONTRACT_PATH, LEAKAGE_PATH, CANDIDATES_PATH, PLAN_PATH, README_PATH]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"[A-Za-z]:\\\\", text)
        assert "/Users/" not in text
        assert "/home/" not in text
        assert "KAGGLE_KEY=" not in text
        assert "KAGGLE_USERNAME=" not in text
        assert "password=" not in text.lower()
        assert "secret=" not in text.lower()


def test_readiness_module_does_not_import_network_or_modeling_clients() -> None:
    source = READINESS_MODULE_PATH.read_text(encoding="utf-8")

    forbidden = [
        "import requests",
        "from requests",
        "import urllib",
        "from urllib",
        "import httpx",
        "from httpx",
        "import socket",
        "sklearn",
        "lifelines",
        "sksurv",
        "xgboost",
    ]
    for text in forbidden:
        assert text not in source
