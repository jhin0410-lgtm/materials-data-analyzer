"""Prepare an exact-byte human-review packet for the acquired Zenodo IN625 supplement.

The output is intentionally a *proposal* and review request, never a review decision.  It
clusters archive paths for reviewer navigation, binds selected bounded text witnesses by
SHA-256, and preserves all unresolved semantic and lineage fields.  A reviewer release can
therefore remove only the human-review blocker for the exact request; it cannot silently
convert path names or file-name tokens into sample identity, calibration, or support.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from .kernel import ResearchLoopError
from .scientific_review_release import build_review_request, canonical_sha256

IN625_ZENODO_REVIEW_PREPARATION_SCHEMA_VERSION = "1.0"
IN625_ZENODO_RECORD_ID = "20503603"
IN625_ZENODO_DATASET_DOI = "10.5281/zenodo.20503603"


class In625ZenodoReviewPreparationError(ResearchLoopError):
    """Raised when the live supplement records cannot be bound into a review packet."""


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise In625ZenodoReviewPreparationError(f"{field} must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise In625ZenodoReviewPreparationError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or text != text.lower() or any(c not in "0123456789abcdef" for c in text):
        raise In625ZenodoReviewPreparationError(f"{field} must be lowercase SHA-256")
    return text


def _archive_family(path: str) -> str:
    parts = PurePosixPath(path).parts
    if len(parts) < 2 or parts[0] != "Dataset":
        return "archive_root_or_unclassified"
    if parts[1] == "Mechanical testing" and len(parts) >= 3:
        return f"Mechanical testing/{parts[2]}"
    return parts[1]


def prepare_in625_zenodo_review_packet(
    *,
    candidate: Mapping[str, Any],
    use_ceiling: Mapping[str, Any],
    live_summary: Mapping[str, Any],
    archive_inventory: Mapping[str, Any],
    selected_text_readout: Mapping[str, Any],
) -> dict[str, Any]:
    """Build proposal artifacts and an exact review request without approving anything."""
    candidate = dict(_mapping(candidate, "candidate"))
    use_ceiling = dict(_mapping(use_ceiling, "use_ceiling"))
    summary = dict(_mapping(live_summary, "live_summary"))
    inventory = dict(_mapping(archive_inventory, "archive_inventory"))
    readout = dict(_mapping(selected_text_readout, "selected_text_readout"))

    candidate_id = _text(candidate.get("candidate_id"), "candidate.candidate_id")
    artifact_sha = _sha(candidate.get("artifact_sha256"), "candidate.artifact_sha256")
    if candidate.get("provider") != "zenodo" or candidate.get("source_id") != f"zenodo:{IN625_ZENODO_RECORD_ID}":
        raise In625ZenodoReviewPreparationError("candidate is not the pinned Zenodo IN625 record")
    if summary.get("record_id") != IN625_ZENODO_RECORD_ID or summary.get("doi") != IN625_ZENODO_DATASET_DOI:
        raise In625ZenodoReviewPreparationError("live summary does not match pinned Zenodo IN625 record")
    if summary.get("evidence_candidate_id") != candidate_id or use_ceiling.get("candidate_id") != candidate_id:
        raise In625ZenodoReviewPreparationError("candidate identity differs across live artifacts")
    if inventory.get("archive_sha256") != artifact_sha or readout.get("archive_sha256") != artifact_sha:
        raise In625ZenodoReviewPreparationError("archive bytes differ across review inputs")
    for source, field in (
        (candidate, "candidate"),
        (use_ceiling, "use_ceiling"),
        (summary, "live_summary"),
        (inventory, "archive_inventory"),
        (readout, "selected_text_readout"),
    ):
        if source.get("scientific_status_changed") is not False:
            raise In625ZenodoReviewPreparationError(f"{field} violates scientific-status boundary")
    if inventory.get("bulk_extraction_performed") is not False or readout.get("bulk_extraction_performed") is not False:
        raise In625ZenodoReviewPreparationError("review preparation requires bounded no-bulk-extraction inputs")

    members = inventory.get("members")
    if not isinstance(members, list) or not members:
        raise In625ZenodoReviewPreparationError("archive inventory must contain members")
    families: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"member_count": 0, "suffixes": set(), "paths": []}
    )
    inventory_by_path: dict[str, Mapping[str, Any]] = {}
    for index, raw_member in enumerate(members):
        member = _mapping(raw_member, f"archive_inventory.members[{index}]")
        path = _text(member.get("path"), "archive member path")
        if path in inventory_by_path:
            raise In625ZenodoReviewPreparationError("duplicate archive member path")
        inventory_by_path[path] = member
        if member.get("is_directory") is True:
            continue
        family = _archive_family(path)
        families[family]["member_count"] += 1
        suffix = member.get("suffix")
        if isinstance(suffix, str) and suffix:
            families[family]["suffixes"].add(suffix)
        families[family]["paths"].append(path)

    read_members = readout.get("members")
    if not isinstance(read_members, list):
        raise In625ZenodoReviewPreparationError("selected_text_readout.members must be a list")
    text_witnesses: list[dict[str, Any]] = []
    for index, raw_member in enumerate(read_members):
        member = _mapping(raw_member, f"selected_text_readout.members[{index}]")
        path = _text(member.get("path"), "selected text path")
        digest = _sha(member.get("sha256"), "selected text sha256")
        inventoried = inventory_by_path.get(path)
        if inventoried is None or inventoried.get("text_sha256") != digest:
            raise In625ZenodoReviewPreparationError("selected text witness differs from inventory")
        text = _text(member.get("text"), "selected text body")
        text_witnesses.append(
            {
                "path": path,
                "archive_family_candidate": _archive_family(path),
                "sha256": digest,
                "size_bytes": member.get("size_bytes"),
                "line_count": member.get("line_count"),
                "text_sha256_reverified": True,
                "text_preview": text[:4000],
                "preview_truncated": len(text) > 4000,
            }
        )

    family_records = []
    for family in sorted(families):
        value = families[family]
        family_records.append(
            {
                "archive_family_candidate": family,
                "member_count": value["member_count"],
                "suffixes": sorted(value["suffixes"]),
                "paths": sorted(value["paths"]),
                "path_group_is_not_validated_measurement_semantics": True,
            }
        )

    blockers = summary.get("remaining_blocker_codes")
    if not isinstance(blockers, list) or not all(isinstance(item, str) and item for item in blockers):
        raise In625ZenodoReviewPreparationError("live summary blocker codes are invalid")
    ceiling_blockers = use_ceiling.get("blocker_codes")
    if not isinstance(ceiling_blockers, list) or not all(isinstance(item, str) and item for item in ceiling_blockers):
        raise In625ZenodoReviewPreparationError("use ceiling blocker codes are invalid")

    semantic_contract = {
        "schema_version": IN625_ZENODO_REVIEW_PREPARATION_SCHEMA_VERSION,
        "contract_kind": "semantic_review_proposal",
        "proposal_only": True,
        "candidate_id": candidate_id,
        "evidence_artifact_sha256": artifact_sha,
        "dataset_doi": IN625_ZENODO_DATASET_DOI,
        "related_article_doi": summary.get("related_article_doi"),
        "evidence_class": candidate.get("evidence_class"),
        "archive_family_candidates": family_records,
        "bounded_text_witnesses": text_witnesses,
        "unresolved_semantic_fields": [
            "measurement_type_per_member",
            "measurement_units_per_column_or_field",
            "instrument_identity_per_measurement_family",
            "calibration_and_reference_state",
            "specimen_code_dictionary",
            "build_orientation_code_dictionary",
            "heat_treatment_code_dictionary",
            "replicate_definition",
            "measurement_direction_and_geometry",
        ],
        "filename_tokens_are_not_sample_identity": True,
        "archive_path_is_not_measurement_semantics": True,
        "scientific_status_changed": False,
    }
    semantic_sha = canonical_sha256(semantic_contract)

    lineage_proposal = {
        "schema_version": IN625_ZENODO_REVIEW_PREPARATION_SCHEMA_VERSION,
        "contract_kind": "experimental_lineage_review_proposal",
        "proposal_only": True,
        "candidate_id": candidate_id,
        "evidence_artifact_sha256": artifact_sha,
        "sample_identity_status": "unresolved",
        "specimen_identity_status": "unresolved",
        "process_run_identity_status": "unresolved",
        "acquisition_identity_status": "unresolved",
        "replicate_independence_status": "unresolved",
        "publication_dataset_relation_verified": summary.get("related_article_relation_verified_from_record"),
        "archive_family_candidates": [item["archive_family_candidate"] for item in family_records],
        "unresolved_lineage_fields": [
            "material_lot_or_feedstock_batch",
            "build_id",
            "specimen_id",
            "orientation",
            "heat_treatment_state",
            "process_run_id",
            "acquisition_id",
            "measurement_id",
            "technical_vs_biological_or_physical_replicate_role",
        ],
        "pseudoreplication_control_required": True,
        "filename_token_inference_authorized": False,
        "scientific_status_changed": False,
    }
    lineage_sha = canonical_sha256(lineage_proposal)

    intake_artifact = {
        "schema_version": IN625_ZENODO_REVIEW_PREPARATION_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "evidence_artifact_sha256": artifact_sha,
        "semantic_contract_sha256": semantic_sha,
        "lineage_sha256": lineage_sha,
        "source_blocker_codes": sorted(set(blockers) | set(ceiling_blockers)),
        "requested_release_scope": ["scientific_intake"],
        "descriptive_analysis_authorized": False,
        "cross_source_comparison_authorized": False,
        "hypothesis_support_authorized": False,
        "external_validation_authorized": False,
        "scientific_status_changed": False,
    }
    intake_sha = canonical_sha256(intake_artifact)
    review_request = build_review_request(
        candidate_id=candidate_id,
        evidence_artifact_sha256=artifact_sha,
        semantic_contract_sha256=semantic_sha,
        lineage_sha256=lineage_sha,
        intake_artifact_sha256=intake_sha,
        requested_uses=["scientific_intake"],
    )

    packet: dict[str, Any] = {
        "schema_version": IN625_ZENODO_REVIEW_PREPARATION_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "evidence_artifact_sha256": artifact_sha,
        "semantic_contract": semantic_contract,
        "semantic_contract_sha256": semantic_sha,
        "lineage_proposal": lineage_proposal,
        "lineage_sha256": lineage_sha,
        "intake_artifact": intake_artifact,
        "intake_artifact_sha256": intake_sha,
        "review_request": review_request,
        "human_review_decision_created": False,
        "human_review_blocker_released": False,
        "scientific_status_changed": False,
        "scientific_support_established": False,
        "issue_76_eligible": False,
    }
    packet["review_packet_sha256"] = canonical_sha256(packet)
    return packet


__all__ = [
    "IN625_ZENODO_DATASET_DOI",
    "IN625_ZENODO_RECORD_ID",
    "IN625_ZENODO_REVIEW_PREPARATION_SCHEMA_VERSION",
    "In625ZenodoReviewPreparationError",
    "prepare_in625_zenodo_review_packet",
]
