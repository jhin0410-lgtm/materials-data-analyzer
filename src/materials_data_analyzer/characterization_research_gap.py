"""Convert verified characterization maturity into autonomous research requirements.

The output of this module is planning metadata. It is not empirical evidence and it
cannot authorize downstream scientific or engineering use.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

RESEARCH_EVIDENCE_GAP_NAME = "characterization_research_evidence_gap.json"

BLOCKING_LEVEL_REQUIREMENTS: dict[str, dict[str, str]] = {
    "L0_software_integration": {
        "requirement_id": "characterization_software_integration_evidence_required",
        "category": "software_integration",
        "description": (
            "Exercise the intended characterization software path under a reproducible "
            "test without treating software execution as measurement truth."
        ),
    },
    "L1_raw_representation_identity": {
        "requirement_id": "characterization_raw_representation_identity_required",
        "category": "raw_representation_identity",
        "description": (
            "Acquire or recover a raw/lossless representation with stable byte identity "
            "and an explicitly versioned source binding."
        ),
    },
    "L2_acquisition_provenance_integrity": {
        "requirement_id": "characterization_acquisition_provenance_required",
        "category": "acquisition_provenance",
        "description": (
            "Establish sample/acquisition identity and relevant processing lineage without "
            "inferring missing provenance."
        ),
    },
    "L3_instrument_calibration_validity": {
        "requirement_id": "characterization_instrument_calibration_required",
        "category": "instrument_calibration",
        "description": (
            "Establish traceable instrument, detector, and calibration metadata required "
            "for the declared characterization claim."
        ),
    },
    "L4_method_algorithm_validation": {
        "requirement_id": "characterization_method_validation_required",
        "category": "method_validation",
        "description": (
            "Validate the characterization analysis method under a predeclared protocol "
            "within the represented measurement scope."
        ),
    },
    "L5_material_domain_validation": {
        "requirement_id": "characterization_target_material_validation_required",
        "category": "material_domain_validation",
        "description": (
            "Acquire direct evidence in the declared target material/composition/domain; "
            "a cross-material proxy is insufficient."
        ),
    },
    "L6_independent_external_validation": {
        "requirement_id": "characterization_independent_external_validation_required",
        "category": "independent_external_validation",
        "description": (
            "Acquire and evaluate evidence that is independent of method/model development "
            "under an explicit provenance-disjoint independence contract."
        ),
    },
    "L7_replicated_multisource_support": {
        "requirement_id": "characterization_multisource_replication_required",
        "category": "replicated_multisource_support",
        "description": (
            "Replicate the characterization result across explicitly provenance-disjoint "
            "sources, samples, acquisitions, or facilities as required."
        ),
    },
    "L8_engineering_decision_readiness": {
        "requirement_id": "characterization_engineering_validation_required",
        "category": "engineering_decision_readiness",
        "description": (
            "Establish operational validation, decision thresholds, and engineering-use "
            "conditions with independent evidence."
        ),
    },
}


class CharacterizationResearchGapError(ValueError):
    """Raised when verified characterization maturity cannot be mapped safely."""


def _canonical_sha256(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CharacterizationResearchGapError(
            "characterization research gap must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CharacterizationResearchGapError(f"{field} must be a non-empty string")
    return value.strip()


def _manifest_sha256(path: str | Path) -> tuple[Path, str]:
    manifest_path = Path(path)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise CharacterizationResearchGapError(
            "bundle_manifest_path must be a regular non-symlink file"
        )
    resolved = manifest_path.resolve()
    try:
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except OSError as exc:
        raise CharacterizationResearchGapError(
            f"could not read bundle manifest: {resolved}"
        ) from exc
    return resolved, digest


def build_characterization_research_evidence_gap(
    *,
    bundle_manifest_path: str | Path,
    instruments: list[str],
    ladder: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build deterministic next-evidence planning metadata from a verified ladder.

    ``ladder`` must already have passed the independent bundle validator. The manifest
    digest is recomputed from the persisted bytes in this function so callers cannot
    bind the gap to an unrelated but syntactically valid digest. This function never
    interprets the ladder as authorization; it only identifies the next unresolved
    evidence requirement.
    """
    _, manifest_sha = _manifest_sha256(bundle_manifest_path)
    normalized_instruments = sorted(
        {_nonempty_text(item, "instrument").lower() for item in instruments}
    )
    if not normalized_instruments:
        raise CharacterizationResearchGapError("at least one instrument is required")

    if ladder is None:
        core: dict[str, Any] = {
            "schema_version": "1.0",
            "artifact_type": "characterization_research_evidence_gap",
            "bundle_manifest_sha256": manifest_sha,
            "instruments": normalized_instruments,
            "ladder_present": False,
            "ladder_declaration_sha256": None,
            "ladder_assessment_sha256": None,
            "highest_contiguous_supported_level": None,
            "first_blocking_level": None,
            "next_requirement": {
                "requirement_id": "characterization_evidence_maturity_assessment_required",
                "category": "evidence_maturity_assessment",
                "description": (
                    "Obtain an independently replayable L0-L8 characterization evidence "
                    "maturity assessment before inferring a next scientific validation step."
                ),
            },
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "semantic_marker": "planning_requirement_not_scientific_evidence",
        }
    else:
        declaration_sha = _nonempty_text(
            ladder.get("declaration_sha256"), "ladder.declaration_sha256"
        )
        assessment_sha = _nonempty_text(
            ladder.get("assessment_sha256"), "ladder.assessment_sha256"
        )
        for field, digest in (
            ("ladder.declaration_sha256", declaration_sha),
            ("ladder.assessment_sha256", assessment_sha),
        ):
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise CharacterizationResearchGapError(f"{field} must be a SHA-256 digest")
        if ladder.get("scientific_status_promoted") is not False:
            raise CharacterizationResearchGapError(
                "verified ladder must not promote scientific status"
            )
        if ladder.get("downstream_use_authorized") is not False:
            raise CharacterizationResearchGapError(
                "verified ladder must not authorize downstream use"
            )
        first_blocking = ladder.get("first_blocking_level")
        if first_blocking is not None and first_blocking not in BLOCKING_LEVEL_REQUIREMENTS:
            raise CharacterizationResearchGapError(
                f"unsupported characterization first_blocking_level: {first_blocking}"
            )
        next_requirement = (
            None
            if first_blocking is None
            else dict(BLOCKING_LEVEL_REQUIREMENTS[first_blocking])
        )
        core = {
            "schema_version": "1.0",
            "artifact_type": "characterization_research_evidence_gap",
            "bundle_manifest_sha256": manifest_sha,
            "instruments": normalized_instruments,
            "ladder_present": True,
            "ladder_declaration_sha256": declaration_sha,
            "ladder_assessment_sha256": assessment_sha,
            "highest_contiguous_supported_level": ladder.get(
                "highest_contiguous_supported_level"
            ),
            "first_blocking_level": first_blocking,
            "next_requirement": next_requirement,
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "semantic_marker": "planning_requirement_not_scientific_evidence",
        }
    result = dict(core)
    result["characterization_evidence_gap_sha256"] = _canonical_sha256(core)
    return result


def write_characterization_research_evidence_gap(
    output_dir: str | Path,
    artifact: Mapping[str, Any],
) -> Path:
    """Persist one verified planning-gap artifact without allowing overwrite or promotion."""
    payload = dict(artifact)
    if payload.get("schema_version") != "1.0":
        raise CharacterizationResearchGapError(
            "unsupported characterization research gap schema_version"
        )
    if payload.get("artifact_type") != "characterization_research_evidence_gap":
        raise CharacterizationResearchGapError(
            "characterization research gap artifact_type mismatch"
        )
    if payload.get("scientific_status_promoted") is not False:
        raise CharacterizationResearchGapError(
            "characterization research gap must not promote scientific status"
        )
    if payload.get("downstream_use_authorized") is not False:
        raise CharacterizationResearchGapError(
            "characterization research gap must not authorize downstream use"
        )
    if payload.get("semantic_marker") != "planning_requirement_not_scientific_evidence":
        raise CharacterizationResearchGapError(
            "characterization research gap semantic boundary mismatch"
        )
    recorded_sha = payload.pop("characterization_evidence_gap_sha256", None)
    if not isinstance(recorded_sha, str) or recorded_sha != _canonical_sha256(payload):
        raise CharacterizationResearchGapError(
            "characterization research gap canonical SHA-256 mismatch"
        )
    payload["characterization_evidence_gap_sha256"] = recorded_sha

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise CharacterizationResearchGapError("output_dir must be a real directory")
    path = output / RESEARCH_EVIDENCE_GAP_NAME
    if path.exists():
        raise FileExistsError(
            f"refusing to overwrite characterization research gap artifact: {path}"
        )
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


__all__ = [
    "BLOCKING_LEVEL_REQUIREMENTS",
    "CharacterizationResearchGapError",
    "RESEARCH_EVIDENCE_GAP_NAME",
    "build_characterization_research_evidence_gap",
    "write_characterization_research_evidence_gap",
]
