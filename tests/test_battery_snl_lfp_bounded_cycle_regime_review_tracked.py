from __future__ import annotations

import json
from pathlib import Path

from src.platform_core import battery_snl_lfp_bounded_cycle_regime_review as mod


EXPECTED_TRACKED_CHECKSUM = "dc6c7c4046d81ddf879c2f1538eab75708dd387f7d9d940adc0c6dfc2c3e01dc"


def test_tracked_reviewed_summary_is_valid_and_bounded():
    tracked = json.loads(Path(mod.DEFAULT_TRACKED_SUMMARY).read_text(encoding="utf-8"))

    mod.validate_result(tracked)
    assert tracked["deterministic_result_checksum"] == EXPECTED_TRACKED_CHECKSUM
    assert mod.canonical_checksum(tracked) == EXPECTED_TRACKED_CHECKSUM

    assert tracked["archive_audit"]["status"] == "verified"
    assert tracked["representative_read_summary"]["opened_entry_count"] == 3
    assert tracked["representative_read_summary"]["sample_cycle_row_count"] == 24
    assert tracked["representative_read_summary"]["contract_mismatch_count"] == 0
    assert tracked["cycle_regime_decision"]["capacity_check_vs_bulk_cycle_discrimination"] == (
        "candidate_supported_not_established"
    )
    assert tracked["cycle_regime_decision"]["overall_status"] == (
        "bounded_cycle_regime_evidence_recorded_gate_not_passed"
    )
    assert tracked["scientific_closeout"]["status"] == "diagnostic"

    observations = tracked["file_observations"]
    assert len(observations) == 3
    assert sum(item["sample_data_rows_read"] for item in observations) == 24
    for item in observations:
        assert item["sample_data_rows_read"] == 8
        assert item["sample_row_widths"] == [12] * 8
        assert item["cycle_index_strictly_increasing"] is True
        assert item["candidate_assignment_promoted"] is False
        assert item["full_file_read"] is False
        assert item["selected_measurement_values_retained"] is True
        assert item["selected_values_preserved_as_exact_decimal_strings"] is True
        assert item["cycle_regime_contrast"]["threshold_fitted_or_inferred"] is False
        assert item["cycle_regime_contrast"]["candidate_labels_promoted"] is False
        assert item["cycle_regime_contrast"]["control_non_overlapping_field_count"] >= 1

    assert tracked["time_series_entry_read"] is False
    assert tracked["threshold_inference_performed"] is False
    assert tracked["capacity_check_classification_promoted"] is False
    assert tracked["cycle_command_binding_inferred"] is False
    assert tracked["instrument_channel_binding_inferred"] is False
    assert tracked["cohort_merge_performed"] is False
    assert tracked["model_trained"] is False
    assert tracked["model_evaluated"] is False
    assert tracked["metrics_recomputed"] is False


def test_v2_6_9_json_artifacts_parse():
    for path in (
        Path("data/platform/battery_bounded_cycle_regime_config_schema_v1.json"),
        Path("data/platform/battery_bounded_cycle_regime_contract_schema_v1.json"),
        Path("data/platform/battery_bounded_cycle_regime_result_schema_v1.json"),
        Path(mod.DEFAULT_CONTRACT_PATH),
        Path(mod.DEFAULT_TRACKED_SUMMARY),
    ):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
