"""Compile independently verified characterization maturity into research planning gaps.

The characterization repository owns modality-specific evidence assessment.  This module
turns the first unresolved L0-L8 level into a deterministic *planning requirement* for the
autonomous research orchestrator.  It creates no scientific evidence, authorizes no
execution, and cannot promote a claim.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .kernel import ResearchLoopError

CHARACTERIZATION_EVIDENCE_GAP_SCHEMA_VERSION = "1.0"
CHARACTERIZATION_EVIDENCE_GAP_POLICY_VERSION = "1.0"

_LEVEL_GAP_SPECS: dict[str, dict[str, Any]] = {
    "L0_software_integration": {
        "action_class_hint": "existing_data_reanalysis",
        "requirement": (
            "Establish the intended characterization software integration path with a "
            "reproducible analysis invocation and checksum-bound inputs/outputs before "
            "treating any result as measurement evidence."
        ),
        "satisfaction_criteria": [
            "The intended public analysis path executes reproducibly.",
            "Inputs, outputs, software version, and preprocessing identity are checksum-bound.",
            "Software success is explicitly not promoted to measurement truth.",
        ],
    },
    "L1_raw_representation_identity": {
        "action_class_hint": "external_evidence_search",
        "requirement": (
            "Acquire or verify the raw or lossless characterization representation, stable "
            "source/version identity, and SHA-256 binding needed to establish raw data identity."
        ),
        "satisfaction_criteria": [
            "Raw or lossless source bytes are available without undocumented transformation.",
            "The exact source/version is recorded and SHA-256 bound.",
            "The analyzed representation is traceably derived from those bound bytes.",
        ],
    },
    "L2_acquisition_provenance_integrity": {
        "action_class_hint": "external_evidence_search",
        "requirement": (
            "Resolve exact sample, specimen, acquisition, measurement, and processing lineage "
            "for the characterization evidence without inferring missing provenance."
        ),
        "satisfaction_criteria": [
            "Sample/specimen and acquisition identifiers are explicit.",
            "Relevant acquisition conditions and processing lineage are traceable.",
            "No required identity or provenance field is inferred from filenames or row order.",
        ],
    },
    "L3_instrument_calibration_validity": {
        "action_class_hint": "physical_experiment_design",
        "requirement": (
            "Acquire or independently verify the instrument, detector, calibration, scale, and "
            "measurement-condition metadata required for the characterization claim."
        ),
        "satisfaction_criteria": [
            "Instrument and detector identity are traceable for the represented acquisition.",
            "Calibration/scale metadata required by the claim are present and valid.",
            "Calibration validity is bound to the relevant acquisition rather than assumed globally.",
        ],
    },
    "L4_method_algorithm_validation": {
        "action_class_hint": "existing_data_reanalysis",
        "requirement": (
            "Validate the characterization method or algorithm under a predeclared protocol "
            "within the represented measurement scope using suitable controls, references, "
            "sensitivity analysis, or held-out validation."
        ),
        "satisfaction_criteria": [
            "Validation protocol and acceptance criteria are declared before evaluation.",
            "Reference/control or held-out evidence is appropriate for the represented measurement scope.",
            "Failure modes and sensitivity to preprocessing/parameters are quantified or bounded.",
        ],
    },
    "L5_material_domain_validation": {
        "action_class_hint": "external_evidence_search",
        "requirement": (
            "Acquire direct evidence in the declared target material, composition, phase, or "
            "microstructural domain so that a cross-material proxy is not promoted to target-domain validation."
        ),
        "satisfaction_criteria": [
            "Validation evidence directly represents the declared target material/domain.",
            "Material/composition/phase identity required by the claim is provenance-bound.",
            "Any remaining domain shift is explicit and not hidden by proxy evidence.",
        ],
    },
    "L6_independent_external_validation": {
        "action_class_hint": "replication",
        "requirement": (
            "Acquire an independent external characterization validation dataset or acquisition "
            "that is provenance-disjoint from method/model development under an explicit independence contract."
        ),
        "satisfaction_criteria": [
            "Validation source/sample/acquisition is explicitly independent of development evidence.",
            "Parent/source overlap and leakage are audited before evaluation.",
            "The predeclared method is evaluated without tuning on the independent validation result.",
        ],
    },
    "L7_replicated_multisource_support": {
        "action_class_hint": "replication",
        "requirement": (
            "Replicate the characterization result across provenance-disjoint sources, samples, "
            "acquisitions, instruments, laboratories, or facilities as required by the claim scope."
        ),
        "satisfaction_criteria": [
            "At least the claim-required number of provenance-disjoint replications is available.",
            "Disjointness is demonstrated by source/sample/acquisition/facility identifiers.",
            "Replication consistency and heterogeneity are reported without selective exclusion.",
        ],
    },
    "L8_engineering_decision_readiness": {
        "action_class_hint": "physical_experiment_design",
        "requirement": (
            "Perform independent operational validation of characterization decision thresholds, "
            "failure costs, uncertainty limits, and engineering-use conditions before release decisions."
        ),
        "satisfaction_criteria": [
            "Operational decision thresholds and error consequences are predeclared.",
            "Independent engineering-relevant validation covers intended operating conditions.",
            "Uncertainty, out-of-domain limits, and release/hold criteria are explicitly supported.",
        ],
    },
}


class CharacterizationEvidenceGapError(ResearchLoopError):
    """Raised when a verified ladder cannot be compiled into a safe planning gap."""


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CharacterizationEvidenceGapError(
            "characterization evidence-gap state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise CharacterizationEvidenceGapError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CharacterizationEvidenceGapError(f"{field} must be an object")
    return value


def build_characterization_evidence_gap(
    *,
    scientific_evidence_ladder: Mapping[str, Any],
    scientific_evidence_ladder_assessment: Mapping[str, Any],
    source_bundle_manifest_sha256: str,
) -> dict[str, Any]:
    """Compile one independently verified ladder into one deterministic research gap.

    Callers are expected to pass the record and replayed assessment returned by the
    independent consumer validator.  Redundant hashes/summary fields are rechecked here so
    a caller cannot splice a valid manifest record onto a different assessment.
    """
    record = dict(_mapping(scientific_evidence_ladder, "scientific_evidence_ladder"))
    assessment = dict(
        _mapping(
            scientific_evidence_ladder_assessment,
            "scientific_evidence_ladder_assessment",
        )
    )
    source_sha = _sha256(source_bundle_manifest_sha256, "source_bundle_manifest_sha256")
    declaration_sha = _sha256(
        record.get("declaration_sha256"), "scientific_evidence_ladder.declaration_sha256"
    )
    assessment_sha = _sha256(
        record.get("assessment_sha256"), "scientific_evidence_ladder.assessment_sha256"
    )
    if assessment.get("declaration_sha256") != declaration_sha:
        raise CharacterizationEvidenceGapError(
            "ladder record declaration SHA differs from independently replayed assessment"
        )
    if assessment.get("assessment_sha256") != assessment_sha:
        raise CharacterizationEvidenceGapError(
            "ladder record assessment SHA differs from independently replayed assessment"
        )
    if record.get("highest_contiguous_supported_level") != assessment.get(
        "highest_contiguous_supported_level"
    ):
        raise CharacterizationEvidenceGapError(
            "ladder record highest supported level differs from replayed assessment"
        )
    if record.get("first_blocking_level") != assessment.get("first_blocking_level"):
        raise CharacterizationEvidenceGapError(
            "ladder record first blocking level differs from replayed assessment"
        )
    if record.get("readiness") != assessment.get("readiness"):
        raise CharacterizationEvidenceGapError(
            "ladder record readiness differs from replayed assessment"
        )
    if record.get("scientific_status_promoted") is not False:
        raise CharacterizationEvidenceGapError(
            "characterization ladder must not promote scientific status"
        )
    if record.get("downstream_use_authorized") is not False:
        raise CharacterizationEvidenceGapError(
            "characterization ladder must not authorize downstream use"
        )

    subject = record.get("subject")
    if not isinstance(subject, Mapping):
        raise CharacterizationEvidenceGapError("ladder subject must be an object")
    blocker = record.get("first_blocking_level")
    if blocker is not None and blocker not in _LEVEL_GAP_SPECS:
        raise CharacterizationEvidenceGapError(
            f"unsupported characterization first_blocking_level: {blocker}"
        )

    gap: dict[str, Any] | None = None
    if isinstance(blocker, str):
        spec = _LEVEL_GAP_SPECS[blocker]
        declaration = assessment.get("declaration")
        if not isinstance(declaration, Mapping):
            raise CharacterizationEvidenceGapError(
                "replayed assessment declaration must be an object"
            )
        levels = declaration.get("levels")
        if not isinstance(levels, Mapping) or not isinstance(levels.get(blocker), Mapping):
            raise CharacterizationEvidenceGapError(
                "replayed assessment does not contain the blocking level declaration"
            )
        blocking_declaration = levels[blocker]
        gap = {
            "gap_id": f"characterization:{declaration_sha[:16]}:{blocker}",
            "source": "characterization_scientific_evidence_ladder",
            "evidence_level": blocker,
            "assessment": blocking_declaration.get("assessment"),
            "requirement": spec["requirement"],
            "action_class_hint": spec["action_class_hint"],
            "satisfaction_criteria": list(spec["satisfaction_criteria"]),
            "producer_declared_limitations": list(
                blocking_declaration.get("limitations", [])
                if isinstance(blocking_declaration.get("limitations", []), list)
                else []
            ),
            "scientific_status_promoted": False,
            "automatic_execution_authorized": False,
        }

    result: dict[str, Any] = {
        "schema_version": CHARACTERIZATION_EVIDENCE_GAP_SCHEMA_VERSION,
        "policy_version": CHARACTERIZATION_EVIDENCE_GAP_POLICY_VERSION,
        "artifact_type": "characterization_evidence_maturity_planning_requirement",
        "source_bundle_manifest_sha256": source_sha,
        "declaration_sha256": declaration_sha,
        "assessment_sha256": assessment_sha,
        "subject": dict(subject),
        "highest_contiguous_supported_level": record.get(
            "highest_contiguous_supported_level"
        ),
        "first_blocking_level": blocker,
        "readiness": dict(_mapping(record.get("readiness"), "ladder readiness")),
        "evidence_gap": gap,
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "automatic_execution_authorized": False,
        "planning_metadata_only": True,
        "scientific_boundary": (
            "This artifact converts an independently replayed characterization evidence-maturity "
            "blocker into a planning requirement. It is not new empirical evidence, does not "
            "upgrade any characterization claim, and grants no action or downstream-use authority."
        ),
    }
    result["canonical_sha256"] = _canonical_sha256(result)
    return result


__all__ = [
    "CHARACTERIZATION_EVIDENCE_GAP_POLICY_VERSION",
    "CHARACTERIZATION_EVIDENCE_GAP_SCHEMA_VERSION",
    "CharacterizationEvidenceGapError",
    "build_characterization_evidence_gap",
]
