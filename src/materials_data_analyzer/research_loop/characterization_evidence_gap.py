"""Translate verified characterization maturity blockers into planning-only evidence gaps.

The returned artifact is deliberately non-empirical.  It identifies what evidence the
research controller must seek next, while preserving downstream-use authorization as a
separate trust boundary.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loaders.characterization_evidence_ladder import LEVELS
from loaders.characterization_features import sha256_file

SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "characterization_evidence_maturity_gap"

_REQUIREMENTS: dict[str, dict[str, str]] = {
    "L0_software_integration": {
        "requirement": "establish the intended characterization software integration path",
        "action_class": "characterization_software_integration_validation",
    },
    "L1_raw_representation_identity": {
        "requirement": "acquire and byte-bind the raw or lossless measurement representation and source version",
        "action_class": "characterization_raw_representation_acquisition",
    },
    "L2_acquisition_provenance_integrity": {
        "requirement": "establish sample, acquisition, and preprocessing provenance without inferred lineage",
        "action_class": "characterization_acquisition_provenance_completion",
    },
    "L3_instrument_calibration_validity": {
        "requirement": "obtain and validate instrument, detector, and calibration evidence required by the claim",
        "action_class": "characterization_instrument_calibration_validation",
    },
    "L4_method_algorithm_validation": {
        "requirement": "validate the characterization method under a predeclared protocol within the represented measurement scope",
        "action_class": "characterization_method_validation",
    },
    "L5_material_domain_validation": {
        "requirement": "acquire target-material or target-domain evidence rather than relying on a cross-material proxy",
        "action_class": "characterization_material_domain_validation",
    },
    "L6_independent_external_validation": {
        "requirement": "acquire an independent external validation set satisfying the declared independence contract",
        "action_class": "characterization_independent_external_validation",
    },
    "L7_replicated_multisource_support": {
        "requirement": "replicate the result across provenance-disjoint sources, samples, acquisitions, or facilities",
        "action_class": "characterization_multisource_replication",
    },
    "L8_engineering_decision_readiness": {
        "requirement": "validate operational decision thresholds and engineering-use conditions independently",
        "action_class": "characterization_engineering_validation",
    },
}


class CharacterizationEvidenceGapError(ValueError):
    """Raised when a verified ladder cannot be translated safely into a planning gap."""


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


def build_characterization_evidence_gap(
    *,
    bundle_manifest_path: str | Path,
    ladder_assessment: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic next-evidence requirement from a verified ladder assessment."""
    manifest_path = Path(bundle_manifest_path)
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise CharacterizationEvidenceGapError(
            "bundle manifest must be a regular non-symlink file"
        )
    declaration_sha = ladder_assessment.get("declaration_sha256")
    assessment_sha = ladder_assessment.get("assessment_sha256")
    subject = ladder_assessment.get("declaration", {}).get("subject") if isinstance(
        ladder_assessment.get("declaration"), Mapping
    ) else None
    first_blocker = ladder_assessment.get("first_blocking_level")
    highest = ladder_assessment.get("highest_contiguous_supported_level")
    readiness = ladder_assessment.get("readiness")
    handoff = ladder_assessment.get("handoff")

    for label, digest in (
        ("declaration_sha256", declaration_sha),
        ("assessment_sha256", assessment_sha),
    ):
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise CharacterizationEvidenceGapError(
                f"verified ladder assessment is missing a valid {label}"
            )
    if not isinstance(subject, Mapping):
        raise CharacterizationEvidenceGapError(
            "verified ladder assessment is missing declaration.subject"
        )
    if not isinstance(readiness, Mapping):
        raise CharacterizationEvidenceGapError(
            "verified ladder assessment is missing readiness"
        )
    if not isinstance(handoff, Mapping):
        raise CharacterizationEvidenceGapError(
            "verified ladder assessment is missing handoff boundary"
        )
    if handoff.get("scientific_status_promoted") is not False:
        raise CharacterizationEvidenceGapError(
            "verified ladder assessment attempts to promote scientific status"
        )
    if handoff.get("downstream_use_authorized") is not False:
        raise CharacterizationEvidenceGapError(
            "verified ladder assessment attempts to authorize downstream use"
        )
    if highest is not None and highest not in LEVELS:
        raise CharacterizationEvidenceGapError(
            "verified ladder assessment contains an unknown highest supported level"
        )
    if first_blocker is not None and first_blocker not in LEVELS:
        raise CharacterizationEvidenceGapError(
            "verified ladder assessment contains an unknown first blocking level"
        )

    if first_blocker is None:
        status = "no_unresolved_characterization_maturity_blocker"
        requirement = None
        action_class = None
    else:
        status = "characterization_evidence_gap_open"
        mapped = _REQUIREMENTS[first_blocker]
        requirement = mapped["requirement"]
        action_class = mapped["action_class"]

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "status": status,
        "source_binding": {
            "bundle_manifest_sha256": sha256_file(manifest_path),
            "ladder_declaration_sha256": declaration_sha,
            "ladder_assessment_sha256": assessment_sha,
        },
        "subject": dict(subject),
        "highest_contiguous_supported_level": highest,
        "first_blocking_level": first_blocker,
        "next_evidence_requirement": requirement,
        "suggested_action_class": action_class,
        "readiness": dict(readiness),
        "scientific_status_promoted": False,
        "empirical_evidence_created": False,
        "downstream_use_authorized": False,
        "planning_semantics": (
            "verified characterization evidence-maturity requirement; not empirical evidence, "
            "not a scientific conclusion, and not downstream-use authorization"
        ),
    }
    artifact["artifact_sha256"] = _canonical_sha256(artifact)
    return artifact


__all__ = [
    "ARTIFACT_TYPE",
    "SCHEMA_VERSION",
    "CharacterizationEvidenceGapError",
    "build_characterization_evidence_gap",
]
