"""Convert a verified characterization maturity blocker into a research requirement.

The output is a planning artifact. It does not create empirical evidence, promote a
scientific claim, or authorize an experiment. Authorization remains at the existing
research-loop action boundary.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "characterization_research_evidence_gap"
LEVEL_REQUIREMENTS: dict[str, dict[str, str]] = {
    "L0_software_integration": {
        "requirement_code": "establish_characterization_software_integration",
        "required_evidence": "A reproducible execution through the intended characterization software path.",
        "suggested_action_class": "characterization_software_integration_validation",
    },
    "L1_raw_representation_identity": {
        "requirement_code": "acquire_and_bind_raw_representation",
        "required_evidence": "Raw or lossless measurement representation with stable byte identity and source version binding.",
        "suggested_action_class": "characterization_raw_representation_acquisition",
    },
    "L2_acquisition_provenance_integrity": {
        "requirement_code": "resolve_acquisition_provenance",
        "required_evidence": "Traceable sample, acquisition, and processing lineage without inferred identity fields.",
        "suggested_action_class": "characterization_acquisition_provenance_audit",
    },
    "L3_instrument_calibration_validity": {
        "requirement_code": "validate_instrument_calibration",
        "required_evidence": "Claim-relevant instrument, detector, and calibration metadata with verified validity for the measurement context.",
        "suggested_action_class": "characterization_calibration_validation",
    },
    "L4_method_algorithm_validation": {
        "requirement_code": "validate_characterization_method",
        "required_evidence": "Predeclared method-validation evidence within the represented measurement scope.",
        "suggested_action_class": "characterization_method_validation",
    },
    "L5_material_domain_validation": {
        "requirement_code": "validate_target_material_domain",
        "required_evidence": "Direct evidence from the declared target material, composition, or domain rather than a cross-material proxy.",
        "suggested_action_class": "characterization_target_material_validation",
    },
    "L6_independent_external_validation": {
        "requirement_code": "acquire_independent_external_validation",
        "required_evidence": "A validation source independent of method or model development under an explicit independence contract.",
        "suggested_action_class": "characterization_independent_validation_acquisition",
    },
    "L7_replicated_multisource_support": {
        "requirement_code": "replicate_across_provenance_disjoint_sources",
        "required_evidence": "Replication across provenance-disjoint sources, samples, acquisitions, or facilities as required by the claim.",
        "suggested_action_class": "characterization_multisource_replication",
    },
    "L8_engineering_decision_readiness": {
        "requirement_code": "establish_engineering_decision_readiness",
        "required_evidence": "Independent operational validation of decision thresholds, use conditions, and release criteria.",
        "suggested_action_class": "characterization_engineering_validation",
    },
}


class CharacterizationEvidenceGapError(ValueError):
    """Raised when verified ladder state is insufficient for deterministic planning."""


def _canonical_sha256(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CharacterizationEvidenceGapError(
            "characterization evidence gap must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CharacterizationEvidenceGapError(f"{field} must be a non-empty string")
    return value.strip()


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise CharacterizationEvidenceGapError(f"{field} must be a lowercase SHA-256 digest")
    return text


def build_characterization_evidence_gap(
    ladder_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic next-evidence requirement from verified ladder state."""
    if ladder_state.get("assessment_replayed") is not True:
        raise CharacterizationEvidenceGapError(
            "ladder_state must come from an independently replayed assessment"
        )
    if ladder_state.get("case_id_bound") is not True:
        raise CharacterizationEvidenceGapError("ladder_state must be case-bound")
    if ladder_state.get("source_digests_bound") is not True:
        raise CharacterizationEvidenceGapError("ladder_state must be source-bound")
    if ladder_state.get("subject_modality_bound") is not True:
        raise CharacterizationEvidenceGapError("ladder_state must be modality-bound")
    if ladder_state.get("scientific_status_promoted") is not False:
        raise CharacterizationEvidenceGapError(
            "ladder_state must not promote scientific status"
        )
    if ladder_state.get("downstream_use_authorized") is not False:
        raise CharacterizationEvidenceGapError(
            "ladder_state must not authorize downstream use"
        )

    declaration_sha = _sha(
        ladder_state.get("declaration_sha256"),
        "ladder_state.declaration_sha256",
    )
    assessment_sha = _sha(
        ladder_state.get("assessment_sha256"),
        "ladder_state.assessment_sha256",
    )
    declaration_id = _text(
        ladder_state.get("declaration_id"),
        "ladder_state.declaration_id",
    )
    subject = ladder_state.get("subject")
    if not isinstance(subject, Mapping):
        raise CharacterizationEvidenceGapError("ladder_state.subject must be an object")
    normalized_subject = {
        key: _text(subject.get(key), f"ladder_state.subject.{key}")
        for key in (
            "claim_scope",
            "modality",
            "source_material_domain",
            "target_material_domain",
        )
    }

    first_blocking = ladder_state.get("first_blocking_level")
    highest = ladder_state.get("highest_contiguous_supported_level")
    if highest is not None and highest not in LEVEL_REQUIREMENTS:
        raise CharacterizationEvidenceGapError(
            "ladder_state.highest_contiguous_supported_level is unsupported"
        )
    if first_blocking is not None and first_blocking not in LEVEL_REQUIREMENTS:
        raise CharacterizationEvidenceGapError(
            "ladder_state.first_blocking_level is unsupported"
        )

    if first_blocking is None:
        status = "no_open_characterization_evidence_gap"
        gap: dict[str, Any] | None = None
    else:
        requirement = LEVEL_REQUIREMENTS[first_blocking]
        status = "open_characterization_evidence_gap"
        gap = {
            "blocking_level": first_blocking,
            "requirement_code": requirement["requirement_code"],
            "required_evidence": requirement["required_evidence"],
            "suggested_action_class": requirement["suggested_action_class"],
            "authorization_required_before_execution": True,
        }

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "status": status,
        "source_ladder": {
            "declaration_id": declaration_id,
            "declaration_sha256": declaration_sha,
            "assessment_sha256": assessment_sha,
            "highest_contiguous_supported_level": highest,
            "first_blocking_level": first_blocking,
            "subject": normalized_subject,
        },
        "gap": gap,
        "planning_boundary": {
            "empirical_evidence_created": False,
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "action_execution_authorized": False,
            "requires_existing_research_loop_authorization_boundary": True,
        },
    }
    artifact["artifact_sha256"] = _canonical_sha256(artifact)
    return artifact


__all__ = [
    "ARTIFACT_TYPE",
    "CharacterizationEvidenceGapError",
    "LEVEL_REQUIREMENTS",
    "SCHEMA_VERSION",
    "build_characterization_evidence_gap",
]
