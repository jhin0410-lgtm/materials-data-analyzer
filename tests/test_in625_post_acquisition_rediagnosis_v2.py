from __future__ import annotations

import pytest

import materials_data_analyzer.research_loop.in625_post_acquisition_rediagnosis_v2 as module
from materials_data_analyzer.research_loop.in625_post_acquisition_rediagnosis_v2 import (
    In625PostAcquisitionRediagnosisV2Error,
    build_in625_post_acquisition_rediagnosis_v2,
)


def _base() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_id": "zenodo-20503603-in625-lpbf-publication-supplement",
        "archive_sha256": "a" * 64,
        "current_blocker": {
            "code": "cross_source_physical_comparability_not_established",
            "kind": "scientific_comparability",
            "summary": "base",
        },
        "next_action": {
            "action_class": "reviewed_physical_comparability_assessment",
            "execution_mode": "plan_only_until_exact_comparison_contract_exists",
            "required_evidence": ["Exact target material/process-condition identity"],
            "automatic_execution_authorized": False,
        },
        "evidence_state": {
            "real_external_source_acquired": True,
            "real_row_level_measurements_observed": True,
            "replicate_independence_established": False,
        },
        "stop_state": {
            "status": "continue",
            "reason": "base",
            "positive_scientific_closeout": False,
        },
        "scientific_status_changed": False,
        "rediagnosis_sha256": "b" * 64,
    }


def _quality() -> dict[str, object]:
    return {
        "verification_sha256": "c" * 64,
        "measurement_row_count": 200289,
        "complete_numeric_measurement_row_count": 200288,
        "incomplete_numeric_measurement_row_count": 1,
        "isolated_source_missingness_observed": True,
        "known_incomplete_rows": [
            {
                "sheet_name": "AM-AB-H",
                "block_index": 1,
                "excel_row_number": 79,
                "missing_reviewed_numeric_fields": ["load_n"],
                "non_numeric_reviewed_fields": [],
                "raw_anomalous_cell_text": {"load_n": ""},
            }
        ],
    }


def _install(monkeypatch: pytest.MonkeyPatch, *, base=None, quality=None) -> None:
    monkeypatch.setattr(
        module,
        "build_in625_post_acquisition_rediagnosis",
        lambda **_: _base() if base is None else base,
    )
    monkeypatch.setattr(
        module,
        "verify_in625_tensile_observed_quality",
        lambda **_: _quality() if quality is None else quality,
    )


def test_v2_keeps_comparability_primary_and_missingness_secondary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)
    result = build_in625_post_acquisition_rediagnosis_v2(
        network_authorization={},
        network_receipt={},
        typed_execution_result={},
        reviewed_tensile_manifest={},
        quality_contract_path="quality.json",
    )
    assert result["schema_version"] == "2.0"
    assert result["current_blocker"]["code"] == (
        "cross_source_physical_comparability_not_established"
    )
    secondary = result["secondary_blockers"][0]
    assert secondary["code"] == "reviewed_numeric_source_missingness_observed"
    assert secondary["affected_row_count"] == 1
    assert secondary["known_incomplete_rows"][0]["excel_row_number"] == 79
    assert secondary["imputation_authorized"] is False
    assert secondary["row_exclusion_authorized"] is False
    assert result["next_action"]["source_quality_constraint"]["affected_field"] == "load_n"
    assert result["next_action"]["source_quality_constraint"][
        "inverse_reconstruction_authorized"
    ] is False
    assert result["evidence_state"]["complete_numeric_measurement_row_count"] == 200288
    assert result["stop_state"]["positive_scientific_closeout"] is False
    assert result["scientific_status_changed"] is False


def test_v2_rejects_wrong_base_primary_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    base = _base()
    base["current_blocker"] = {"code": "something_else"}
    _install(monkeypatch, base=base)
    with pytest.raises(In625PostAcquisitionRediagnosisV2Error, match="comparability"):
        build_in625_post_acquisition_rediagnosis_v2(
            network_authorization={},
            network_receipt={},
            typed_execution_result={},
            reviewed_tensile_manifest={},
            quality_contract_path="quality.json",
        )


def test_v2_rejects_missing_quality_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    quality = _quality()
    quality.pop("verification_sha256")
    _install(monkeypatch, quality=quality)
    with pytest.raises(In625PostAcquisitionRediagnosisV2Error, match="quality"):
        build_in625_post_acquisition_rediagnosis_v2(
            network_authorization={},
            network_receipt={},
            typed_execution_result={},
            reviewed_tensile_manifest={},
            quality_contract_path="quality.json",
        )
