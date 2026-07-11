"""Tests for Smart Factory v1.4 contract-stage artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "smart_factory"
    / "process_quality_contract_v1_4.json"
)
LEAKAGE_MAP_PATH = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "smart_factory"
    / "leakage_map_v1_4.csv"
)
PLAN_PATH = PROJECT_ROOT / "docs" / "SMART_FACTORY_V1_4_PLAN.md"
READINESS_MODULE_PATH = (
    PROJECT_ROOT / "src" / "analyzers" / "process_quality_readiness.py"
)

ALLOWED_STATUSES = {"required", "preferred", "optional", "unavailable"}
REQUIRED_LEAKAGE_TYPES = {
    "quality result measured after production",
    "rework/inspection outcome",
    "final disposition",
    "defect code generated after inspection",
    "downstream equipment signal",
    "future sensor windows",
    "lot-level aggregate using test rows",
    "target encoding across groups",
    "random split mixing same lot",
    "random split mixing adjacent time windows",
    "equipment maintenance event known only afterward",
    "manually assigned troubleshooting labels",
    "duplicated product measurements",
    "recipe or product identity acting as hidden target proxy",
}


def _load_contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_process_quality_contract_json_parses_and_contains_required_sections() -> None:
    contract = _load_contract()

    assert contract["schema_version"] == "1.0"
    assert contract["case_study_version"] == "v1.4.1-contract-stage"
    assert "business_question" in contract
    assert "fields" in contract
    assert "policies" in contract
    assert "stop_conditions" in contract


def test_process_quality_contract_field_statuses_are_explicit() -> None:
    contract = _load_contract()

    fields = contract["fields"]
    assert isinstance(fields, dict)
    required_field_names = {
        "unit_of_analysis",
        "prediction_horizon",
        "observation_timestamp",
        "quality_measurement_timestamp",
        "equipment_id",
        "line_id",
        "lot_id",
        "batch_id",
        "product_id",
        "recipe_id",
        "operator_id",
    }
    assert required_field_names.issubset(fields)
    for field_name, field_contract in fields.items():
        assert field_contract["status"] in ALLOWED_STATUSES, field_name


def test_contract_policies_and_feature_families_have_valid_statuses() -> None:
    contract = _load_contract()

    for policy_name, policy in contract["policies"].items():
        assert policy["status"] in ALLOWED_STATUSES, policy_name
    for family in contract["process_feature_families"]:
        assert family["status"] in ALLOWED_STATUSES, family["name"]
    for family in contract["quality_target_families"]:
        assert family["status"] in ALLOWED_STATUSES, family["name"]
    for target_name, target in contract["defect_yield_target_definitions"].items():
        assert target["status"] in ALLOWED_STATUSES, target_name


def test_contract_contains_no_credentials_or_absolute_local_paths() -> None:
    text = CONTRACT_PATH.read_text(encoding="utf-8")

    assert "api_key" not in text.lower()
    assert "secret" not in text.lower()
    assert "token" not in text.lower()
    assert not re.search(r"[A-Za-z]:\\\\", text)
    assert "/Users/" not in text
    assert "/home/" not in text


def test_leakage_map_csv_parses_with_required_columns_and_leakage_types() -> None:
    leakage = pd.read_csv(LEAKAGE_MAP_PATH)

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
    assert REQUIRED_LEAKAGE_TYPES.issubset(set(leakage["leakage_type"]))


def test_high_risk_leakage_rows_are_not_allowed_as_features() -> None:
    leakage = pd.read_csv(LEAKAGE_MAP_PATH)
    high_risk = leakage[leakage["risk_level"] == "high"]

    assert not high_risk.empty
    assert set(high_risk["allowed_as_feature"].astype(str).str.lower()) == {"false"}


def test_plan_marks_v1_4_as_active_case_study_with_claim_limits() -> None:
    text = PLAN_PATH.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "Status: active case-study track through v1.4.4." in text
    assert "fixed classical time-aware classification baselines" in text
    assert "stratified random split as an optimistic reference only" in text
    assert "no representative production model is selected" in normalized


def test_readiness_module_does_not_import_network_clients() -> None:
    source = READINESS_MODULE_PATH.read_text(encoding="utf-8")

    forbidden_imports = [
        "import requests",
        "from requests",
        "import urllib",
        "from urllib",
        "import httpx",
        "from httpx",
        "import socket",
    ]
    for forbidden in forbidden_imports:
        assert forbidden not in source
