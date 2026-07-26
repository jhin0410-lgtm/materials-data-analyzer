from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.platform_core import battery_external_cohort_next_source_selection_gate as mod


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _inputs():
    config = mod.load_config()
    contract = _load(mod.DEFAULT_CONTRACT_PATH)
    register = _load(mod.DEFAULT_REGISTER_PATH)
    v264 = _load(mod.DEFAULT_V264_PATH)
    v2610 = _load(mod.DEFAULT_V2610_PATH)
    return config, contract, register, v264, v2610


def test_preview_selects_only_michigan_formation():
    config = mod.load_config()
    preview = mod.preview(config)
    assert preview["candidate_count"] == 9
    assert preview["selected_candidates"] == ["Michigan Formation.zip"]
    assert preview["network_access"] is False
    assert preview["raw_dataset_download"] is False
    assert preview["local_archive_payload_read"] is False
    assert preview["model_execution"] is False


def test_build_result_preserves_admission_boundaries():
    config, contract, register, v264, v2610 = _inputs()
    result = mod.build_result(config, contract, register, v264, v2610)
    mod.validate_result(result)
    decision = result["selection_decision"]
    assert decision["selection_status"] == "selected_for_bounded_source_binding_only"
    assert decision["local_archive_to_official_dataset_binding"] == "not_established"
    assert decision["provider_package_to_cycle_row_binding"] == "not_established"
    assert decision["cross_cohort_comparability"] == "not_admitted"
    assert decision["predictive_validation"] == "blocked"
    assert decision["raw_dataset_download"] == "not_authorized"
    assert decision["local_archive_payload_read"] == "not_authorized"


def test_candidate_summary_and_dispositions_are_exact():
    config, contract, register, v264, v2610 = _inputs()
    result = mod.build_result(config, contract, register, v264, v2610)
    assert result["candidate_summary"] == {
        "candidate_count": 9,
        "selected_count": 1,
        "reserve_count": 1,
        "closed_count": 1,
        "hold_count": 6,
        "hard_gate_pass_count": 1,
    }
    dispositions = {
        item["archive_name"]: item["disposition"]
        for item in result["candidate_assessments"]
    }
    assert dispositions["Michigan Formation.zip"] == (
        "selected_for_bounded_source_binding_only"
    )
    assert dispositions["Oxford.zip"] == "reserve_versioned_source_no_command_artifact"
    assert dispositions["SNL LFP.zip"] == "closed_diagnostic_no_incremental_payload"


def test_only_selected_candidate_passes_hard_gate():
    config, contract, register, v264, v2610 = _inputs()
    result = mod.build_result(config, contract, register, v264, v2610)
    selected = [
        item["archive_name"]
        for item in result["candidate_assessments"]
        if item["hard_gate_passed"]
    ]
    assert selected == ["Michigan Formation.zip"]


def test_michigan_formation_evidence_is_source_package_only():
    config, contract, register, v264, v2610 = _inputs()
    result = mod.build_result(config, contract, register, v264, v2610)
    item = next(
        value
        for value in result["candidate_assessments"]
        if value["archive_name"] == "Michigan Formation.zip"
    )
    assert item["dataset_doi"] == "10.7302/pa3f-4w30"
    assert item["stable_dataset_record"] is True
    assert item["detailed_readme_declared"] is True
    assert item["raw_cycler_data_declared"] is True
    assert item["cell_tracker_declared"] is True
    assert item["test_schedule_declared"] is True
    assert item["source_code_declared"] is True
    assert item["local_to_source_binding"] == (
        "source_family_match_only_exact_file_binding_pending"
    )


def test_snl_line_remains_closed():
    config, contract, register, v264, v2610 = _inputs()
    result = mod.build_result(config, contract, register, v264, v2610)
    assert result["upstream_checks"]["snl_lfp_evidence_line"] == (
        "closed_at_diagnostic_boundary"
    )
    assert result["selection_decision"]["selected_archive"] != "SNL LFP.zip"


def test_no_prohibited_operation_flags():
    config, contract, register, v264, v2610 = _inputs()
    result = mod.compact(
        mod.build_result(config, contract, register, v264, v2610)
    )
    for flag in mod.FALSE_FLAGS:
        assert result[flag] is False


def test_register_mutation_is_rejected():
    _, _, register, _, _ = _inputs()
    mutated = copy.deepcopy(register)
    selected = next(
        item for item in mutated["candidates"]
        if item["archive_name"] == "Michigan Formation.zip"
    )
    selected["official_source_record"]["test_schedule_declared"] = False
    with pytest.raises(ValueError, match="register checksum"):
        mod.validate_register(mutated)


def test_contract_selection_mutation_is_rejected():
    _, contract, _, _, _ = _inputs()
    mutated = copy.deepcopy(contract)
    mutated["selection_policy"]["selected_archive"] = "Oxford.zip"
    with pytest.raises(ValueError, match="selected archive"):
        mod.validate_contract(mutated)


def test_upstream_admission_mutation_is_rejected():
    _, _, _, v264, v2610 = _inputs()
    mutated = copy.deepcopy(v264)
    mutated["admission_decision"]["overall_status"] = "admitted"
    with pytest.raises(ValueError):
        mod.verify_upstream(mutated, v2610)


def test_result_promotion_is_rejected():
    config, contract, register, v264, v2610 = _inputs()
    result = mod.compact(
        mod.build_result(config, contract, register, v264, v2610)
    )
    result["selection_decision"]["cross_cohort_comparability"] = "admitted"
    result["deterministic_result_checksum"] = mod.canonical_checksum(result)
    with pytest.raises(ValueError, match="cross_cohort_comparability"):
        mod.validate_result(result)


def test_config_path_escape_is_rejected(tmp_path: Path):
    payload = _load(mod.DEFAULT_CONFIG_PATH)
    payload["candidate_register_path"] = "../candidate-register.json"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="repository-relative"):
        mod.load_config(path.name, tmp_path)


def test_v2_6_11_json_artifacts_parse():
    for path in (
        Path("data/platform/battery_next_source_selection_config_schema_v1.json"),
        Path("data/platform/battery_external_cohort_source_candidate_register_schema_v1.json"),
        Path("data/platform/battery_external_cohort_next_source_selection_contract_schema_v1.json"),
        Path("data/platform/battery_external_cohort_next_source_selection_result_schema_v1.json"),
        Path(mod.DEFAULT_REGISTER_PATH),
        Path(mod.DEFAULT_CONTRACT_PATH),
        Path(mod.DEFAULT_TRACKED_SUMMARY),
    ):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
