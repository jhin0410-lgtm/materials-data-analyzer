"""Real-evidence adapters used by the first IN625 autonomous-scientist benchmark.

This module is benchmark/domain composition, not a second generic EvidencePacket core.  It
reuses the exact mds2-2923 scientific intake parser against live/retained workbook, README,
and NERDm bytes, then narrows that authenticated intake to the AMMT 195 W / 800 mm/s
machine-setting subset.

The resulting packets preserve a critical semantic distinction:

* 195 W is the source workbook's AMMT *machine setting*;
* it is not silently converted to calibrated/actual optical power;
* row-level width/depth authority comes from the exact workbook Data sheet;
* micrograph identity is retained as context but image bytes are not invented or claimed
  as packet-bound artifacts unless a later adapter explicitly acquires them.

Packets do not authorize cross-source comparability, calibration transfer, prediction,
causality, optimization, or engineering use.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from typing import Any

from .evidence_packet import finalize_evidence_packet
from .nist_mds2_2923_scientific_intake import audit_mds2_2923

MDS2_BENCHMARK_ADAPTER_ID = "mds2-2923-ammt-195w-800-evidence-packet-v1"


class In625CompetencyEvidenceError(ValueError):
    """Raised when benchmark evidence would exceed the authenticated mds2 source."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise In625CompetencyEvidenceError(message)


def _binding(
    *,
    binding_id: str,
    role: str,
    artifact_id: str,
    locator: str,
    raw: bytes,
    media_type: str,
) -> dict[str, Any]:
    return {
        "binding_id": binding_id,
        "role": role,
        "artifact_id": artifact_id,
        "locator": locator,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "media_type": media_type,
    }


def _attribute(
    name: str,
    value: object,
    *,
    source_binding_ids: list[str],
    unit: str | None = None,
) -> dict[str, Any]:
    if isinstance(value, bool):
        value_type = "boolean"
    elif isinstance(value, int):
        value_type = "integer"
    elif isinstance(value, float):
        value_type = "number"
    elif isinstance(value, str):
        value_type = "text"
    else:
        raise In625CompetencyEvidenceError(
            f"unsupported context value type for {name!r}"
        )
    return {
        "name": name,
        "value": value,
        "value_type": value_type,
        "unit_state": "specified" if unit is not None else "not_applicable",
        "unit": unit,
        "source_binding_ids": list(source_binding_ids),
    }


def build_mds2_2923_ammt_195_800_evidence_packets(
    *,
    workbook_bytes: bytes,
    readme_bytes: bytes,
    nerdm_metadata_bytes: bytes,
) -> list[dict[str, Any]]:
    """Recompute and adapt the exact AMMT 195 W / 800 mm/s IN625 row subset."""

    intake = audit_mds2_2923(
        workbook_bytes=workbook_bytes,
        readme_bytes=readme_bytes,
        nerdm_metadata_bytes=nerdm_metadata_bytes,
    )
    source = intake.get("source")
    semantics = intake.get("measurement_semantics")
    boundary = intake.get("scientific_boundary")
    issue76 = intake.get("issue_76")
    measurements = intake.get("measurements")
    _require(isinstance(source, Mapping), "mds2 source block is missing")
    _require(isinstance(semantics, Mapping), "mds2 measurement semantics are missing")
    _require(isinstance(boundary, Mapping), "mds2 scientific boundary is missing")
    _require(isinstance(issue76, Mapping), "mds2 Issue #76 boundary is missing")
    _require(isinstance(measurements, list), "mds2 measurements are missing")

    _require(
        source.get("product_id") == "mds2-2923"
        and source.get("doi") == "10.18434/mds2-2923",
        "mds2 source identity drifted",
    )
    _require(
        source.get("workbook_sha256") == hashlib.sha256(workbook_bytes).hexdigest()
        and source.get("readme_sha256") == hashlib.sha256(readme_bytes).hexdigest()
        and source.get("nerdm_metadata_sha256")
        == hashlib.sha256(nerdm_metadata_bytes).hexdigest(),
        "mds2 source-byte binding drifted",
    )
    _require(
        semantics.get("laser_power") == "machine_setting_as_stated_by_README"
        and semantics.get("scan_speed") == "machine_setting_as_stated_by_README"
        and semantics.get("calibration_conversion_performed") is False,
        "mds2 machine-setting semantics drifted",
    )
    _require(
        boundary.get("cross_machine_pooling_eligible") is False
        and boundary.get("predictive_modeling_eligible_from_this_audit") is False
        and boundary.get("causal_inference_eligible_from_this_audit") is False
        and boundary.get("optimization_eligible_from_this_audit") is False
        and boundary.get("scientific_status_changed") is False,
        "mds2 scientific boundary widened",
    )
    _require(
        issue76.get("eligible") is False
        and issue76.get("exact_target_cells_satisfied") == 0,
        "mds2 Issue #76 boundary was promoted",
    )

    subset = [
        item
        for item in measurements
        if isinstance(item, Mapping)
        and item.get("material") == "IN625"
        and item.get("machine") == "AMMT"
        and item.get("laser_power_w_machine_setting") == 195.0
        and item.get("scan_speed_mm_s_machine_setting") == 800.0
    ]
    _require(len(subset) == 18, "mds2 AMMT 195 W / 800 mm/s row count drifted")
    track_ids = {
        item.get("physical_track_id")
        for item in subset
        if isinstance(item.get("physical_track_id"), str)
    }
    spot_levels = {
        float(item["estimated_or_measured_spot_diameter_um"])
        for item in subset
    }
    _require(len(track_ids) == 18, "mds2 AMMT subset physical-track count drifted")
    _require(
        len(spot_levels) == 7 and min(spot_levels) == 50.0 and max(spot_levels) == 256.0,
        "mds2 AMMT subset spot-size signature drifted",
    )

    source_bindings = [
        _binding(
            binding_id="mds2-workbook",
            role="authoritative_row_level_data_sheet",
            artifact_id="mds2-2923:Master_TrackList_Measurements.xlsx",
            locator="NIST mds2-2923/Master_TrackList_Measurements.xlsx",
            raw=workbook_bytes,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        ),
        _binding(
            binding_id="mds2-readme",
            role="source_measurement_semantics",
            artifact_id="mds2-2923:README",
            locator="NIST mds2-2923/README",
            raw=readme_bytes,
            media_type="text/plain",
        ),
        _binding(
            binding_id="mds2-nerdm",
            role="authoritative_repository_file_manifest",
            artifact_id="mds2-2923:NERDm-metadata",
            locator="NIST mds2-2923/NERDm-metadata.json",
            raw=nerdm_metadata_bytes,
            media_type="application/json",
        ),
    ]

    packets: list[dict[str, Any]] = []
    for row in sorted(subset, key=lambda item: int(item["workbook_excel_row"])):
        measurement_id = str(row["measurement_id"])
        physical_track_id = str(row["physical_track_id"])
        excel_row = int(row["workbook_excel_row"])
        width = float(row["width_um"])
        depth = float(row["depth_um"])
        spot = float(row["estimated_or_measured_spot_diameter_um"])
        pixel = float(row["pixel_size_um"])
        track_no = row["track_no"]
        _require(width > 0.0 and depth > 0.0, "mds2 row geometry must be positive")

        packet = finalize_evidence_packet(
            {
                "schema_version": "1.0",
                "packet_type": "evidence_packet",
                "evidence_id": measurement_id,
                "evidence_kind": "measurement",
                "provider": {
                    "provider_id": "nist-mds2-2923-row-provider",
                    "contract_version": "1.0",
                    "schema_version": "1.0",
                    "adapter_id": MDS2_BENCHMARK_ADAPTER_ID,
                },
                "subject": {
                    "subject_type": "material_process_cross_section_measurement",
                    "identities": [
                        {"namespace": "material", "value": "IN625", "role": "material"},
                        {
                            "namespace": "mds2_measurement_id",
                            "value": measurement_id,
                            "role": "measurement",
                        },
                        {
                            "namespace": "mds2_physical_track_id",
                            "value": physical_track_id,
                            "role": "sample",
                        },
                        {
                            "namespace": "mds2_workbook_excel_row",
                            "value": str(excel_row),
                            "role": "row",
                        },
                    ],
                    "material_scope": (
                        "NIST mds2-2923 IN625 AMMT 195 W / 800 mm/s "
                        "machine-setting subset"
                    ),
                    "description": (
                        "One authoritative workbook Data-sheet melt-pool cross-section "
                        "measurement; power remains the source machine setting."
                    ),
                },
                "contexts": {
                    "process": {
                        "status": "applicable",
                        "attributes": [
                            _attribute(
                                "process_family",
                                "additive_manufacturing",
                                source_binding_ids=["mds2-readme"],
                            ),
                            _attribute(
                                "process_route",
                                "NIST AMMT bare-substrate laser track experiment",
                                source_binding_ids=["mds2-readme", "mds2-workbook"],
                            ),
                            _attribute(
                                "laser_power_machine_setting",
                                195.0,
                                unit="W",
                                source_binding_ids=["mds2-workbook", "mds2-readme"],
                            ),
                            _attribute(
                                "scan_speed_machine_setting",
                                800.0,
                                unit="mm/s",
                                source_binding_ids=["mds2-workbook", "mds2-readme"],
                            ),
                            _attribute(
                                "spot_diameter_D4sigma",
                                spot,
                                unit="um",
                                source_binding_ids=["mds2-workbook", "mds2-readme"],
                            ),
                            _attribute(
                                "machine",
                                "AMMT",
                                source_binding_ids=["mds2-workbook"],
                            ),
                        ],
                    },
                    "sample": {
                        "status": "applicable",
                        "attributes": [
                            _attribute(
                                "physical_track_id",
                                physical_track_id,
                                source_binding_ids=["mds2-workbook"],
                            ),
                            _attribute(
                                "track_no",
                                int(track_no) if isinstance(track_no, int) else float(track_no),
                                source_binding_ids=["mds2-workbook"],
                            ),
                            _attribute(
                                "surface_condition",
                                str(row["surface_condition_normalized"]),
                                source_binding_ids=["mds2-workbook"],
                            ),
                            _attribute(
                                "scan_direction",
                                str(row["scan_direction"]),
                                source_binding_ids=["mds2-workbook"],
                            ),
                        ],
                    },
                    "method": {
                        "status": "applicable",
                        "attributes": [
                            _attribute(
                                "method",
                                "optical cross-section measurement as defined by mds2 README",
                                source_binding_ids=["mds2-readme"],
                            ),
                            _attribute(
                                "pixel_size",
                                pixel,
                                unit="um",
                                source_binding_ids=["mds2-workbook"],
                            ),
                        ],
                    },
                    "measurement": {
                        "status": "applicable",
                        "attributes": [
                            _attribute(
                                "measurement_semantics",
                                "workbook Data-sheet width/depth row measurement",
                                source_binding_ids=["mds2-workbook", "mds2-readme"],
                            ),
                            _attribute(
                                "micrograph_filepath",
                                str(row["nerdm_micrograph_filepath"]),
                                source_binding_ids=["mds2-workbook", "mds2-nerdm"],
                            ),
                            _attribute(
                                "micrograph_sha256",
                                str(row["nerdm_micrograph_sha256"]),
                                source_binding_ids=["mds2-nerdm"],
                            ),
                            _attribute(
                                "micrograph_size_bytes",
                                int(row["nerdm_micrograph_size_bytes"]),
                                source_binding_ids=["mds2-nerdm"],
                            ),
                            _attribute(
                                "reference_convention",
                                "melt-pool transverse width/depth geometry",
                                source_binding_ids=["mds2-readme"],
                            ),
                        ],
                    },
                },
                "results": [
                    {
                        "result_id": "melt-pool-width",
                        "result_kind": "melt_pool_width",
                        "value_state": "observed",
                        "value": width,
                        "value_type": "number",
                        "unit_state": "specified",
                        "unit": "um",
                        "source_binding_ids": ["mds2-workbook"],
                        "derivation_ids": [],
                        "uncertainty_ids": ["row-measurement-uncertainty"],
                        "qualifiers": [
                            "authoritative-workbook-data-sheet",
                            "machine-setting-power-not-calibrated-actual-power",
                        ],
                    },
                    {
                        "result_id": "melt-pool-depth",
                        "result_kind": "melt_pool_depth",
                        "value_state": "observed",
                        "value": depth,
                        "value_type": "number",
                        "unit_state": "specified",
                        "unit": "um",
                        "source_binding_ids": ["mds2-workbook"],
                        "derivation_ids": [],
                        "uncertainty_ids": ["row-measurement-uncertainty"],
                        "qualifiers": [
                            "authoritative-workbook-data-sheet",
                            "machine-setting-power-not-calibrated-actual-power",
                        ],
                    },
                ],
                "uncertainty": [
                    {
                        "uncertainty_id": "row-measurement-uncertainty",
                        "status": "unknown",
                        "kind": "row_specific_measurement_uncertainty",
                        "value": None,
                        "unit": None,
                        "distribution": None,
                        "confidence_level": None,
                        "source_binding_ids": ["mds2-workbook", "mds2-readme"],
                        "notes": (
                            "No row-specific numeric uncertainty is invented from the "
                            "derived Summary sheet."
                        ),
                    }
                ],
                "calibration": {"status": "unknown", "records": []},
                "source_bindings": copy.deepcopy(source_bindings),
                "derivation_lineage": [],
                "independence": {
                    "source_family_id": "nist-mds2-2923",
                    "dataset_parent_id": "nist-mds2-2923",
                    "sample_parent_ids": [physical_track_id],
                    "acquisition_parent_ids": [physical_track_id],
                    "development_family_id": None,
                    "overlap_status": "unknown",
                    "overlap_with": [],
                    "independence_claim_status": "not_assessed",
                },
                "scientific_validity": {
                    "domain_verifier_id": MDS2_BENCHMARK_ADAPTER_ID,
                    "verification_status": "limited",
                    "validated_scope": [
                        "exact workbook/README/NERDm byte replay through source-specific intake",
                        "Data-sheet row identity",
                        "physical-track identity",
                        "workbook-to-NERDm micrograph identity binding",
                        "source machine-setting power and scan-speed semantics",
                        "row-level width/depth measurement values",
                    ],
                    "excluded_scope": [
                        "calibrated actual laser power",
                        "cross-experiment calibration transfer",
                        "cross-source comparability",
                        "protocol equivalence",
                        "independent replication across dataset families",
                        "predictive validation",
                        "causality",
                        "optimization",
                        "engineering use",
                    ],
                    "assumptions": [],
                    "scientific_status_promoted": False,
                },
                "comparability": {
                    "status": "not_assessed",
                    "requirements": [
                        "separate provenance-aware Comparability Engine assessment required"
                    ],
                    "limitations": [
                        "matching AMMT/power/speed labels do not establish exact experiment identity"
                    ],
                    "comparison_performed": False,
                    "comparable_claimed": False,
                },
                "limitations": [
                    "195 W is a machine setting as stated by the source README, not calibrated actual power.",
                    "Micrograph identity is metadata-bound here; image bytes are not attached to this packet.",
                    "Summary-sheet uncertainty is not back-propagated into row measurements.",
                    "Issue #76 remains ineligible from this source-specific intake.",
                ],
                "authority": {
                    "empirical_evidence_created": True,
                    "scientific_status_promoted": False,
                    "downstream_use_authorized": False,
                    "planning_metadata_only": False,
                    "row_level_measurement_authority": True,
                    "authority_source": "domain_verifier",
                },
            }
        )
        packets.append(packet)

    return packets


def build_mds2_2923_ammt_195_800_validation_material(
    *,
    workbook_bytes: bytes,
    readme_bytes: bytes,
    nerdm_metadata_bytes: bytes,
) -> list[dict[str, Any]]:
    """Return packet/artifact/expectation material without issuing its trust-root digest."""

    packets = build_mds2_2923_ammt_195_800_evidence_packets(
        workbook_bytes=workbook_bytes,
        readme_bytes=readme_bytes,
        nerdm_metadata_bytes=nerdm_metadata_bytes,
    )
    artifacts = {
        "mds2-workbook": workbook_bytes,
        "mds2-readme": readme_bytes,
        "mds2-nerdm": nerdm_metadata_bytes,
    }
    material: list[dict[str, Any]] = []
    for packet in packets:
        expected = {
            "provider_id": "nist-mds2-2923-row-provider",
            "subject_identities": copy.deepcopy(packet["subject"]["identities"]),
            "source_bindings": copy.deepcopy(packet["source_bindings"]),
            "result_units": {
                item["result_id"]: item["unit"] for item in packet["results"]
            },
            "calibration_status": "unknown",
            "uncertainty_status_by_id": {
                item["uncertainty_id"]: item["status"]
                for item in packet["uncertainty"]
            },
            "existing_source_family_ids": [],
            "packet_sha256": packet["packet_sha256"],
        }
        material.append(
            {
                "evidence_id": packet["evidence_id"],
                "packet": packet,
                "artifacts": dict(artifacts),
                "expected": expected,
            }
        )
    return material


__all__ = [
    "In625CompetencyEvidenceError",
    "MDS2_BENCHMARK_ADAPTER_ID",
    "build_mds2_2923_ammt_195_800_evidence_packets",
    "build_mds2_2923_ammt_195_800_validation_material",
]
