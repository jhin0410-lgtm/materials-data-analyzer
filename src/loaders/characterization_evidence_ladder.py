"""Independent consumer verification for characterization L0-L8 evidence ladders.

This module intentionally does not import ``mca``.  The producer and consumer must
agree through persisted, checksum-bound bytes rather than a shared implementation.
A validated ladder describes evidence maturity only; it never authorizes downstream
use or promotes scientific status.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

LEGACY_BUNDLE_SCHEMA_VERSION = "1.0"
LADDER_BUNDLE_SCHEMA_VERSION = "1.1"
SUPPORTED_BUNDLE_SCHEMA_VERSIONS = (
    LEGACY_BUNDLE_SCHEMA_VERSION,
    LADDER_BUNDLE_SCHEMA_VERSION,
)
LADDER_SCHEMA_VERSION = "1.0"
LADDER_POLICY_VERSION = "1.0"
ASSESSMENTS = ("Supported", "Diagnostic", "Inconclusive", "Unsupported")
LEVELS = (
    "L0_software_integration",
    "L1_raw_representation_identity",
    "L2_acquisition_provenance_integrity",
    "L3_instrument_calibration_validity",
    "L4_method_algorithm_validation",
    "L5_material_domain_validation",
    "L6_independent_external_validation",
    "L7_replicated_multisource_support",
    "L8_engineering_decision_readiness",
)
LEVEL_DESCRIPTIONS = {
    "L0_software_integration": "The source/result exercises the intended software path without establishing measurement truth.",
    "L1_raw_representation_identity": "Raw/lossless representation, stable byte identity, and source version are verified.",
    "L2_acquisition_provenance_integrity": "Sample/acquisition identity and relevant processing lineage are traceable without inference.",
    "L3_instrument_calibration_validity": "Instrument/detector/calibration metadata required for the claim are traceable and valid.",
    "L4_method_algorithm_validation": "The analysis method is validated under a predeclared protocol within the represented measurement scope.",
    "L5_material_domain_validation": "Evidence directly supports the declared target material/composition/domain rather than a cross-material proxy.",
    "L6_independent_external_validation": "Evidence is independent of model/method development under the declared independence contract.",
    "L7_replicated_multisource_support": "The result is replicated across explicitly provenance-disjoint sources, samples, acquisitions, or facilities as required.",
    "L8_engineering_decision_readiness": "Operational validation, decision thresholds, and engineering-use conditions are independently supported.",
}
_REQUIRED_ROOT_FIELDS = {
    "schema_version",
    "declaration_id",
    "subject",
    "source_bindings",
    "levels",
    "limitations",
}
_REQUIRED_SUBJECT_FIELDS = {
    "modality",
    "source_material_domain",
    "target_material_domain",
    "claim_scope",
}
_REQUIRED_LEVEL_FIELDS = {"assessment", "evidence", "limitations"}
_REQUIRED_BINDING_FIELDS = {"role", "sha256"}
_REQUIRED_BUNDLE_SOURCE_ROLES = {
    "source_manifest",
    "analysis_manifest",
    "comparability_matrix",
}
_ALLOWED_MULTIMODAL_SUBJECTS = {"multimodal", "multi-modal", "multiple"}


class CharacterizationEvidenceLadderError(ValueError):
    """Raised when a characterization maturity artifact fails closed."""


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
        raise CharacterizationEvidenceLadderError(
            "characterization evidence ladder must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CharacterizationEvidenceLadderError(
                f"duplicate JSON key in characterization evidence ladder: {key}"
            )
        result[key] = value
    return result


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CharacterizationEvidenceLadderError(f"{label} must be a regular file")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CharacterizationEvidenceLadderError(f"could not read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise CharacterizationEvidenceLadderError(f"{label} must contain a JSON object")
    return payload


def _exact_mapping(
    value: object,
    *,
    required: set[str],
    field: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CharacterizationEvidenceLadderError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing:
        raise CharacterizationEvidenceLadderError(f"{field} is missing field: {missing[0]}")
    if unknown:
        raise CharacterizationEvidenceLadderError(f"{field} contains unknown field: {unknown[0]}")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CharacterizationEvidenceLadderError(f"{field} must be a non-empty string")
    return value.strip()


def _text_list(value: object, field: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list):
        raise CharacterizationEvidenceLadderError(f"{field} must be a list")
    if not allow_empty and not value:
        raise CharacterizationEvidenceLadderError(f"{field} must not be empty")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _text(item, f"{field}[{index}]")
        if text in result:
            raise CharacterizationEvidenceLadderError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _sha256(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise CharacterizationEvidenceLadderError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _normalize_subject(value: object) -> dict[str, str]:
    subject = _exact_mapping(
        value,
        required=_REQUIRED_SUBJECT_FIELDS,
        field="subject",
    )
    return {
        field: _text(subject[field], f"subject.{field}")
        for field in sorted(_REQUIRED_SUBJECT_FIELDS)
    }


def _normalize_bindings(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise CharacterizationEvidenceLadderError(
            "source_bindings must be a non-empty list"
        )
    result: list[dict[str, str]] = []
    roles: set[str] = set()
    for index, raw in enumerate(value):
        item = _exact_mapping(
            raw,
            required=_REQUIRED_BINDING_FIELDS,
            field=f"source_bindings[{index}]",
        )
        role = _text(item["role"], f"source_bindings[{index}].role")
        if role in roles:
            raise CharacterizationEvidenceLadderError(
                f"duplicate source binding role: {role}"
            )
        roles.add(role)
        result.append(
            {
                "role": role,
                "sha256": _sha256(
                    item["sha256"], f"source_bindings[{index}].sha256"
                ),
            }
        )
    return result


def _normalize_levels(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise CharacterizationEvidenceLadderError("levels must be an object")
    missing = sorted(set(LEVELS) - set(value))
    unknown = sorted(set(value) - set(LEVELS))
    if missing:
        raise CharacterizationEvidenceLadderError(
            f"levels is missing required level: {missing[0]}"
        )
    if unknown:
        raise CharacterizationEvidenceLadderError(
            f"levels contains unknown level: {unknown[0]}"
        )

    result: dict[str, dict[str, Any]] = {}
    prior_supported = True
    for level in LEVELS:
        raw = _exact_mapping(
            value[level],
            required=_REQUIRED_LEVEL_FIELDS,
            field=f"levels.{level}",
        )
        assessment = _text(raw["assessment"], f"levels.{level}.assessment")
        if assessment not in ASSESSMENTS:
            raise CharacterizationEvidenceLadderError(
                f"levels.{level}.assessment must be one of: {', '.join(ASSESSMENTS)}"
            )
        evidence = _text_list(
            raw["evidence"],
            f"levels.{level}.evidence",
            allow_empty=assessment != "Supported",
        )
        limitations = _text_list(
            raw["limitations"],
            f"levels.{level}.limitations",
            allow_empty=True,
        )
        if assessment == "Supported" and not prior_supported:
            raise CharacterizationEvidenceLadderError(
                f"{level} cannot be Supported when a lower evidence level is not Supported"
            )
        result[level] = {
            "assessment": assessment,
            "evidence": evidence,
            "limitations": limitations,
            "description": LEVEL_DESCRIPTIONS[level],
        }
        prior_supported = prior_supported and assessment == "Supported"
    return result


def _declaration_from_persisted(value: object) -> dict[str, Any]:
    root = _exact_mapping(
        value,
        required=_REQUIRED_ROOT_FIELDS,
        field="evidence ladder declaration",
    )
    if _text(root["schema_version"], "schema_version") != LADDER_SCHEMA_VERSION:
        raise CharacterizationEvidenceLadderError(
            "unsupported evidence ladder schema_version"
        )
    raw_levels = root["levels"]
    if not isinstance(raw_levels, Mapping):
        raise CharacterizationEvidenceLadderError("levels must be an object")
    stripped_levels: dict[str, dict[str, Any]] = {}
    for level in LEVELS:
        raw_level = raw_levels.get(level)
        if not isinstance(raw_level, Mapping):
            raise CharacterizationEvidenceLadderError(
                f"levels.{level} must be an object"
            )
        allowed = _REQUIRED_LEVEL_FIELDS | {"description"}
        unknown = sorted(set(raw_level) - allowed)
        missing = sorted(_REQUIRED_LEVEL_FIELDS - set(raw_level))
        if missing:
            raise CharacterizationEvidenceLadderError(
                f"levels.{level} is missing field: {missing[0]}"
            )
        if unknown:
            raise CharacterizationEvidenceLadderError(
                f"levels.{level} contains unknown field: {unknown[0]}"
            )
        if "description" in raw_level and raw_level["description"] != LEVEL_DESCRIPTIONS[level]:
            raise CharacterizationEvidenceLadderError(
                f"levels.{level}.description does not match the evidence-ladder contract"
            )
        stripped_levels[level] = {
            key: raw_level[key] for key in _REQUIRED_LEVEL_FIELDS
        }
    return {
        "schema_version": root["schema_version"],
        "declaration_id": root["declaration_id"],
        "subject": root["subject"],
        "source_bindings": root["source_bindings"],
        "levels": stripped_levels,
        "limitations": root["limitations"],
    }


def evaluate_scientific_evidence_ladder(value: object) -> dict[str, Any]:
    """Independently reproduce the producer's deterministic L0-L8 assessment."""
    root = _exact_mapping(
        value,
        required=_REQUIRED_ROOT_FIELDS,
        field="evidence ladder declaration",
    )
    if _text(root["schema_version"], "schema_version") != LADDER_SCHEMA_VERSION:
        raise CharacterizationEvidenceLadderError(
            "unsupported evidence ladder schema_version"
        )
    declaration = {
        "schema_version": LADDER_SCHEMA_VERSION,
        "declaration_id": _text(root["declaration_id"], "declaration_id"),
        "subject": _normalize_subject(root["subject"]),
        "source_bindings": _normalize_bindings(root["source_bindings"]),
        "levels": _normalize_levels(root["levels"]),
        "limitations": _text_list(root["limitations"], "limitations", allow_empty=True),
    }
    highest_index = -1
    for index, level in enumerate(LEVELS):
        if declaration["levels"][level]["assessment"] != "Supported":
            break
        highest_index = index
    highest = LEVELS[highest_index] if highest_index >= 0 else None
    first_blocking = (
        LEVELS[highest_index + 1] if highest_index + 1 < len(LEVELS) else None
    )
    result = {
        "schema_version": LADDER_SCHEMA_VERSION,
        "policy_version": LADDER_POLICY_VERSION,
        "declaration": declaration,
        "declaration_sha256": _canonical_sha256(declaration),
        "highest_contiguous_supported_level": highest,
        "highest_contiguous_supported_index": highest_index,
        "first_blocking_level": first_blocking,
        "non_supported_levels": [
            {
                "level": level,
                "assessment": declaration["levels"][level]["assessment"],
                "limitations": declaration["levels"][level]["limitations"],
            }
            for level in LEVELS
            if declaration["levels"][level]["assessment"] != "Supported"
        ],
        "readiness": {
            "raw_representation_ready": highest_index >= 1,
            "acquisition_provenance_ready": highest_index >= 2,
            "instrument_calibration_ready": highest_index >= 3,
            "method_validation_ready": highest_index >= 4,
            "material_domain_validation_ready": highest_index >= 5,
            "independent_external_validation_ready": highest_index >= 6,
            "replicated_multisource_support_ready": highest_index >= 7,
            "engineering_decision_ready": highest_index >= 8,
        },
        "handoff": {
            "contract": "materials-characterization-scientific-evidence-ladder",
            "schema_version": LADDER_SCHEMA_VERSION,
            "subject": declaration["subject"],
            "source_bindings": declaration["source_bindings"],
            "highest_supported_level": highest,
            "first_blocking_level": first_blocking,
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "lower_level_evidence_preserved": True,
        },
        "policy_boundary": {
            "cross_material_proxy_promoted_to_target_material_validation": False,
            "software_validation_promoted_to_measurement_truth": False,
            "simulation_promoted_to_empirical_truth": False,
            "independence_inferred_from_file_count": False,
            "engineering_readiness_inferred": False,
        },
    }
    result["assessment_sha256"] = _canonical_sha256(result)
    return result


def replay_scientific_evidence_ladder_assessment(
    persisted: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute a persisted assessment and reject producer-authored substitutions."""
    declaration = persisted.get("declaration")
    if declaration is None:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence ladder assessment is missing declaration"
        )
    recomputed = evaluate_scientific_evidence_ladder(
        _declaration_from_persisted(declaration)
    )
    if dict(persisted) != recomputed:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence ladder assessment does not match independent replay"
        )
    if recomputed["handoff"]["scientific_status_promoted"] is not False:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence ladder must not promote scientific status"
        )
    if recomputed["handoff"]["downstream_use_authorized"] is not False:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence ladder must not authorize downstream use"
        )
    return recomputed


def _resolve_ladder_record(
    bundle_root: Path,
    record: object,
) -> tuple[Path, dict[str, Any]]:
    if not isinstance(record, Mapping):
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder must be an object"
        )
    required = {
        "path",
        "sha256",
        "size_bytes",
        "declaration_sha256",
        "assessment_sha256",
        "subject",
        "source_bindings",
        "highest_contiguous_supported_level",
        "first_blocking_level",
        "readiness",
        "scientific_status_promoted",
        "downstream_use_authorized",
    }
    missing = sorted(required - set(record))
    unknown = sorted(set(record) - required)
    if missing:
        raise CharacterizationEvidenceLadderError(
            f"scientific_evidence_ladder is missing field: {missing[0]}"
        )
    if unknown:
        raise CharacterizationEvidenceLadderError(
            f"scientific_evidence_ladder contains unknown field: {unknown[0]}"
        )
    path_text = _text(record["path"], "scientific_evidence_ladder.path")
    relative = Path(path_text)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != path_text:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder.path must be one direct sibling filename"
        )
    path = bundle_root / relative
    if path.is_symlink() or not path.is_file():
        raise CharacterizationEvidenceLadderError(
            "scientific evidence ladder assessment file is missing or unsafe"
        )
    expected_sha = _sha256(record["sha256"], "scientific_evidence_ladder.sha256")
    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence ladder checksum mismatch"
        )
    size = record["size_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder.size_bytes must be a non-negative integer"
        )
    if path.stat().st_size != size:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence ladder size_bytes mismatch"
        )
    return path, dict(record)


def validate_bundle_scientific_evidence_ladder(
    *,
    bundle_root: Path,
    record: object,
    case_id: str,
    evidence_paths: Mapping[str, Path],
    instruments: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate, replay, and cross-bind a schema-1.1 ladder to bundle evidence."""
    path, manifest_record = _resolve_ladder_record(bundle_root, record)
    persisted = _load_json_object(path, "scientific evidence ladder assessment")
    replayed = replay_scientific_evidence_ladder_assessment(persisted)

    summary_fields = {
        "declaration_sha256": replayed["declaration_sha256"],
        "assessment_sha256": replayed["assessment_sha256"],
        "subject": replayed["declaration"]["subject"],
        "source_bindings": replayed["declaration"]["source_bindings"],
        "highest_contiguous_supported_level": replayed[
            "highest_contiguous_supported_level"
        ],
        "first_blocking_level": replayed["first_blocking_level"],
        "readiness": replayed["readiness"],
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
    }
    for key, expected in summary_fields.items():
        if manifest_record[key] != expected:
            raise CharacterizationEvidenceLadderError(
                f"scientific evidence ladder manifest summary mismatch: {key}"
            )

    declaration = replayed["declaration"]
    if declaration["declaration_id"] != case_id:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence ladder declaration_id does not match bundle case_id"
        )
    bindings = {item["role"]: item["sha256"] for item in declaration["source_bindings"]}
    if set(bindings) != _REQUIRED_BUNDLE_SOURCE_ROLES:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence ladder source bindings must exactly cover bundle evidence"
        )
    for role in sorted(_REQUIRED_BUNDLE_SOURCE_ROLES):
        expected = hashlib.sha256(evidence_paths[role].read_bytes()).hexdigest()
        if bindings[role] != expected:
            raise CharacterizationEvidenceLadderError(
                f"scientific evidence ladder source binding mismatch: {role}"
            )

    normalized_instruments = sorted({str(item).strip().lower() for item in instruments})
    modality = declaration["subject"]["modality"].strip().lower()
    if len(normalized_instruments) == 1:
        if modality != normalized_instruments[0]:
            raise CharacterizationEvidenceLadderError(
                "scientific evidence ladder subject modality does not match bundle instrument"
            )
    elif modality not in _ALLOWED_MULTIMODAL_SUBJECTS:
        raise CharacterizationEvidenceLadderError(
            "multi-instrument bundle requires an explicit multimodal ladder subject"
        )

    summary = {
        **summary_fields,
        "artifact_sha256": manifest_record["sha256"],
        "artifact_size_bytes": manifest_record["size_bytes"],
    }
    binding = {
        "case_id_bound": True,
        "required_source_roles": sorted(_REQUIRED_BUNDLE_SOURCE_ROLES),
        "source_digests_bound": True,
        "subject_modality_bound": True,
        "bundle_instruments": normalized_instruments,
    }
    return summary, binding


__all__ = [
    "CharacterizationEvidenceLadderError",
    "LADDER_BUNDLE_SCHEMA_VERSION",
    "LEGACY_BUNDLE_SCHEMA_VERSION",
    "LEVELS",
    "SUPPORTED_BUNDLE_SCHEMA_VERSIONS",
    "evaluate_scientific_evidence_ladder",
    "replay_scientific_evidence_ladder_assessment",
    "validate_bundle_scientific_evidence_ladder",
]
