from __future__ import annotations

import json
from pathlib import Path

from src.platform_core import battery_snl_lfp_bounded_schema_read as mod


EXPECTED_TRACKED_CHECKSUM = (
    "28c68acecdce55787189ddd981c097d1748504dab43b3777b896638652fb70f2"
)


def test_tracked_local_schema_observation_is_valid_and_checksum_locked():
    tracked_path = Path(mod.DEFAULT_TRACKED_SUMMARY)
    tracked_text = tracked_path.read_text(encoding="utf-8")
    payload = json.loads(tracked_text)

    expected_text = json.dumps(
        payload,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    ) + "\n"
    assert tracked_text == expected_text

    mod.validate_result(payload)
    assert payload["deterministic_result_checksum"] == EXPECTED_TRACKED_CHECKSUM
    assert payload["archive_audit"]["status"] == "verified"
    assert payload["representative_read_summary"] == {
        "declared_entry_count": 6,
        "header_count": 6,
        "max_data_rows_per_entry": 5,
        "max_line_bytes": 65536,
        "opened_entries": [
            "SNL LFP/SNL_18650_LFP_25C_0-100_0.5-1C_a_cycle_data.csv",
            "SNL LFP/SNL_18650_LFP_25C_0-100_0.5-1C_a_timeseries.csv",
            "SNL LFP/SNL_18650_LFP_25C_20-80_0.5-0.5C_a_cycle_data.csv",
            "SNL LFP/SNL_18650_LFP_25C_20-80_0.5-0.5C_a_timeseries.csv",
            "SNL LFP/SNL_18650_LFP_25C_40-60_0.5-0.5C_a_cycle_data.csv",
            "SNL LFP/SNL_18650_LFP_25C_40-60_0.5-0.5C_a_timeseries.csv",
        ],
        "opened_entry_count": 6,
        "sample_data_row_count": 30,
        "schema_contract_match_count": 6,
        "schema_contract_mismatch_count": 0,
        "status": "bounded_schema_observed",
    }
    assert payload["schema_read_decision"] == {
        "bounded_schema_observation": "bounded_schema_observed",
        "capacity_check_vs_bulk_cycle_discrimination": (
            "header_and_first_rows_insufficient"
        ),
        "cross_cohort_comparability": "not_admitted",
        "cycle_command_to_rows": "not_established",
        "instrument_channel_to_columns": "not_established",
        "official_distribution_snapshot": "not_established",
        "overall_status": "bounded_schema_observed_gate_not_passed",
        "physical_cell_to_entry": "not_established",
        "predictive_validation": "blocked",
    }
    assert payload["scientific_closeout"]["status"] == "diagnostic"
    assert payload["raw_sample_values_retained"] is False if "raw_sample_values_retained" in payload else True
    assert all(
        observation["raw_sample_values_retained"] is False
        and observation["full_file_read"] is False
        and observation["row_width_contract_match"] is True
        and observation["sample_data_rows_read"] == 5
        for observation in payload["file_observations"]
    )


def test_v2_6_8_json_artifacts_parse():
    for path in (
        Path("data/platform/battery_bounded_schema_read_config_schema_v1.json"),
        Path("data/platform/battery_bounded_schema_read_contract_schema_v1.json"),
        Path("data/platform/battery_bounded_schema_read_result_schema_v1.json"),
        Path(mod.DEFAULT_CONTRACT_PATH),
        Path(mod.DEFAULT_TRACKED_SUMMARY),
    ):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
