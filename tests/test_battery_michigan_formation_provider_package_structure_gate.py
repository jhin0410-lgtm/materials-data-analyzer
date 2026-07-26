from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.platform_core import (
    battery_michigan_formation_provider_package_structure_gate as mod,
)


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_config_contract_and_evidence_are_checksum_bound():
    config = mod.load_config()
    evidence = _load(mod.DEFAULT_EVIDENCE_PATH)
    contract = _load(mod.DEFAULT_CONTRACT_PATH)

    mod.validate_evidence(evidence)
    mod.validate_contract(contract)

    assert config["execution_policy"] == {
        "network_access": False,
        "provider_dataset_download": False,
        "provider_file_payload_read": False,
        "local_archive_read": False,
        "local_csv_payload_read": False,
        "filename_inference": False,
        "command_inference": False,
        "cohort_merge": False,
        "model_execution": False,
        "metric_recomputation": False,
    }
    assert mod.canonical_checksum(evidence) == mod.EXPECTED_EVIDENCE_CHECKSUM
    assert mod.canonical_checksum(contract) == mod.EXPECTED_CONTRACT_CHECKSUM


def test_gate_recovers_structure_without_promoting_manifest_or_binding():
    config = mod.load_config()
    result = mod.execute(config, write_outputs=False)

    assert result["provider_dataset_identity"]["dataset_doi"] == "10.7302/pa3f-4w30"
    assert result["provider_dataset_identity"]["file_set_count"] == 2
    assert result["provider_package_structure"]["declared_folders"] == [
        "code", "data", "documents", "output"
    ]
    assert result["provider_package_structure"]["cell_tracker_files_declared"] is True
    assert result["provider_package_structure"]["test_schedule_files_declared"] is True

    manifest = result["exact_manifest_status"]
    assert manifest["status"] == "not_established"
    assert manifest["file_set_identifiers_recovered"] is False
    assert manifest["file_set_checksums_recovered"] is False
    assert manifest["internal_filenames_recovered"] is False
    assert manifest["cell_tracker_schema_recovered"] is False
    assert manifest["test_schedule_schema_recovered"] is False

    decision = result["decision"]
    assert decision["provider_package_folder_structure"] == "recovered_document_level"
    assert decision["exact_provider_file_manifest"] == "not_established"
    assert decision["local_archive_binding"] == "not_established"
    assert decision["provider_to_standardized_row_binding"] == "not_established"
    assert decision["cross_cohort_comparability"] == "not_admitted"
    assert decision["predictive_validation"] == "blocked"


def test_all_prohibited_execution_and_promotion_flags_remain_false():
    result = mod.execute(mod.load_config(), write_outputs=False)
    for flag in mod.FALSE_FLAGS:
        assert result{flag] is False


def test_provider_evidence_rejects_manifest_promotion():
    evidence = _load(mod.DEFAULT_EVIDENCE_PATH)
    promoted = copy.deepcopy(evidence)
    promoted["manifest_observation"]["file_set_identifiers_recovered"] = True
    with pytest.raises(ValueError):
        mod.validate_evidence(promoted)


def test_provider_evidence_rejects_schedule_schema_promotion():
    evidence = _load(mod.DEFAULT_EVIDENCE_PATH)
    promoted = copy.deepcopy(evidence)
    promoted["manifest_observation"]["test_schedule_schema_recovered"] = True
    with pytest.raises(ValueError):
        mod.validate_evidence(promoted)


def test_contract_rejects_download_or_admission_promotion():
    contract = _load(mod.DEFAULT_CONTRACT_PATH)

    download = copy.deepcopy(contract)
    download["execution_policy"]["provider_dataset_download"] = True
    with pytest.raises(ValueError):
        mod.validate_contract(download)

    admission = copy.deepcopy(contract)
    admission["decision_policy"]["cross_cohort_admission_allowed"] = True
    with pytest.raises(ValueError):
        mod.validate_contract(admission)


def test_upstream_selection_and_non_admission_are_preserved():
    upstream = _load(mod.DEFAULT_V2611_PATH)
    preservation = mod.verify_upstream(upstream)
    assert preservation == {
        "v2_6_11_checksum_verified": True,
        "v2_6_11_selected_archive_preserved": True,
        "v2_6_11_non_admission_preserved": True,
        "model_or_metric_change_performed": False,
    }

    changed = copy.deepcopy(upstream)
    changed["selection_decision"]["selected_archive"] = "Oxford.zip"
    with pytest.raises(ValueError):
        mod.verify_upstream(changed)


def test_repository_relative_path_validation_rejects_escape():
    with pytest.raises(ValueError):
        mod._relative("contract_path", "../contract.json")
    with pytest.raises(ValueError):
        mod._relative("contract_path", "C:/contract.json")
