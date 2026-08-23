"""Reviewed multi-source geometry-condition mapping for the tracked IN625 AMMT target."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from typing import Any, Mapping, Sequence

ACTION_CLASS = "reviewed_geometry_condition_mapping_assessment"
NEXT_ACTION_CLASS = "ammt_mds2_2923_calibration_protocol_bridge_evidence_acquisition"
TARGET_PROCESS_SHA256 = "bfec7d3099304edb3f7cefa96309d64853cc006eadf02ea976dc78b16bf1f137"
TARGET_RESPONSE_SHA256 = "728dc7de7675e14d6f5e1c0df42dcef90dcdd6c7d795a7039209decfc0b2712e"
_EXPECTED_CLAIMS = {
    "amb2018-ammt-actual-power-correction",
    "amb2018-programmed-cases-and-replications",
    "benchmark-ammt-calibration-note",
    "benchmark-later-spot-size-correction-note",
    "ricker-two-machine-bare-plate-design",
    "lane-surface-preparation-320-grit",
    "lane-ammt-cbm-spot-diameters",
    "lane-machine-environment",
    "lane-ammt-corrected-cases",
    "lane-cross-section-uncertainty-exists",
    "weaver-spot-size-range-abstract",
    "naderi-eos-m270-condition-space",
    "naderi-ammt-spot-range",
    "naderi-spot-measurement-authority",
    "nist-2026-machine-parameter-uncertainty",
    "nist-2026-cross-section-uncertainty",
}


class GeometryConditionMappingAssessmentError(ValueError):
    """Raised when the mapping inputs cannot support a bounded reviewed decision."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometryConditionMappingAssessmentError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _parse_csv(raw: bytes, field: str) -> list[dict[str, str]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GeometryConditionMappingAssessmentError(f"{field} is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    _require(bool(rows), f"{field} is empty")
    return rows


def _claim_index(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    sources = report.get("sources")
    _require(isinstance(sources, list) and len(sources) == 8, "multi-source report source count drifted")
    claims: dict[str, dict[str, Any]] = {}
    for source in sources:
        _require(isinstance(source, Mapping), "multi-source report entry malformed")
        _require(source.get("row_level_measurement_authority") is False, "paper source was promoted to row-level authority")
        source_id = source.get("source_id")
        _require(isinstance(source_id, str), "source_id missing in multi-source report")
        for claim in source.get("claims", []):
            _require(isinstance(claim, Mapping), "claim receipt malformed")
            claim_id = claim.get("claim_id")
            _require(isinstance(claim_id, str), "claim_id missing in evidence report")
            _require(claim_id not in claims, "claim_id duplicated across evidence sources")
            _require(claim.get("matched") is True, f"required evidence claim did not match: {claim_id}")
            claims[claim_id] = {"source_id": source_id, **dict(claim)}
    _require(set(claims) == _EXPECTED_CLAIMS, "multi-source claim universe drifted")
    return claims


def _axis(
    axis: str,
    status: str,
    rationale: str,
    evidence_ids: Sequence[str],
    *,
    conflicting_evidence_ids: Sequence[str] = (),
) -> dict[str, Any]:
    _require(status in {"established", "incompatible", "unresolved", "not_applicable"}, "invalid axis disposition")
    return {
        "axis": axis,
        "status": status,
        "rationale": rationale,
        "supporting_evidence_ids": list(evidence_ids),
        "conflicting_evidence_ids": list(conflicting_evidence_ids),
    }


def build_geometry_condition_mapping_assessment(
    *,
    nist_intake: Mapping[str, Any],
    multisource_evidence: Mapping[str, Any],
    target_process_bytes: bytes,
    target_response_bytes: bytes,
) -> dict[str, Any]:
    """Map mds2-2923 evidence to the tracked AMB2018 target without inventing bridges."""
    _require(
        hashlib.sha256(target_process_bytes).hexdigest() == TARGET_PROCESS_SHA256,
        "tracked target process-condition bytes drifted",
    )
    _require(
        hashlib.sha256(target_response_bytes).hexdigest() == TARGET_RESPONSE_SHA256,
        "tracked target response bytes drifted",
    )
    _require(
        multisource_evidence.get("acquisition_status")
        == "exact_multisource_condition_evidence_acquired",
        "multi-source evidence acquisition is not authenticated",
    )
    _require(multisource_evidence.get("source_count") == 8, "multi-source evidence source count drifted")
    _require(multisource_evidence.get("all_claim_anchors_matched") is True, "multi-source claim anchors are incomplete")
    _require(multisource_evidence.get("paper_claims_promoted_to_row_level_authority") is False, "paper evidence authority was improperly promoted")
    claims = _claim_index(multisource_evidence)

    inventory = nist_intake.get("in625_inventory")
    semantics = nist_intake.get("measurement_semantics")
    issue76 = nist_intake.get("issue_76")
    boundary = nist_intake.get("scientific_boundary")
    measurements = nist_intake.get("measurements")
    _require(isinstance(inventory, Mapping), "NIST inventory missing")
    _require(isinstance(semantics, Mapping), "NIST measurement semantics missing")
    _require(isinstance(issue76, Mapping), "NIST Issue #76 boundary missing")
    _require(isinstance(boundary, Mapping), "NIST scientific boundary missing")
    _require(isinstance(measurements, list) and len(measurements) == 178, "NIST measurement rows drifted")
    _require(inventory.get("physical_track_count") == 106, "NIST physical-track count drifted")
    _require(semantics.get("laser_power") == "machine_setting_as_stated_by_README", "NIST laser-power semantics drifted")
    _require(semantics.get("calibration_conversion_performed") is False, "NIST calibration conversion was already performed")
    _require(issue76.get("eligible") is False and issue76.get("exact_target_cells_satisfied") == 0, "Issue #76 was improperly promoted")
    _require(boundary.get("cross_machine_pooling_eligible") is False, "NIST intake improperly permits machine pooling")

    process_rows = _parse_csv(target_process_bytes, "target process conditions")
    response_rows = _parse_csv(target_response_bytes, "target melt-pool responses")
    _require(len(process_rows) == 10 and len(response_rows) == 10, "tracked target trace count drifted")
    process_ids = [row["sample_id"] for row in process_rows]
    response_ids = [row["sample_id"] for row in response_rows]
    _require(process_ids == response_ids and len(set(process_ids)) == 10, "tracked target process-response identity join drifted")
    _require({row["system"] for row in process_rows} == {"AMMT"}, "tracked target machine drifted")
    _require({row["material"] for row in process_rows} == {"IN625"}, "tracked target material drifted")
    target_conditions = Counter(
        (float(row["actual_laser_power_w"]), float(row["scan_speed_mm_s"]))
        for row in process_rows
    )
    _require(
        target_conditions == Counter({(137.9, 400.0): 3, (179.2, 800.0): 3, (179.2, 1200.0): 4}),
        "tracked target A/B/C condition contract drifted",
    )

    ammt_rows = [row for row in measurements if isinstance(row, Mapping) and row.get("machine") == "AMMT"]
    eos_rows = [row for row in measurements if isinstance(row, Mapping) and row.get("machine") == "EOS M270"]
    _require(len(ammt_rows) == 34 and len(eos_rows) == 144, "NIST machine row stratification drifted")
    ammt_power_speed = Counter(
        (
            float(row["laser_power_w_machine_setting"]),
            float(row["scan_speed_mm_s_machine_setting"]),
        )
        for row in ammt_rows
    )
    _require(ammt_power_speed == Counter({(180.0, 800.0): 16, (195.0, 800.0): 18}), "mds2 AMMT power/speed support drifted")
    _require({row.get("surface_condition_normalized") for row in ammt_rows} == {"320 grit"}, "mds2 AMMT surface state drifted")
    _require(all(row.get("material") == "IN625" for row in measurements), "mds2 material identity drifted")

    axes = [
        _axis(
            "nominal_material_identity",
            "established",
            "Tracked target and all admitted mds2 rows identify IN625.",
            ["tracked-target-process", "nist-mds2-2923-row-level"],
        ),
        _axis(
            "machine_identity",
            "established",
            "The 34-row mds2 AMMT subset shares the AMMT machine label with the tracked target; all 144 EOS M270 rows are explicitly excluded from direct target mapping.",
            ["nist-mds2-2923-row-level", "ricker-two-machine-bare-plate-design"],
        ),
        _axis(
            "programmed_or_machine_setting_laser_power",
            "incompatible",
            "The mds2 AMMT subset contains machine settings 180 W and 195 W at 800 mm/s, whereas the tracked AMB2018 cases were programmed at a different case set and later corrected to actual powers.",
            ["nist-mds2-2923-row-level", "amb2018-programmed-cases-and-replications"],
        ),
        _axis(
            "calibrated_actual_laser_power",
            "unresolved",
            "Official AMB2018 evidence establishes the tracked target's corrected actual powers, but no admitted evidence maps the mds2 AMMT 180/195 W machine settings to achieved calibrated actual power for that later experiment.",
            ["amb2018-ammt-actual-power-correction", "benchmark-ammt-calibration-note", "lane-ammt-corrected-cases"],
            conflicting_evidence_ids=["nist-mds2-2923-machine-setting-semantics"],
        ),
        _axis(
            "scan_speed",
            "incompatible",
            "All mds2 AMMT rows are 800 mm/s, while the tracked target spans 400, 800 and 1200 mm/s; only the speed coordinate of case B overlaps.",
            ["nist-mds2-2923-row-level", "tracked-target-process"],
        ),
        _axis(
            "laser_spot_size_definition_and_value",
            "unresolved",
            "Later evidence establishes deliberate spot-size variation and distinct D4-sigma/FWHM semantics, but it does not establish that a specific mds2 spot row is condition-equivalent to the tracked AMB2018 target.",
            ["benchmark-later-spot-size-correction-note", "lane-ammt-cbm-spot-diameters", "weaver-spot-size-range-abstract", "naderi-ammt-spot-range", "naderi-spot-measurement-authority"],
        ),
        _axis(
            "surface_preparation_and_material_state",
            "established",
            "The mds2 AMMT rows are explicitly 320 grit and the primary AMB2018 experiment report documents 320-grit bare-plate preparation.",
            ["nist-mds2-2923-row-level", "lane-surface-preparation-320-grit", "ricker-two-machine-bare-plate-design"],
        ),
        _axis(
            "shielding_gas_and_environment",
            "unresolved",
            "Primary evidence distinguishes machine gas/environment conditions, but the admitted mds2 row-level intake does not bind a per-row environment field sufficient for direct equivalence.",
            ["lane-machine-environment"],
        ),
        _axis(
            "track_identity_and_replication_semantics",
            "incompatible",
            "The tracked ten AMB2018 traces and the 106 mds2 physical tracks are distinct experiments with independent identifiers; no authoritative one-to-one row pairing exists.",
            ["tracked-target-process", "nist-mds2-2923-row-level", "ricker-two-machine-bare-plate-design"],
        ),
        _axis(
            "cross_section_measurement_protocol",
            "unresolved",
            "Both evidence families use melt-pool cross-section measurements, but the evidence admitted here does not establish protocol-level equivalence for direct numerical validation across the two experiment families.",
            ["lane-cross-section-uncertainty-exists", "nist-2026-cross-section-uncertainty"],
        ),
        _axis(
            "response_definition_width_depth",
            "established",
            "Both tracked target and mds2 row-level evidence provide melt-pool width and depth responses in micrometre-scale geometry semantics.",
            ["tracked-target-response", "nist-mds2-2923-row-level"],
        ),
        _axis(
            "uncertainty_and_calibration_support",
            "unresolved",
            "The benchmark literature demonstrates uncertainty analysis and machine-parameter uncertainty, but no exact uncertainty/calibration bridge has been bound between the mds2 rows and tracked ten-trace target.",
            ["lane-cross-section-uncertainty-exists", "nist-2026-machine-parameter-uncertainty", "nist-2026-cross-section-uncertainty"],
        ),
        _axis(
            "temporal_and_source_version_consistency",
            "unresolved",
            "Later official/paper evidence contains scoped calibration and spot-size corrections to earlier benchmark reporting; these are retained as versioned corrections rather than silently overwriting experiment identities.",
            ["benchmark-ammt-calibration-note", "benchmark-later-spot-size-correction-note", "lane-ammt-corrected-cases"],
        ),
    ]

    conflict_ledger = [
        {
            "conflict_id": "amb2018-commanded-versus-corrected-actual-power",
            "classification": "explicit_scoped_calibration_correction",
            "older_semantics": "commanded/programmed power",
            "later_semantics": "corrected actual AMMT power for tracked AMB2018 A/B/C cases",
            "resolution": "retain both semantics; corrected actual values apply only to the tracked AMB2018 cases supported by the correction evidence",
            "evidence_ids": ["amb2018-programmed-cases-and-replications", "amb2018-ammt-actual-power-correction", "benchmark-ammt-calibration-note"],
        },
        {
            "conflict_id": "amb2018-original-versus-later-measured-spot-size",
            "classification": "later_measurement_and_definition_refinement",
            "older_semantics": "intended/originally reported laser spot size",
            "later_semantics": "measured machine-specific D4-sigma/FWHM spot-size evidence",
            "resolution": "do not overwrite by date alone; retain definition, machine and experiment scope for each value",
            "evidence_ids": ["benchmark-later-spot-size-correction-note", "lane-ammt-cbm-spot-diameters", "weaver-spot-size-range-abstract", "naderi-spot-measurement-authority"],
        },
        {
            "conflict_id": "mds2-ammt-setting-versus-tracked-actual-power",
            "classification": "unresolved_cross_experiment_calibration_mapping",
            "older_semantics": "tracked AMB2018 corrected actual power",
            "later_semantics": "mds2 AMMT machine-setting power",
            "resolution": "no conversion or equivalence is allowed until experiment-specific calibration bridge evidence is acquired",
            "evidence_ids": ["nist-mds2-2923-machine-setting-semantics", "benchmark-ammt-calibration-note", "naderi-ammt-spot-range"],
        },
    ]

    decision = {
        "decision_code": "direct_mds2_to_tracked_amb2018_validation_blocked_by_condition_and_calibration_mapping",
        "material_identity_established": True,
        "response_compatibility_established": True,
        "same_machine_subset_identified": True,
        "eos_rows_excluded_from_direct_mapping": 144,
        "mds2_ammt_rows_reviewed": 34,
        "directly_comparable_mds2_rows": 0,
        "calibrated_actual_power_mapping_established": False,
        "spot_size_mapping_established": False,
        "protocol_equivalence_established": False,
        "direct_numerical_validation_authorized": False,
        "cross_machine_pooling_authorized": False,
        "paper_claims_promoted_to_row_level_authority": False,
        "issue_76_exact_target_cells_satisfied": 0,
        "issue_76_eligible": False,
        "scientific_status_changed": False,
    }

    next_action = {
        "action_class": NEXT_ACTION_CLASS,
        "objective": "Acquire experiment-specific authoritative calibration/protocol bridge evidence for the mds2-2923 AMMT spot-size experiment before any direct comparison to the tracked AMB2018 target.",
        "required_bridge_evidence": [
            "mds2 AMMT 180/195 W machine-setting to achieved/calibrated actual-power mapping for the exact experiment",
            "spot-size definition/value mapping with machine and experiment scope",
            "cross-section preparation/measurement protocol and uncertainty compatibility",
            "explicit evidence distinguishing or linking mds2 experiment identity to tracked AMB2018 A/B/C cases",
        ],
        "eligible_evidence_lanes": [
            "official_calibration_metrology_documentation",
            "paper_and_supplementary_material",
            "authoritative_dataset_repository",
            "characterization_evidence",
            "direct_author_correspondence_or_repository_release_if_provenance_bound",
        ],
        "unrestricted_search_authorized": False,
        "automatic_execution_authorized": False,
        "issue_76_promotion_authorized": False,
    }

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "assessment_status": "reviewed_multisource_geometry_condition_mapping_completed",
        "target_binding": {
            "process_conditions_sha256": TARGET_PROCESS_SHA256,
            "melt_pool_measurements_sha256": TARGET_RESPONSE_SHA256,
            "trace_count": 10,
            "machine": "AMMT",
            "material": "IN625",
            "actual_power_speed_replication": {
                "137.9W_400mm_s": 3,
                "179.2W_800mm_s": 3,
                "179.2W_1200mm_s": 4,
            },
        },
        "mds2_binding": {
            "measurement_row_count": 178,
            "physical_track_count": 106,
            "ammt_measurement_rows": 34,
            "eos_m270_measurement_rows": 144,
            "ammt_machine_setting_power_speed_support": {
                "180W_800mm_s": 16,
                "195W_800mm_s": 18,
            },
        },
        "multisource_evidence_binding": {
            "report_sha256": multisource_evidence.get("report_sha256_without_self_field"),
            "source_count": 8,
            "claim_count": len(claims),
            "actual_source_sha256_by_id": {
                source["source_id"]: source["source_sha256"]
                for source in multisource_evidence["sources"]
            },
        },
        "condition_map": axes,
        "conflict_version_ledger": conflict_ledger,
        "gate_decision": decision,
        "next_action": next_action,
        "scientific_boundary": {
            "numerical_cross_source_comparison_performed": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout": False,
            "source_acquisition_success_interpreted_as_scientific_support": False,
            "scientific_status_changed": False,
        },
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


__all__ = [
    "ACTION_CLASS",
    "GeometryConditionMappingAssessmentError",
    "NEXT_ACTION_CLASS",
    "TARGET_PROCESS_SHA256",
    "TARGET_RESPONSE_SHA256",
    "build_geometry_condition_mapping_assessment",
]
