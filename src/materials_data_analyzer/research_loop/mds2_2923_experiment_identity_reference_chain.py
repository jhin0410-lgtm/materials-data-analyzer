"""Build a fail-closed experiment-identity/reference graph for NIST mds2-2923."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .nist_mds2_2923_reference_chain_policy import ACTION_CLASS

IMPLEMENTATION_ID = "mds2-2923-experiment-identity-reference-chain-v1"
FACTORY_ID = "bounded-provenance-reference-graph-v1"
REQUIRED_VERIFIED_PRIMITIVES = (
    "exact_mds2_metadata_binding",
    "exact_naderi_reference_claim_acquisition",
    "official_dataset_publication_association_extraction",
    "bounded_reference_graph_construction",
    "non_transitive_epistemic_edge_classification",
)
NEXT_ACTION_CLASS = "weaver_2021_spot_size_full_text_derived_acquisition"
WEAVER_DOI = "10.1016/j.jmapro.2021.10.053"
NADERI_DOI = "10.1007/s40192-022-00289-w"
LANE_DOI = "10.1007/s40192-020-00169-1"
AMMT_DESIGN_TITLE = "Design, Developments, and Results from the NIST Additive Manufacturing Metrology Testbed (AMMT)"
WEAVER_TITLE = "Laser spot size and scaling laws for laser beam additive manufacturing"


class Mds22923ExperimentIdentityReferenceChainError(ValueError):
    """Raised when the reference graph would exceed authenticated evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Mds22923ExperimentIdentityReferenceChainError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_hash(
    report: Mapping[str, Any],
    field: str = "report_sha256_without_self_field",
) -> str:
    digest = report.get(field)
    _require(isinstance(digest, str) and len(digest) == 64, f"{field} is missing")
    unsigned = dict(report)
    unsigned.pop(field, None)
    _require(_canonical_sha(unsigned) == digest, f"{field} is invalid")
    return digest


def _metadata_description_text(metadata: Mapping[str, Any]) -> str:
    """Accept only the historical string fixture or exact one-element NERDm list shape."""
    description = metadata.get("description")
    if isinstance(description, str):
        _require(bool(description), "NERDm description is missing")
        return description
    _require(
        isinstance(description, list)
        and len(description) == 1
        and isinstance(description[0], str)
        and bool(description[0]),
        "NERDm description must be text or one non-empty text item",
    )
    return description[0]


def _metadata_associations(nerdm_metadata_bytes: bytes) -> tuple[str, list[str]]:
    try:
        metadata = json.loads(nerdm_metadata_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Mds22923ExperimentIdentityReferenceChainError(
            "NERDm metadata must be UTF-8 JSON"
        ) from exc
    _require(isinstance(metadata, dict), "NERDm metadata root must be an object")
    identifiers = [metadata.get(key) for key in ("@id", "ediid", "doi")]
    _require(
        any(
            isinstance(value, str) and "mds2-2923" in value.lower()
            for value in identifiers
        ),
        "NERDm metadata does not identify mds2-2923",
    )
    description = _metadata_description_text(metadata)
    normalized = re.sub(r"\s+", " ", description)
    associations = [
        doi
        for doi in (WEAVER_DOI, NADERI_DOI)
        if f"https://doi.org/{doi}" in normalized or doi in normalized
    ]
    _require(
        associations == [WEAVER_DOI, NADERI_DOI],
        "NERDm description does not preserve both expected publication associations",
    )
    return hashlib.sha256(nerdm_metadata_bytes).hexdigest(), associations


def _claim_map(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = report.get("claims")
    _require(isinstance(raw, list), "reference evidence claims are missing")
    result: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        _require(isinstance(item, Mapping), "reference claim must be an object")
        claim_id = item.get("claim_id")
        _require(
            isinstance(claim_id, str) and claim_id,
            "reference claim identity missing",
        )
        _require(claim_id not in result, "reference claim identity repeated")
        result[claim_id] = item
    return result


def _find_multisource_source(
    report: Mapping[str, Any],
    source_id: str,
) -> Mapping[str, Any]:
    sources = report.get("sources")
    _require(isinstance(sources, list), "multisource evidence sources are missing")
    matches = [
        item
        for item in sources
        if isinstance(item, Mapping) and item.get("source_id") == source_id
    ]
    _require(len(matches) == 1, f"multisource source {source_id} is not unique")
    return matches[0]


def _find_discovery_candidate(
    report: Mapping[str, Any],
    *,
    doi: str | None = None,
    title_token: str | None = None,
) -> Mapping[str, Any]:
    candidates = report.get("candidates")
    _require(isinstance(candidates, list), "source discovery candidates are missing")
    matches: list[Mapping[str, Any]] = []
    for item in candidates:
        if not isinstance(item, Mapping):
            continue
        url = str(item.get("url", ""))
        label = str(item.get("link_label", ""))
        if doi is not None and doi in url:
            matches.append(item)
        elif title_token is not None and title_token.lower() in (
            url + " " + label
        ).lower():
            matches.append(item)
    _require(len(matches) == 1, "required official-index candidate is not unique")
    return matches[0]


def build_mds2_2923_experiment_identity_reference_chain(
    *,
    nerdm_metadata_bytes: bytes,
    nist_intake: Mapping[str, Any],
    naderi_reference_evidence: Mapping[str, Any],
    multisource_evidence: Mapping[str, Any],
    source_discovery_report: Mapping[str, Any],
    calibration_candidate_assessment: Mapping[str, Any],
) -> dict[str, Any]:
    """Construct a provenance graph without transitive identity/power promotion."""
    _validate_hash(nist_intake)
    _validate_hash(naderi_reference_evidence)
    _validate_hash(multisource_evidence)
    _validate_hash(source_discovery_report)
    _validate_hash(calibration_candidate_assessment)

    source = nist_intake.get("source")
    _require(isinstance(source, Mapping), "mds2 scientific-intake source is missing")
    _require(
        source.get("product_id") == "mds2-2923",
        "scientific intake product drifted",
    )
    metadata_sha, associations = _metadata_associations(nerdm_metadata_bytes)
    _require(
        metadata_sha == source.get("nerdm_metadata_sha256"),
        "reference-chain metadata bytes do not match scientific intake",
    )
    semantics = nist_intake.get("measurement_semantics")
    _require(
        isinstance(semantics, Mapping)
        and semantics.get("laser_power") == "machine_setting_as_stated_by_README"
        and semantics.get("calibration_conversion_performed") is False,
        "mds2 machine-setting power semantics drifted",
    )
    issue76 = nist_intake.get("issue_76")
    _require(
        isinstance(issue76, Mapping)
        and issue76.get("eligible") is False
        and issue76.get("exact_target_cells_satisfied") == 0,
        "Issue #76 was already promoted before reference-chain assessment",
    )

    support = nist_intake.get("machine_power_speed_support")
    _require(isinstance(support, list), "mds2 support table is missing")
    support195 = [
        item
        for item in support
        if isinstance(item, Mapping)
        and item.get("machine") == "AMMT"
        and item.get("laser_power_w_machine_setting") == 195.0
        and item.get("scan_speed_mm_s_machine_setting") == 800.0
    ]
    support180 = [
        item
        for item in support
        if isinstance(item, Mapping)
        and item.get("machine") == "AMMT"
        and item.get("laser_power_w_machine_setting") == 180.0
        and item.get("scan_speed_mm_s_machine_setting") == 800.0
    ]
    _require(
        len(support195) == 1 and len(support180) == 1,
        "mds2 AMMT 180/195 support drifted",
    )
    _require(
        support195[0].get("measurement_count") == 18
        and support195[0].get("independent_physical_track_count") == 18
        and support195[0].get("spot_diameter_level_count") == 7,
        "mds2 AMMT 195/800 support drifted",
    )
    measurements = nist_intake.get("measurements")
    _require(isinstance(measurements, list), "mds2 measurements are missing")
    spots195 = sorted(
        {
            float(item["estimated_or_measured_spot_diameter_um"])
            for item in measurements
            if isinstance(item, Mapping)
            and item.get("machine") == "AMMT"
            and item.get("laser_power_w_machine_setting") == 195.0
            and item.get("scan_speed_mm_s_machine_setting") == 800.0
        }
    )
    _require(
        len(spots195) == 7 and spots195[0] == 50.0 and spots195[-1] == 256.0,
        "mds2 AMMT 195/800 spot signature drifted",
    )

    _require(
        naderi_reference_evidence.get("acquisition_status")
        == "exact_naderi_reference_chain_evidence_acquired"
        and naderi_reference_evidence.get("all_claims_matched") is True
        and naderi_reference_evidence.get("scientific_status_changed") is False,
        "Naderi reference evidence is not exact/complete",
    )
    claims = _claim_map(naderi_reference_evidence)
    required_claims = {
        "naderi-ammt-in625-weaver-detail-reference",
        "naderi-reference-7-weaver-spot-size-paper",
        "naderi-reference-31-ammt-design",
        "naderi-reference-32-lane-in625-protocol",
    }
    _require(
        required_claims == set(claims)
        and all(claims[item].get("matched") is True for item in required_claims),
        "Naderi reference-chain claims are incomplete",
    )

    weaver_meta = _find_multisource_source(
        multisource_evidence,
        "weaver-2021-spot-size-scaling-metadata",
    )
    lane = _find_multisource_source(
        multisource_evidence,
        "lane-2020-melt-pool-geometry",
    )
    _require(
        weaver_meta.get("source_class") == "primary_paper_metadata"
        and weaver_meta.get("doi") == WEAVER_DOI,
        "Weaver evidence is not the expected metadata-only authority",
    )
    _require(
        lane.get("source_class") == "primary_paper"
        and lane.get("doi") == LANE_DOI,
        "Lane 2020 protocol evidence identity drifted",
    )
    weaver_candidate = _find_discovery_candidate(
        source_discovery_report,
        doi=WEAVER_DOI,
    )
    design_candidate = _find_discovery_candidate(
        source_discovery_report,
        title_token=(
            "design-developments-and-results-nist-additive-manufacturing-"
            "metrology-testbed-ammt"
        ),
    )
    _require(
        weaver_candidate.get("acquisition_authorized") is False
        and design_candidate.get("acquisition_authorized") is False,
        "reference identifiers already gained acquisition authority",
    )
    _require(
        calibration_candidate_assessment.get("experiment_specific_bridge", {}).get(
            "bridge_established"
        )
        is False
        and calibration_candidate_assessment.get("evidence_scope", {}).get(
            "digital_camera_in_situ_calibration_methodology_established"
        )
        is True,
        "calibration predecessor boundary drifted",
    )

    nodes = [
        {
            "node_id": "dataset:mds2-2923",
            "node_type": "authoritative_dataset",
            "authority": "row_level_only_for_workbook_measurements",
        },
        {
            "node_id": f"paper:{WEAVER_DOI}",
            "node_type": "primary_paper",
            "full_text_acquired": False,
        },
        {
            "node_id": f"paper:{NADERI_DOI}",
            "node_type": "primary_paper",
            "full_text_acquired": True,
        },
        {
            "node_id": f"paper:{LANE_DOI}",
            "node_type": "primary_paper",
            "full_text_acquired": True,
        },
        {
            "node_id": "paper:nist-ammt-design-2016",
            "node_type": "primary_paper",
            "full_text_acquired_in_reference_chain": False,
        },
        {
            "node_id": "paper:nist-laser-calibration-2022",
            "node_type": "primary_paper",
            "full_text_acquired": True,
        },
        {
            "node_id": "condition:mds2-ammt-195w-800",
            "node_type": "dataset_condition_subset",
            "measurement_rows": 18,
            "physical_tracks": 18,
            "spot_levels_um": spots195,
        },
    ]
    edges = [
        {
            "edge_id": "mds2-associated-with-weaver",
            "from": "dataset:mds2-2923",
            "to": f"paper:{WEAVER_DOI}",
            "classification": "official_dataset_publication_association",
            "authority_effect": "dataset_level_association_only",
            "exact_row_identity_established": False,
            "provenance_sha256": metadata_sha,
        },
        {
            "edge_id": "mds2-associated-with-naderi",
            "from": "dataset:mds2-2923",
            "to": f"paper:{NADERI_DOI}",
            "classification": "official_dataset_publication_association",
            "authority_effect": "dataset_level_association_only",
            "exact_row_identity_established": False,
            "provenance_sha256": metadata_sha,
        },
        {
            "edge_id": "naderi-in625-ammt-details-from-weaver-7",
            "from": f"paper:{NADERI_DOI}",
            "to": f"paper:{WEAVER_DOI}",
            "classification": "primary_paper_experiment_detail_reference",
            "authority_effect": "supports_reference_chain_not_transitive_identity",
            "exact_row_identity_established": False,
            "claim_id": "naderi-ammt-in625-weaver-detail-reference",
        },
        {
            "edge_id": "naderi-ammt-platform-reference-31",
            "from": f"paper:{NADERI_DOI}",
            "to": "paper:nist-ammt-design-2016",
            "classification": "same_platform_design_reference",
            "authority_effect": "platform_relevance_only",
            "exact_experiment_identity_established": False,
            "claim_id": "naderi-reference-31-ammt-design",
        },
        {
            "edge_id": "naderi-in625-protocol-reference-32",
            "from": f"paper:{NADERI_DOI}",
            "to": f"paper:{LANE_DOI}",
            "classification": "primary_paper_protocol_reference",
            "authority_effect": "protocol_relevance_only",
            "protocol_equivalence_established": False,
            "claim_id": "naderi-reference-32-lane-in625-protocol",
        },
        {
            "edge_id": "mds2-195-condition-signature-compatible-with-naderi",
            "from": "condition:mds2-ammt-195w-800",
            "to": f"paper:{NADERI_DOI}",
            "classification": "condition_signature_match",
            "authority_effect": "candidate_subset_identity_only",
            "condition_signature_match": True,
            "exact_row_identity_established": False,
        },
    ]
    edge_sha = _canonical_sha(edges)

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "action_class": ACTION_CLASS,
        "assessment_status": (
            "reference_chain_built_and_missing_full_text_frontier_identified"
        ),
        "input_bindings": {
            "nerdm_metadata_sha256": metadata_sha,
            "nist_intake_sha256": nist_intake[
                "report_sha256_without_self_field"
            ],
            "naderi_reference_evidence_sha256": naderi_reference_evidence[
                "report_sha256_without_self_field"
            ],
            "multisource_evidence_sha256": multisource_evidence[
                "report_sha256_without_self_field"
            ],
            "source_discovery_sha256": source_discovery_report[
                "report_sha256_without_self_field"
            ],
            "calibration_candidate_assessment_sha256": calibration_candidate_assessment[
                "report_sha256_without_self_field"
            ],
        },
        "dataset_publication_associations": associations,
        "reference_graph": {
            "nodes": nodes,
            "edges": edges,
            "edges_sha256": edge_sha,
            "transitive_authority_promotion_allowed": False,
        },
        "condition_signature": {
            "mds2_ammt_195w_800_measurement_rows": 18,
            "mds2_ammt_195w_800_physical_tracks": 18,
            "mds2_ammt_195w_800_spot_levels_um": spots195,
            "naderi_reported_ammt_power_w": 195.0,
            "naderi_reported_scan_speed_mm_s": 800.0,
            "naderi_reported_spot_range_um": [50.0, 256.0],
            "signature_match": True,
            "exact_row_identity_established": False,
        },
        "experiment_identity": {
            "dataset_to_weaver_association_established": True,
            "dataset_to_naderi_association_established": True,
            "naderi_to_weaver_experiment_detail_reference_established": True,
            "ammt_platform_reference_established": True,
            "lane_protocol_reference_established": True,
            "exact_mds2_rows_to_weaver_experiment_established": False,
            "exact_mds2_experiment_identity_established": False,
        },
        "calibration_and_protocol_gate": {
            "weaver_full_text_acquired": False,
            "machine_setting_to_calibrated_power_relation_established": False,
            "spot_size_transfer_authorized": False,
            "protocol_equivalence_established": False,
            "uncertainty_transfer_authorized": False,
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_cross_source_validation_authorized": False,
            "cross_machine_pooling_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
        },
        "missing_evidence": [
            {
                "code": "weaver_primary_full_text_not_acquired",
                "doi": WEAVER_DOI,
                "title": WEAVER_TITLE,
                "reason": (
                    "Both official mds2 metadata and Naderi reference 7 point to "
                    "Weaver, but the current authenticated evidence package contains "
                    "only NIST metadata/abstract authority for this paper."
                ),
            }
        ],
        "new_verified_information": True,
        "scientific_status_changed": False,
        "positive_scientific_closeout": False,
        "global_evidence_unavailability_claimed": False,
        "next_action": {
            "action_class": NEXT_ACTION_CLASS,
            "objective": (
                "Acquire the exact Weaver/Heigel/Lane primary full text only under "
                "separately derived provenance authority, then test whether it "
                "explicitly maps the mds2-2923 AMMT 195 W / 800 mm/s rows, "
                "laser-power calibration semantics, spot-size calibration, and "
                "cross-section protocol."
            ),
            "candidate": {
                "doi": WEAVER_DOI,
                "title": WEAVER_TITLE,
                "official_index_candidate_id": weaver_candidate.get("candidate_id"),
                "official_index_rank": weaver_candidate.get("rank"),
                "discovered_url": weaver_candidate.get("url"),
                "acquisition_authorized": False,
            },
            "caller_authored_url_authorized": False,
            "automatic_acquisition_authorized": False,
            "unrestricted_search_authorized": False,
        },
    }
    report["report_sha256_without_self_field"] = _canonical_sha(report)
    return report


__all__ = [
    "ACTION_CLASS",
    "FACTORY_ID",
    "IMPLEMENTATION_ID",
    "Mds22923ExperimentIdentityReferenceChainError",
    "NEXT_ACTION_CLASS",
    "REQUIRED_VERIFIED_PRIMITIVES",
    "build_mds2_2923_experiment_identity_reference_chain",
]
