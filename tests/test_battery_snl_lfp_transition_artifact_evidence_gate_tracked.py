from __future__ import annotations

import json
from pathlib import Path

from src.platform_core import battery_snl_lfp_transition_artifact_evidence_gate as mod


def test_v2_6_10_json_artifacts_parse():
    for path in (
        Path("data/platform/battery_transition_artifact_evidence_config_schema_v1.json"),
        Path("data/platform/battery_transition_artifact_evidence_contract_schema_v1.json"),
        Path("data/platform/battery_transition_artifact_evidence_result_schema_v1.json"),
        Path(mod.DEFAULT_CONTRACT_PATH),
        Path(mod.DEFAULT_TRACKED_SUMMARY),
    ):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


def test_tracked_evidence_preserves_source_and_scientific_boundaries():
    payload = json.loads(
        Path(mod.DEFAULT_TRACKED_SUMMARY).read_text(encoding="utf-8")
    )
    mod.validate_result(payload)
    assert payload["source_evidence_audit"]["document_id"] == (
        "battery_archive_snl_study_page"
    )
    assert payload["source_evidence_audit"]["documented_transition_artifact"] is True
    assert payload["source_evidence_audit"]["exact_csv_row_binding_established"] is False
    assert payload["scientific_closeout"]["status"] == "diagnostic"
    assert payload["transition_artifact_decision"]["overall_status"] == (
        "transition_artifact_consistency_recorded_gate_not_passed"
    )
