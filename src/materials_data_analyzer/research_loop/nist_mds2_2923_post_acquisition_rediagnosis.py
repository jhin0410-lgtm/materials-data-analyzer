"""Re-diagnose the research frontier after exact NIST mds2-2923 scientific intake.

The NIST workbook supplies response-compatible melt-pool width/depth evidence, but that is not
the same as direct condition equivalence to the tracked AMMT target.  This transition therefore
records the real geometry evidence and routes the next work toward reviewed machine/process/
calibration mapping.  Papers, supplementary material, technical reports, official documentation,
and further row-level datasets remain valid evidence lanes for resolving that mapping.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "1.0"
NEXT_ACTION_CLASS = "reviewed_geometry_condition_mapping_assessment"
BLOCKER_CODE = "geometry_condition_mapping_not_established"


class NistMds22923PostAcquisitionRediagnosisError(ValueError):
    """Raised when the verified NIST evidence state cannot support re-diagnosis."""


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NistMds22923PostAcquisitionRediagnosisError(message)


def build_nist_mds2_2923_post_acquisition_rediagnosis(
    *,
    acquisition_receipt: Mapping[str, Any],
    scientific_intake: Mapping[str, Any],
) -> dict[str, Any]:
    """Create the next bounded research state from exact acquired NIST evidence."""
    _require(
        acquisition_receipt.get("acquisition_status")
        == "exact_nist_mds2_2923_source_files_acquired",
        "NIST acquisition receipt is not the exact production acquisition",
    )
    _require(
        acquisition_receipt.get("candidate_id")
        == "nist-mds2-2923-cross-sectional-micrographs",
        "NIST acquisition candidate drifted",
    )
    _require(
        acquisition_receipt.get("product_id") == "mds2-2923",
        "NIST acquisition product drifted",
    )
    _require(
        acquisition_receipt.get("metadata_sha256")
        == "e10b2afb0e8b5f0d3b0a015bb38ed59a285510e1bb8534fed73f2fd0b7e883b6",
        "NIST metadata digest drifted",
    )
    _require(
        acquisition_receipt.get("network_requests_performed") == 3,
        "NIST production acquisition did not use the exact three-request path",
    )
    _require(
        acquisition_receipt.get("all_acquisition_provenance_authenticated") is True,
        "NIST acquisition provenance was not fully authenticated",
    )
    _require(
        acquisition_receipt.get("unrestricted_network_search_performed") is False
        and acquisition_receipt.get("arbitrary_url_fetch_performed") is False,
        "NIST acquisition widened network authority",
    )

    source = scientific_intake.get("source")
    inventory = scientific_intake.get("in625_inventory")
    semantics = scientific_intake.get("measurement_semantics")
    issue_76 = scientific_intake.get("issue_76")
    boundary = scientific_intake.get("scientific_boundary")
    _require(isinstance(source, Mapping), "NIST intake source is missing")
    _require(isinstance(inventory, Mapping), "NIST intake inventory is missing")
    _require(isinstance(semantics, Mapping), "NIST intake semantics are missing")
    _require(isinstance(issue_76, Mapping), "NIST intake Issue #76 boundary is missing")
    _require(isinstance(boundary, Mapping), "NIST intake scientific boundary is missing")

    _require(source.get("product_id") == "mds2-2923", "NIST intake product drifted")
    _require(
        source.get("doi") == "10.18434/mds2-2923",
        "NIST intake DOI drifted",
    )
    _require(
        source.get("workbook_sha256")
        == "6cd32669f5c84cdb9e90890ba40ddc5548c85b0dbb95cf038f2f6fc69da67a52",
        "NIST intake workbook digest drifted",
    )
    _require(
        source.get("readme_sha256")
        == "8b8fc00ce62915af3e0c91c138dc4d033c031d7758161fb9da0e8702fa621c39",
        "NIST intake README digest drifted",
    )
    _require(
        source.get("nerdm_metadata_sha256")
        == "e10b2afb0e8b5f0d3b0a015bb38ed59a285510e1bb8534fed73f2fd0b7e883b6",
        "NIST intake metadata digest drifted",
    )
    _require(
        inventory.get("measurement_row_count") == 178,
        "NIST IN625 measurement-row count drifted",
    )
    _require(
        inventory.get("physical_track_count") == 106,
        "NIST IN625 physical-track count drifted",
    )
    _require(
        inventory.get("machine_measurement_counts") == {"AMMT": 34, "EOS M270": 144},
        "NIST machine measurement inventory drifted",
    )
    _require(
        inventory.get("machine_physical_track_counts") == {"AMMT": 34, "EOS M270": 72},
        "NIST machine physical-track inventory drifted",
    )
    _require(
        inventory.get("source_track_metadata_conflict_count") == 1,
        "NIST source metadata conflict count drifted",
    )
    _require(
        semantics.get("laser_power") == "machine_setting_as_stated_by_README"
        and semantics.get("calibration_conversion_performed") is False,
        "NIST power semantics were improperly promoted",
    )
    _require(
        issue_76.get("eligible") is False
        and issue_76.get("exact_target_cells_satisfied") == 0,
        "NIST intake improperly promoted Issue #76 eligibility",
    )
    _require(
        boundary.get("cross_machine_pooling_eligible") is False
        and boundary.get("predictive_modeling_eligible_from_this_audit") is False
        and boundary.get("scientific_status_changed") is False,
        "NIST intake widened scientific authority",
    )

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "input_acquisition_receipt_sha256": acquisition_receipt.get("receipt_sha256"),
        "input_scientific_intake_sha256": scientific_intake.get(
            "report_sha256_without_self_field"
        ),
        "verified_new_evidence": {
            "source": "NIST PDR mds2-2923",
            "material": "IN625",
            "response_semantics": ["melt_pool_width", "melt_pool_depth"],
            "measurement_row_count": 178,
            "dataset_local_physical_track_count": 106,
            "machine_measurement_counts": {"AMMT": 34, "EOS M270": 144},
            "machine_physical_track_counts": {"AMMT": 34, "EOS M270": 72},
            "row_level_authority": "Data sheet",
            "summary_role": "incomplete_derived_view",
            "source_metadata_conflict_count": 1,
            "geometry_response_compatibility_established": True,
        },
        "current_blocker": {
            "code": BLOCKER_CODE,
            "reason": (
                "Response-compatible width/depth evidence is now acquired, but machine identity, "
                "programmed-versus-calibrated power, spot size, surface state, and target-condition "
                "mapping remain insufficient for direct cross-source numerical validation."
            ),
        },
        "next_action": {
            "action_class": NEXT_ACTION_CLASS,
            "goal": (
                "Review condition-level comparability across the tracked NIST target and mds2-2923 "
                "without pooling machines or converting machine settings into calibrated power."
            ),
            "eligible_evidence_lanes": [
                "authoritative_row_level_dataset",
                "paper_and_supplementary_material",
                "official_technical_report",
                "official_calibration_or_metrology_documentation",
                "characterization_evidence",
                "other_provenance_verifiable_physical_evidence",
            ],
            "paper_evidence_role": (
                "May establish or challenge protocol, calibration, machine, spot-size, surface-state, "
                "and condition-mapping claims; literature-only claims are not silently promoted to "
                "row-level measurement authority."
            ),
            "network_access_performed": False,
            "automatic_execution_authorized": False,
        },
        "scientific_boundary": {
            "response_compatible_geometry_evidence_acquired": True,
            "direct_target_condition_comparability_established": False,
            "cross_machine_pooling_performed": False,
            "calibration_conversion_performed": False,
            "issue_76_eligible": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_established": False,
            "global_evidence_unavailability_claimed": False,
            "scientific_status_changed": False,
        },
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    result["rediagnosis_sha256"] = _canonical_sha(result)
    return result


__all__ = [
    "BLOCKER_CODE",
    "NEXT_ACTION_CLASS",
    "NistMds22923PostAcquisitionRediagnosisError",
    "build_nist_mds2_2923_post_acquisition_rediagnosis",
]
