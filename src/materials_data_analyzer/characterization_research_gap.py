"""Convert verified characterization maturity into autonomous research requirements.

The output of this module is planning metadata. It is not empirical evidence and it
cannot authorize downstream scientific or engineering use or execute an action.
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
        "planning_action_family": "characterization_software_integration_validation",
        "description": (
            "Exercise the intended characterization software path under a reproducible "
            "test without treating software execution as measurement truth."
        ),
    },
    "L1_raw_representation_identity": {
        "requirement_id": "characterization_raw_representation_identity_required",
        "category": "raw_representation_identity",
        "planning_action_family": "characterization_raw_representation_acquisition",
        "description": (
            "Acquire or recover a raw/lossless representation with stable byte identity "
            "and an explicitly versioned source binding."
        ),
    },
    "L2_acquisition_provenance_integrity": {
        "requirement_id": "characterization_acquisition_provenance_required",
        "category": "acquisition_provenance",
        "planning_action_family": "characterization_acquisition_provenance_audit",
        "description": (
            "Establish sample/acquisition identity and relevant processing lineage without "
            "inferring missing provenance."
        ),
    },
    "L3_instrument_calibration_validity": {
        "requirement_id": "characterization_instrument_calibration_required",
        "category": "instrument_calibration",
        "planning_action_family": "characterization_calibration_validation",
        "description": (
            "Establish traceable instrument, detector, and calibration metadata required "
            "for the declared characterization claim."
        ),
    },
    "L4_method_algorithm_validation": {
        "requirement_id": "characterization_method_validation_required",
        "category": "method_validation",
        "planning_action_family": "characterization_method_validation",
        "description": (
            "Validate the characterization analysis method under a predeclared protocol "
            "within the represented measurement scope."
        ),
    },
    "L5_material_domain_validation": {
        "requirement_id": "characterization_target_material_validation_required",
        "category": "material_domain_validation",
        "planning_action_family": "characterization_target_material_validation",
        "description": (
            "Acquire direct evidence in the declared target material/composition/domain; "
            "a cross-material proxy is insufficient."
        ),
    },
    "L6_independent_external_validation": {
        "requirement_id": "characterization_independent_external_validation_required",
        "category": "independent_external_validation",
        "planning_action_family": "characterization_independent_validation_acquisition",
        "description": (
            "Acquire and evaluate evidence that is independent of method/model development "
            "under an explicit provenance-disjoint independence contract."
        ),
    },
    "L7_replicated_multisource_support": {
        "requirement_id": "characterization_multisource_replication_required",
        "category": "replicated_multisource_support",
        "planning_action_family": "characterization_multisource_replication",
        "description": (
            "Replicate the characterization result across explicitly provenance-disjoint "
            "sources, samples, acquisitions, or facilities as required."
        ),
    },
    "L8_engineering_decision_readiness": {
        "requirement_id": "characterization_engineering_validation_required",
        "category": "engineering_decision_readiness",
        "planning_action_family": "characterization_engineering_validation",
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


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CharacterizationResearchGapError(
                f"duplicate JSON key in bundle manifest: {key}"
            )
        result[key] = value
    return result


def _manifest_identity(path: str | Path) -> tuple[Path, str, str]:
    manifest_path = Path(path)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise CharacterizationResearchGapError(
            "bundle_manifest_path must be a regular non-symlink file"
        )
    resolved = manifest_path.resolve()
    try:
        raw = resolved.read_bytes()
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CharacterizationResearchGapError(
            f"could not read bundle manifest: {resolved}"
        ) from exc
    if not isinstance(payload, dict):
        raise CharacterizationResearchGapError("bundle manifest must contain an object")
    case_id = _nonempty_text(payload.get("case_id"), "bundle manifest case_id")
    return resolved, hashlib.sha256(raw).hexdigest(), case_id


def _validated_ladder_binding(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CharacterizationResearchGapError(
            "ladder_binding is required for a verified ladder"
        )
    required_flags = (
        "case_id_bound",
        "source_digests_bound",
        "subject_modality_bound",
    )
    for flag in required_flags:
        if value.get(flag) is not True:
            raise CharacterizationResearchGapError(
                f"ladder_binding.{flag} must be true"
            )
    roles = value.get("required_source_roles")
    expected_roles = [
        "analysis_manifest",
        "comparability_matrix",
        "source_manifest",
    ]
    if roles != expected_roles:
        raise CharacterizationResearchGapError(
            "ladder_binding.required_source_roles mismatch"
        )
    instruments = value.get("bundle_instruments")
    if not isinstance(instruments, list) or not instruments:
        raise CharacterizationResearchGapError(
            "ladder_binding.bundle_instruments must be a non-empty list"
        )
    normalized_instruments = sorted(
        {_nonempty_text(item, "ladder_binding.bundle_instruments").lower() for item in instruments}
    )
    return {
        "case_id_bound": True,
        "source_digests_bound": True,
        "subject_modality_bound": True,
        "required_source_roles": expected_roles,
        "bundle_instruments": normalized_instruments,
    }


def _normalized_source_bindings(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise CharacterizationResearchGapError(
            "ladder.source_bindings must be a non-empty list"
        )
    result: list[dict[str, str]] = []
    roles: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise CharacterizationResearchGapError(
                f"ladder.source_bindings[{index}] must be an object"
            )
        role = _nonempty_text(item.get("role"), f"ladder.source_bindings[{index}].role")
        digest = _nonempty_text(
            item.get("sha256"), f"ladder.source_bindings[{index}].sha256"
        )
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise CharacterizationResearchGapError(
                f"ladder.source_bindings[{index}].sha256 must be a SHA-256 digest"
            )
        if role in roles:
            raise CharacterizationResearchGapError(
                f"duplicate ladder source binding role: {role}"
            )
        roles.add(role)
        result.append({"role": role, "sha256": digest})
    return sorted(result, key=lambda item: item["role"])


def _normalized_subject(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise CharacterizationResearchGapError("ladder.subject must be an object")
    return {
        key: _nonempty_text(value.get(key), f"ladder.subject.{key}")
        for key in (
            "claim_scope",
            "modality",
            "source_material_domain",
            "target_material_domain",
        )
    }


def build_characterization_research_evidence_gap(
    *,
    bundle_manifest_path: str | Path,
    instruments: list[str],
    ladder: Mapping[str, Any] | None,
    ladder_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic next-evidence planning metadata from a verified ladder.

    The producer manifest digest and case identity are recomputed from persisted bytes.
    A present ladder must also carry the independent consumer's case/source/modality
    binding proof. The result is a planning requirement only; it never authorizes the
    corresponding action family.
    """
    _, manifest_sha, case_id = _manifest_identity(bundle_manifest_path)
    normalized_instruments = sorted(
        {_nonempty_text(item, "instrument").lower() for item in instruments}
    )
    if not normalized_instruments:
        raise CharacterizationResearchGapError("at least one instrument is required")

    if ladder is None:
        if ladder_binding is not None:
            raise CharacterizationResearchGapError(
                "legacy bundle without a ladder must not provide ladder_binding"
            )
        core: dict[str, Any] = {
            "schema_version": "1.0",
            "artifact_type": "characterization_research_evidence_gap",
            "bundle_manifest_sha256": manifest_sha,
            "case_id": case_id,
            "instruments": normalized_instruments,
            "ladder_present": False,
            "ladder_declaration_id": None,
            "ladder_declaration_sha256": None,
            "ladder_assessment_sha256": None,
            "ladder_subject": None,
            "ladder_source_bindings": None,
            "ladder_binding": None,
            "highest_contiguous_supported_level": None,
            "first_blocking_level": None,
            "next_requirement": {
                "requirement_id": "characterization_evidence_maturity_assessment_required",
                "category": "evidence_maturity_assessment",
                "planning_action_family": "characterization_evidence_maturity_assessment",
                "description": (
                    "Obtain an independently replayable L0-L8 characterization evidence "
                    "maturity assessment before inferring a next scientific validation step."
                ),
                "authorization_required_before_execution": True,
            },
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "action_execution_authorized": False,
            "semantic_marker": "planning_requirement_not_scientific_evidence",
        }
    else:
        binding = _validated_ladder_binding(ladder_binding)
        if binding["bundle_instruments"] != normalized_instruments:
            raise CharacterizationResearchGapError(
                "ladder binding instruments do not match requested gap instruments"
            )
        declaration_id = _nonempty_text(
            ladder.get("declaration_id"), "ladder.declaration_id"
        )
        if declaration_id != case_id:
            raise CharacterizationResearchGapError(
                "ladder declaration_id does not match bundle manifest case_id"
            )
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
            else {
                **BLOCKING_LEVEL_REQUIREMENTS[first_blocking],
                "authorization_required_before_execution": True,
            }
        )
        core = {
            "schema_version": "1.0",
            "artifact_type": "characterization_research_evidence_gap",
            "bundle_manifest_sha256": manifest_sha,
            "case_id": case_id,
            "instruments": normalized_instruments,
            "ladder_present": True,
            "ladder_declaration_id": declaration_id,
            "ladder_declaration_sha256": declaration_sha,
            "ladder_assessment_sha256": assessment_sha,
            "ladder_subject": _normalized_subject(ladder.get("subject")),
            "ladder_source_bindings": _normalized_source_bindings(
                ladder.get("source_bindings")
            ),
            "ladder_binding": binding,
            "highest_contiguous_supported_level": ladder.get(
                "highest_contiguous_supported_level"
            ),
            "first_blocking_level": first_blocking,
            "next_requirement": next_requirement,
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "action_execution_authorized": False,
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
    if payload.get("action_execution_authorized") is not False:
        raise CharacterizationResearchGapError(
            "characterization research gap must not authorize action execution"
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
