"""Scientifically assess acquired NIST calibration literature without promoting acquisition success."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .nist_ammt_calibration_candidate_acquisition import ACTION_CLASS as ACQUISITION_ACTION_CLASS

NEXT_ACTION_CLASS = "mds2_2923_experiment_identity_reference_chain_assessment"


class NistAmmtCalibrationCandidateBridgeAssessmentError(ValueError):
    """Raised when calibration-candidate evidence or predecessor boundaries drift."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NistAmmtCalibrationCandidateBridgeAssessmentError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_self_hash(value: Mapping[str, Any], field: str) -> str:
    digest = value.get(field)
    _require(isinstance(digest, str) and len(digest) == 64, f"{field} is missing")
    unsigned = dict(value)
    unsigned.pop(field, None)
    _require(_canonical_sha(unsigned) == digest, f"{field} is invalid")
    return digest


def _validate_manifest(manifest: Mapping[str, Any]) -> str:
    digest = manifest.get("manifest_sha256")
    _require(isinstance(digest, str) and len(digest) == 64, "predecessor manifest SHA is missing")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    _require(_canonical_sha(unsigned) == digest, "predecessor manifest self binding is invalid")
    return digest


def _claim_map(acquisition: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = acquisition.get("claim_receipts")
    _require(isinstance(raw, list), "acquisition claim receipts are missing")
    result: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        _require(isinstance(item, Mapping), "claim receipt must be an object")
        claim_id = item.get("claim_id")
        _require(isinstance(claim_id, str) and claim_id, "claim receipt identity is missing")
        _require(claim_id not in result, "claim receipt identities must be unique")
        result[claim_id] = item
    return result


def build_calibration_candidate_bridge_assessment(
    *,
    acquisition_report: Mapping[str, Any],
    predecessor_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Assess experiment-specific calibration bridge authority from exact acquired literature."""
    acquisition_sha = _validate_self_hash(
        acquisition_report,
        "report_sha256_without_self_field",
    )
    manifest_sha = _validate_manifest(predecessor_manifest)
    _require(
        acquisition_report.get("action_class") == ACQUISITION_ACTION_CLASS
        and acquisition_report.get("acquisition_status")
        == "derived_nist_calibration_candidate_and_full_text_acquired",
        "candidate acquisition status/action drifted",
    )
    _require(
        acquisition_report.get("candidate_rank") == 1
        and acquisition_report.get("candidate_url_derived_from_discovery") is True
        and acquisition_report.get("full_text_url_derived_from_candidate_page") is True
        and acquisition_report.get("network_requests_performed") == 2,
        "candidate acquisition derivation/budget contract drifted",
    )
    _require(
        acquisition_report.get("caller_authored_url_used") is False
        and acquisition_report.get("unrestricted_search_performed") is False
        and acquisition_report.get("literature_promoted_to_row_level_measurement_authority") is False
        and acquisition_report.get("acquisition_success_establishes_calibration_bridge") is False
        and acquisition_report.get("scientific_status_changed") is False,
        "candidate acquisition improperly widened scientific authority",
    )
    _require(
        predecessor_manifest.get("directly_comparable_mds2_rows") == 0
        and predecessor_manifest.get("issue_76_exact_target_cells_satisfied") == 0
        and predecessor_manifest.get("bridge_established") is False,
        "predecessor scientific boundary drifted before calibration assessment",
    )

    claims = _claim_map(acquisition_report)
    required_claim_ids = {
        "digital_camera_in_situ_calibration_methodology",
        "open_platform_testbed_experiment_scope",
        "spot_calibration_200w_pulsed_condition",
        "d4sigma_spot_definition",
        "explicit_mds2_2923_identity",
        "explicit_machine_setting_actual_power_bridge",
    }
    _require(required_claim_ids.issubset(claims), "required calibration claim receipts are incomplete")

    calibration_methodology = claims[
        "digital_camera_in_situ_calibration_methodology"
    ].get("matched") is True
    open_platform_scope = claims["open_platform_testbed_experiment_scope"].get("matched") is True
    spot_200w_scope = claims["spot_calibration_200w_pulsed_condition"].get("matched") is True
    d4sigma_definition = claims["d4sigma_spot_definition"].get("matched") is True
    explicit_mds2_identity = claims["explicit_mds2_2923_identity"].get("matched") is True
    explicit_power_bridge = claims[
        "explicit_machine_setting_actual_power_bridge"
    ].get("matched") is True

    bridge_established = bool(explicit_mds2_identity and explicit_power_bridge)
    _require(
        bridge_established is False,
        "first calibration candidate unexpectedly establishes an exact bridge; independent review required",
    )

    assessment: dict[str, Any] = {
        "schema_version": "1.0",
        "assessment_type": "experiment_specific_calibration_bridge_assessment",
        "acquisition_report_sha256": acquisition_sha,
        "predecessor_manifest_sha256": manifest_sha,
        "evidence_class": "primary_calibration_methodology_paper",
        "evidence_scope": {
            "official_nist_ammt_index_association_established": True,
            "digital_camera_in_situ_calibration_methodology_established": calibration_methodology,
            "open_platform_testbed_experiment_scope_established": open_platform_scope,
            "paper_spot_calibration_200w_pulsed_condition_established": spot_200w_scope,
            "d4sigma_spot_definition_established": d4sigma_definition,
        },
        "experiment_specific_bridge": {
            "exact_mds2_2923_experiment_identity_established": explicit_mds2_identity,
            "exact_machine_setting_to_calibrated_power_relation_established": explicit_power_bridge,
            "exact_mds2_spot_size_value_transfer_established": False,
            "cross_section_protocol_identity_established": False,
            "uncertainty_transfer_established": False,
            "bridge_established": bridge_established,
        },
        "gate_decision": {
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_validation_authorized": False,
            "direct_numerical_cross_source_validation_authorized": False,
            "cross_machine_pooling_authorized": False,
            "literature_promoted_to_row_level_measurement_authority": False,
            "issue_76_exact_target_cells_satisfied": 0,
        },
        "interpretation": (
            "The acquired NIST paper establishes a concrete in-situ laser calibration methodology, "
            "including D4sigma spot characterization and a 200 W pulsed calibration experiment, "
            "but it does not explicitly identify mds2-2923 or provide the required 180/195 W "
            "machine-setting to 137.9/179.2 W calibrated-actual-power relation."
        ),
        "new_verified_information": bool(
            calibration_methodology or open_platform_scope or spot_200w_scope or d4sigma_definition
        ),
        "scientific_status_changed": False,
        "positive_scientific_closeout": False,
        "global_evidence_unavailability_claimed": False,
        "next_action": {
            "action_class": NEXT_ACTION_CLASS,
            "objective": (
                "Trace the exact mds2-2923 AMMT experiment identity and calibration reference chain "
                "across the dataset README/workbook, the Naderi spot-size experiment, and NIST AMMT "
                "design/calibration references to determine whether an experiment-scoped power and "
                "protocol bridge exists."
            ),
            "eligible_evidence_lanes": [
                "authoritative_dataset_or_readme",
                "primary_paper_reference_chain",
                "official_ammt_design_or_calibration_documentation",
                "supplementary_material_or_repository_artifact",
                "provenance_bound_author_correspondence_or_release",
            ],
            "automatic_unrestricted_search_authorized": False,
            "caller_authored_arbitrary_urls_authorized": False,
        },
    }
    assessment["report_sha256_without_self_field"] = _canonical_sha(assessment)
    return assessment


__all__ = [
    "NEXT_ACTION_CLASS",
    "NistAmmtCalibrationCandidateBridgeAssessmentError",
    "build_calibration_candidate_bridge_assessment",
]
