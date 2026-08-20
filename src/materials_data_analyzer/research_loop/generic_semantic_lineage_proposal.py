"""Proposal-only bridge from generic structure to strict scientific contracts.

The bridge records lexical/structural hints and unresolved requirements. It never turns
headers, filenames, rows, repeated values, or provenance candidate identifiers into
accepted materials semantics or physical lineage. Exact proposal hashes can be reviewed
later through the existing human-review release contract.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .kernel import ResearchLoopError
from .scientific_review_release import (
    ScientificReviewReleaseError,
    build_review_request,
    validate_review_request,
)

GENERIC_SEMANTIC_LINEAGE_PROPOSAL_SCHEMA_VERSION = "1.0"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_HINTS = {
    "identity_like",
    "replicate_like",
    "time_like",
    "frequency_like",
    "temperature_like",
    "measurement_like",
}
_REQUIRED_MEASUREMENT_FIELDS = [
    "material",
    "sample_id",
    "property_name",
    "value_column",
    "unit",
    "method",
    "instrument_model",
    "source_id",
    "record_locator",
]
_REQUIRED_LINEAGE_FIELDS = [
    "source_id",
    "specimen_id",
    "acquisition_id",
    "measurement_id",
]
_UNRESOLVED_SCIENTIFIC_CONTEXT = [
    "calibration_status",
    "process_signature",
    "standard_uncertainty",
]


class GenericSemanticLineageProposalError(ResearchLoopError):
    """Raised when a proposal cannot preserve the generic structural boundary."""


def _canonical_sha(value: object) -> str:
    try:
        body = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GenericSemanticLineageProposalError(
            "proposal content must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(body).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise GenericSemanticLineageProposalError(
            f"{field} must be non-empty trimmed text"
        )
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if not _SHA_RE.fullmatch(text):
        raise GenericSemanticLineageProposalError(
            f"{field} must be lowercase SHA-256"
        )
    return text


def _validate_generic_structure(structure: Mapping[str, Any]) -> str:
    if not isinstance(structure, Mapping):
        raise GenericSemanticLineageProposalError("structure must be an object")
    artifact_sha = _sha(
        structure.get("artifact_sha256"),
        "structure.artifact_sha256",
    )
    required_false = {
        "accepted_for_analysis": structure.get("accepted_for_analysis"),
        "measurement_semantics_interpreted": structure.get(
            "measurement_semantics_interpreted"
        ),
        "units_interpreted": structure.get("units_interpreted"),
        "sample_identity_inferred": structure.get("sample_identity_inferred"),
        "replicate_independence_inferred": structure.get(
            "replicate_independence_inferred"
        ),
        "calibration_semantics_interpreted": structure.get(
            "calibration_semantics_interpreted"
        ),
        "scientific_support_established": structure.get(
            "scientific_support_established"
        ),
        "scientific_status_changed": structure.get("scientific_status_changed"),
    }
    invalid = sorted(
        key for key, value in required_false.items() if value is not False
    )
    if invalid:
        raise GenericSemanticLineageProposalError(
            "generic structure violated proposal-only boundary: " + ", ".join(invalid)
        )
    profiles = structure.get("column_profiles")
    if not isinstance(profiles, list):
        raise GenericSemanticLineageProposalError(
            "generic structure column_profiles must be a list"
        )
    return artifact_sha


def _column_candidates(structure: Mapping[str, Any]) -> list[dict[str, Any]]:
    profiles = structure["column_profiles"]
    result: list[dict[str, Any]] = []
    for profile in profiles:
        if not isinstance(profile, Mapping):
            raise GenericSemanticLineageProposalError(
                "column profile must be an object"
            )
        index = profile.get("column_index")
        header = profile.get("header_candidate")
        hints = profile.get("header_semantic_hints_proposal_only")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise GenericSemanticLineageProposalError(
                "column_index must be a non-negative integer"
            )
        if not isinstance(header, str):
            raise GenericSemanticLineageProposalError(
                "header_candidate must be text"
            )
        if not isinstance(hints, list) or any(
            not isinstance(item, str) or item not in _ALLOWED_HINTS
            for item in hints
        ):
            raise GenericSemanticLineageProposalError(
                "column semantic hints are invalid"
            )
        result.append(
            {
                "column_index": index,
                "source_header_candidate": header,
                "lexical_structural_hints_proposal_only": sorted(set(hints)),
                "numeric_count": profile.get("numeric_count"),
                "text_count": profile.get("text_count"),
                "blank_count": profile.get("blank_count"),
                "constant_nonblank_signal": profile.get(
                    "constant_nonblank_signal"
                ),
                "candidate_role_is_accepted_semantics": False,
                "header_is_authoritative_scientific_metadata": False,
            }
        )
    return result


def _hint_columns(columns: list[dict[str, Any]], hint: str) -> list[int]:
    return [
        int(item["column_index"])
        for item in columns
        if hint in item["lexical_structural_hints_proposal_only"]
    ]


def build_generic_semantic_lineage_proposal(
    *,
    candidate_id: str,
    structure: Mapping[str, Any],
) -> dict[str, Any]:
    """Build exact proposal artifacts and a scoped scientific-intake review request."""
    candidate = _text(candidate_id, "candidate_id")
    evidence_sha = _validate_generic_structure(structure)
    intake_sha = _canonical_sha(structure)
    columns = _column_candidates(structure)

    semantic_proposal: dict[str, Any] = {
        "schema_version": GENERIC_SEMANTIC_LINEAGE_PROPOSAL_SCHEMA_VERSION,
        "candidate_id": candidate,
        "candidate_id_is_scientific_identity": False,
        "evidence_artifact_sha256": evidence_sha,
        "structural_intake_sha256": intake_sha,
        "columns": columns,
        "candidate_identity_columns": _hint_columns(columns, "identity_like"),
        "candidate_replicate_columns": _hint_columns(columns, "replicate_like"),
        "candidate_time_columns": _hint_columns(columns, "time_like"),
        "candidate_frequency_columns": _hint_columns(columns, "frequency_like"),
        "candidate_temperature_columns": _hint_columns(
            columns,
            "temperature_like",
        ),
        "candidate_measurement_columns": _hint_columns(
            columns,
            "measurement_like",
        ),
        "unresolved_normalized_measurement_fields": list(
            _REQUIRED_MEASUREMENT_FIELDS
        ),
        "unresolved_scientific_context_fields": list(
            _UNRESOLVED_SCIENTIFIC_CONTEXT
        ),
        "material_identity_inferred": False,
        "sample_identity_inferred": False,
        "property_semantics_inferred": False,
        "units_inferred": False,
        "method_inferred": False,
        "instrument_model_inferred": False,
        "calibration_inferred": False,
        "header_hints_are_authoritative": False,
        "proposal_accepted": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    semantic_sha = _canonical_sha(semantic_proposal)

    lineage_proposal: dict[str, Any] = {
        "schema_version": GENERIC_SEMANTIC_LINEAGE_PROPOSAL_SCHEMA_VERSION,
        "candidate_id": candidate,
        "candidate_id_is_specimen_identity": False,
        "evidence_artifact_sha256": evidence_sha,
        "structural_intake_sha256": intake_sha,
        "semantic_proposal_sha256": semantic_sha,
        "identity_like_source_columns_proposal_only": _hint_columns(
            columns,
            "identity_like",
        ),
        "replicate_like_source_columns_proposal_only": _hint_columns(
            columns,
            "replicate_like",
        ),
        "unresolved_observation_lineage_fields": list(_REQUIRED_LINEAGE_FIELDS),
        "specimen_id_assigned": False,
        "acquisition_id_assigned": False,
        "measurement_id_assigned": False,
        "build_or_synthesis_id_assigned": False,
        "material_lot_id_assigned": False,
        "filename_or_row_number_used_as_identity": False,
        "replicate_independence_established": False,
        "independence_level": "unresolved",
        "naive_row_count_is_independent_n": False,
        "proposal_accepted": False,
        "scientific_status_changed": False,
    }
    lineage_sha = _canonical_sha(lineage_proposal)

    review_request = build_review_request(
        candidate_id=candidate,
        evidence_artifact_sha256=evidence_sha,
        semantic_contract_sha256=semantic_sha,
        lineage_sha256=lineage_sha,
        intake_artifact_sha256=intake_sha,
        requested_uses=["scientific_intake"],
    )

    proposal: dict[str, Any] = {
        "schema_version": GENERIC_SEMANTIC_LINEAGE_PROPOSAL_SCHEMA_VERSION,
        "candidate_id": candidate,
        "candidate_identifier_is_provenance_only": True,
        "evidence_artifact_sha256": evidence_sha,
        "structural_intake_sha256": intake_sha,
        "semantic_proposal": semantic_proposal,
        "semantic_proposal_sha256": semantic_sha,
        "lineage_proposal": lineage_proposal,
        "lineage_proposal_sha256": lineage_sha,
        "review_request": review_request,
        "review_request_created": True,
        "review_request_scope": ["scientific_intake"],
        "human_review_decision_created": False,
        "human_review_blocker_released": False,
        "next_actions": [
            "domain_semantic_mapping_required",
            "sample_lineage_recovery_required",
            "units_method_instrument_evidence_required",
            "calibration_or_uncertainty_evidence_required",
            "human_scientific_review_required",
        ],
        "proposal_can_instantiate_normalized_measurement": False,
        "proposal_can_instantiate_observation_lineage": False,
        "accepted_for_analysis": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    proposal["proposal_packet_sha256"] = _canonical_sha(proposal)
    return proposal


def verify_generic_semantic_lineage_proposal(
    *,
    structure: Mapping[str, Any],
    proposal: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute proposal/review bindings and fail closed on mutated content."""
    if not isinstance(proposal, Mapping):
        raise GenericSemanticLineageProposalError("proposal must be an object")
    candidate = _text(
        proposal.get("candidate_id"),
        "proposal.candidate_id",
    )
    expected = build_generic_semantic_lineage_proposal(
        candidate_id=candidate,
        structure=structure,
    )
    try:
        validate_review_request(proposal.get("review_request"))
    except ScientificReviewReleaseError as exc:
        raise GenericSemanticLineageProposalError(
            "proposal review request is invalid"
        ) from exc
    if dict(proposal) != expected:
        raise GenericSemanticLineageProposalError(
            "proposal bytes differ from exact structure-bound canonical proposal"
        )
    return {
        "candidate_id": candidate,
        "proposal_packet_sha256": expected["proposal_packet_sha256"],
        "review_request_id": expected["review_request"]["review_request_id"],
        "exact_structure_binding_verified": True,
        "human_review_blocker_released": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "GENERIC_SEMANTIC_LINEAGE_PROPOSAL_SCHEMA_VERSION",
    "GenericSemanticLineageProposalError",
    "build_generic_semantic_lineage_proposal",
    "verify_generic_semantic_lineage_proposal",
]
