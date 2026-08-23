from __future__ import annotations

import hashlib
import json
from typing import Any

from materials_data_analyzer.research_loop import nist_ammt_calibration_candidate_acquisition as acquisition
from materials_data_analyzer.research_loop import nist_ammt_calibration_candidate_bridge_assessment as assessment


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _acquisition_report() -> dict[str, Any]:
    claims = [
        ("digital_camera_in_situ_calibration_methodology", True),
        ("open_platform_testbed_experiment_scope", True),
        ("spot_calibration_200w_pulsed_condition", True),
        ("d4sigma_spot_definition", True),
        ("explicit_mds2_2923_identity", False),
        ("explicit_machine_setting_actual_power_bridge", False),
    ]
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "action_class": acquisition.ACTION_CLASS,
        "acquisition_status": "derived_nist_calibration_candidate_and_full_text_acquired",
        "candidate_rank": 1,
        "candidate_url_derived_from_discovery": True,
        "full_text_url_derived_from_candidate_page": True,
        "network_requests_performed": 2,
        "caller_authored_url_used": False,
        "unrestricted_search_performed": False,
        "literature_promoted_to_row_level_measurement_authority": False,
        "acquisition_success_establishes_calibration_bridge": False,
        "scientific_status_changed": False,
        "claim_receipts": [
            {
                "claim_id": claim_id,
                "matched": matched,
            }
            for claim_id, matched in claims
        ],
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


def _manifest() -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "directly_comparable_mds2_rows": 0,
        "issue_76_exact_target_cells_satisfied": 0,
        "bridge_established": False,
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    return manifest


def test_calibration_assessment_exposes_explicit_cross_source_gate_without_promotion() -> None:
    result = assessment.build_calibration_candidate_bridge_assessment(
        acquisition_report=_acquisition_report(),
        predecessor_manifest=_manifest(),
    )

    gate = result["gate_decision"]
    assert gate["directly_comparable_mds2_rows"] == 0
    assert gate["issue_76_exact_target_cells_satisfied"] == 0
    assert gate["direct_numerical_validation_authorized"] is False
    assert gate["direct_numerical_cross_source_validation_authorized"] is False
    assert gate["cross_machine_pooling_authorized"] is False
    assert result["experiment_specific_bridge"]["bridge_established"] is False
    assert result["scientific_status_changed"] is False

    unsigned = dict(result)
    digest = unsigned.pop("report_sha256_without_self_field")
    assert digest == _canonical_sha(unsigned)
