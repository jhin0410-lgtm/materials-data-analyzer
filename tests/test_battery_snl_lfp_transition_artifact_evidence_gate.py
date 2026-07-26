from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.platform_core import battery_snl_lfp_transition_artifact_evidence_gate as mod


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_config_and_contract_are_strict():
    config = mod.load_config()
    contract = _load(config["contract_path"])
    mod.validate_contract(contract, config)
    assert config["v2_6_5_source_evidence_summary_path"] == mod.V265_SUMMARY_PATH
    assert config["v2_6_9_cycle_regime_summary_path"] == mod.V269_SUMMARY_PATH


def test_build_result_matches_tracked_summary():
    config = mod.load_config()
    contract = _load(config["contract_path"])
    v265 = _load(config["v2_6_5_source_evidence_summary_path"])
    v269 = _load(config["v2_6_9_cycle_regime_summary_path"])
    generated = mod.compact(mod.build_result(config, contract, v265, v269))
    mod.validate_result(generated)
    assert _load(mod.DEFAULT_TRACKED_SUMMARY) == generated


def test_reviewed_checksum_is_locked():
    tracked = _load(mod.DEFAULT_TRACKED_SUMMARY)
    assert tracked["deterministic_result_checksum"] == (
        "0093de000c25cfcbbd36eaf8216eabc7fb3bc3db23b724dbffcb69b4d77ddf28"
    )
    mod.validate_result(tracked)


def test_all_representatives_have_row4_transition_contrast():
    summary = _load(mod.DEFAULT_TRACKED_SUMMARY)["transition_summary"]
    assert summary["representative_entry_count"] == 3
    assert summary["row4_contrast_observed_count"] == 3
    assert summary["all_representatives_have_row4_contrast"] is True
    assert summary["common_outside_range_fields"] == [
        "charge_capacity_ah",
        "discharge_capacity_ah",
    ]


def test_condition_specific_row4_fields_are_preserved():
    tracked = _load(mod.DEFAULT_TRACKED_SUMMARY)
    audits = {
        item["entry_name"]: item["outside_range_fields"]
        for item in tracked["row4_transition_audits"]
    }
    assert audits[mod.REPRESENTATIVE_ENTRIES[0]] == [
        "charge_capacity_ah",
        "discharge_capacity_ah",
    ]
    assert audits[mod.REPRESENTATIVE_ENTRIES[1]] == [
        "min_voltage_v",
        "max_voltage_v",
        "charge_capacity_ah",
        "discharge_capacity_ah",
    ]
    assert audits[mod.REPRESENTATIVE_ENTRIES[2]] == [
        "min_voltage_v",
        "max_voltage_v",
        "charge_capacity_ah",
        "discharge_capacity_ah",
    ]


def test_transition_consistency_is_not_row_binding():
    decision = _load(mod.DEFAULT_TRACKED_SUMMARY)["transition_artifact_decision"]
    assert decision["row4_to_source_transition_binding"] == (
        "transition_consistent_not_row_bound"
    )
    assert decision["row4_exact_identity"] == "not_established"
    assert decision["capacity_check_vs_bulk_cycle_discrimination"] == (
        "candidate_supported_not_established"
    )
    assert decision["time_series_read_gate"] == (
        "not_authorized_no_provider_step_or_command_binding"
    )


def test_no_threshold_model_or_new_payload_read():
    tracked = _load(mod.DEFAULT_TRACKED_SUMMARY)
    for flag in mod.FALSE_FLAGS:
        assert tracked[flag] is False
    assert tracked["transition_summary"]["universal_numeric_threshold_defined"] is False
    assert (
        tracked["transition_summary"][
            "positions_4_to_8_homogeneous_bulk_regime_established"
        ]
        is False
    )


def test_preview_is_tracked_only():
    config = mod.load_config()
    preview = mod.preview(config)
    assert preview["write_outputs"] is False
    assert preview["row4_position"] == 4
    assert preview["comparison_positions"] == [5, 6, 7, 8]
    assert "raw archive bytes" in preview["prohibited_reads"]
    assert "time-series entries" in preview["prohibited_reads"]


def test_v2_6_9_mutation_is_rejected():
    config = mod.load_config()
    contract = _load(config["contract_path"])
    v265 = _load(config["v2_6_5_source_evidence_summary_path"])
    v269 = _load(config["v2_6_9_cycle_regime_summary_path"])
    mutated = copy.deepcopy(v269)
    mutated["cycle_regime_decision"]["row4_exact_identity"] = "established"
    with pytest.raises(ValueError, match="content checksum mismatch"):
        mod.build_result(config, contract, v265, mutated)


def test_contract_cannot_promote_row_identity():
    config = mod.load_config()
    contract = _load(config["contract_path"])
    mutated = copy.deepcopy(contract)
    mutated["claim_policy"]["row4_is_confirmed_transition_record"] = True
    with pytest.raises(ValueError, match="claim policy"):
        mod.validate_contract(mutated, config)


def test_contract_cannot_authorize_time_series():
    config = mod.load_config()
    contract = _load(config["contract_path"])
    mutated = copy.deepcopy(contract)
    mutated["decision_policy"]["time_series_read_may_be_authorized"] = True
    with pytest.raises(ValueError, match="decision policy"):
        mod.validate_contract(mutated, config)


def test_source_contains_no_external_or_model_dependencies():
    source = Path(mod.__file__).read_text(encoding="utf-8")
    for prohibited in (
        "requests", "urllib", "pandas", "numpy", "sklearn",
        "tensorflow", "torch", "zipfile",
    ):
        assert f"import {prohibited}" not in source
        assert f"from {prohibited}" not in source
