"""Tests for Materials Project v1.3 acquisition/modeling contracts."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "inspect_materials_project_v1_3_readiness.py"
ACQUISITION_SPEC_PATH = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "materials_project"
    / "acquisition_spec_v1_3.json"
)
MODELING_CONTRACT_PATH = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "materials_project"
    / "modeling_contract_v1_3.json"
)


def _load_readiness_module():
    spec = importlib.util.spec_from_file_location("mp_v13_readiness", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_acquisition_spec_validates() -> None:
    module = _load_readiness_module()

    module.validate_acquisition_spec(_load_json(ACQUISITION_SPEC_PATH))


def test_modeling_contract_validates() -> None:
    module = _load_readiness_module()

    module.validate_modeling_contract(_load_json(MODELING_CONTRACT_PATH))


def test_acquisition_spec_rejects_duplicate_fields() -> None:
    module = _load_readiness_module()
    spec = _load_json(ACQUISITION_SPEC_PATH)
    spec["requested_fields"] = ["material_id", "material_id"]

    with pytest.raises(ValueError, match="duplicates"):
        module.validate_acquisition_spec(spec)


def test_acquisition_spec_rejects_target_filter_policy() -> None:
    module = _load_readiness_module()
    spec = _load_json(ACQUISITION_SPEC_PATH)
    spec["query_parameters"]["energy_above_hull"] = [0.0, 0.1]

    with pytest.raises(ValueError, match="energy_above_hull"):
        module.validate_acquisition_spec(spec)


def test_acquisition_spec_rejects_is_stable_filter_policy() -> None:
    module = _load_readiness_module()
    spec = _load_json(ACQUISITION_SPEC_PATH)
    spec["query_parameters"]["is_stable"] = True

    with pytest.raises(ValueError, match="is_stable"):
        module.validate_acquisition_spec(spec)


def test_modeling_contract_forbids_identifier_and_target_features() -> None:
    module = _load_readiness_module()
    contract = _load_json(MODELING_CONTRACT_PATH)

    assert "material_id" in contract["forbidden_features"]
    assert "energy_above_hull" in contract["forbidden_features"]
    assert "is_stable" in contract["forbidden_features"]

    bad_contract = copy.deepcopy(contract)
    bad_contract["primary_feature_tier"]["source_fields"].append("energy_above_hull")
    with pytest.raises(ValueError, match="target/leakage"):
        module.validate_modeling_contract(bad_contract)


def test_contracts_reject_secret_like_keys_and_absolute_paths() -> None:
    module = _load_readiness_module()
    acquisition = _load_json(ACQUISITION_SPEC_PATH)
    acquisition["api_key"] = "do-not-store"
    with pytest.raises(ValueError, match="secret"):
        module.validate_acquisition_spec(acquisition)

    modeling = _load_json(MODELING_CONTRACT_PATH)
    modeling["notes"] = ["C:\\private\\materials_project.csv"]
    with pytest.raises(ValueError, match="absolute"):
        module.validate_modeling_contract(modeling)


def test_modeling_contract_contains_required_split_strategies_and_metrics() -> None:
    contract = _load_json(MODELING_CONTRACT_PATH)
    split_names = {split["name"] for split in contract["split_strategies"]}

    assert {
        "deterministic_random_split",
        "reduced_formula_group_split",
        "chemical_system_group_split",
    }.issubset(split_names)
    assert {"MAE", "RMSE", "R2", "Spearman rank correlation"}.issubset(
        set(contract["metrics"])
    )


def test_readiness_report_contains_provenance_capture_fields_without_network() -> None:
    module = _load_readiness_module()
    acquisition = _load_json(ACQUISITION_SPEC_PATH)
    modeling = _load_json(MODELING_CONTRACT_PATH)
    inspection = module.inspect_installed_api_contract()
    report = module.build_readiness_report(acquisition, modeling, inspection)

    assert report["network_called"] is False
    assert report["api_key_read"] is False
    assert "acquisition_utc_timestamp" in report["provenance_capture_required_fields"]
    assert "materials_project_database_version" in report["provenance_capture_required_fields"]
    assert "duplicate_material_id_count" in report["provenance_capture_required_fields"]


def test_readiness_cli_outputs_sanitized_json_without_network() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/inspect_materials_project_v1_3_readiness.py",
            "--acquisition-spec",
            str(ACQUISITION_SPEC_PATH.relative_to(PROJECT_ROOT)),
            "--modeling-contract",
            str(MODELING_CONTRACT_PATH.relative_to(PROJECT_ROOT)),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)

    assert report["network_called"] is False
    assert report["api_key_read"] is False
    assert "requested_fields" in report
    assert "MP_API_KEY" not in result.stdout
    assert "C:\\Users" not in result.stdout


def test_json_loading_is_deterministic() -> None:
    first = _load_json(ACQUISITION_SPEC_PATH)
    second = _load_json(ACQUISITION_SPEC_PATH)

    assert first == second
