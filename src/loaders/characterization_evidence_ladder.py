"""Independent consumer validation for characterization L0-L8 evidence ladders.

This module intentionally does not import ``mca``. The consumer reconstructs the
producer's public contract from bytes and declaration semantics, then cross-binds it
to the exact bundle case, evidence files, and represented modality.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .characterization_features import sha256_file

CONTRACT = "materials-characterization-scientific-evidence-ladder"
SCHEMA_VERSION = "1.0"
POLICY_VERSION = "1.0"
RECORD_SCHEMA_VERSION = "1.0"
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
_ROOT_FIELDS = {
    "schema_version",
    "declaration_id",
    "subject",
    "source_bindings",
    "levels",
    "limitations",
}
_SUBJECT_FIELDS = {
    "modality",
    "source_material_domain",
    "target_material_domain",
    "claim_scope",
}
_LEVEL_FIELDS = {"assessment", "evidence", "limitations"}
_BINDING_FIELDS = {"role", "sha256"}
_RECORD_FIELDS = {
    "contract",
    "schema_version",
    "policy_version",
    "assessment",
    "declaration_id",
    "declaration_sha256",
    "assessment_sha256",
    "subject",
    "source_bindings",
    "highest_contiguous_supported_level",
    "first_blocking_level",
    "readiness",
    "scientific_status_promoted",
    "downstream_use_authorized",
    "lower_level_evidence_preserved",
}
_FILE_RECORD_FIELDS = {"path", "sha256", "size_bytes"}


class CharacterizationEvidenceLadderError(ValueError):
    """Raised when the producer ladder cannot be independently reconstructed."""


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
            "evidence ladder must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CharacterizationEvidenceLadderError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise CharacterizationEvidenceLadderError(
            f"{label} must be a regular non-symlink file"
        )
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CharacterizationEvidenceLadderError(f"could not read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise CharacterizationEvidenceLadderError(f"{label} root must be an object")
    return value


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
            raise CharacterizationEvidenceLadderError(
                f"{field} must not contain duplicates"
            )
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
    subject = _exact_mapping(value, required=_SUBJECT_FIELDS, field="subject")
    return {
        field: _text(subject[field], f"subject.{field}")
        for field in sorted(_SUBJECT_FIELDS)
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
            required=_BINDING_FIELDS,
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
            required=_LEVEL_FIELDS,
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


def _evaluate_raw_declaration(value: object) -> dict[str, Any]:
    root = _exact_mapping(
        value,
        required=_ROOT_FIELDS,
        field="evidence ladder declaration",
    )
    if _text(root["schema_version"], "schema_version") != SCHEMA_VERSION:
        raise CharacterizationEvidenceLadderError(
            "unsupported evidence ladder schema_version"
        )
    declaration = {
        "schema_version": SCHEMA_VERSION,
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
    first_blocking = LEVELS[highest_index + 1] if highest_index + 1 < len(LEVELS) else None
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
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
            "contract": CONTRACT,
            "schema_version": SCHEMA_VERSION,
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


def _raw_declaration_for_replay(declaration: Mapping[str, Any]) -> dict[str, Any]:
    levels = declaration.get("levels")
    if not isinstance(levels, Mapping):
        raise CharacterizationEvidenceLadderError(
            "assessment declaration.levels must be an object"
        )
    raw_levels: dict[str, dict[str, Any]] = {}
    for level in LEVELS:
        item = levels.get(level)
        if not isinstance(item, Mapping):
            raise CharacterizationEvidenceLadderError(
                f"assessment declaration is missing level: {level}"
            )
        raw_levels[level] = {
            "assessment": item.get("assessment"),
            "evidence": item.get("evidence"),
            "limitations": item.get("limitations"),
        }
    return {
        "schema_version": declaration.get("schema_version"),
        "declaration_id": declaration.get("declaration_id"),
        "subject": declaration.get("subject"),
        "source_bindings": declaration.get("source_bindings"),
        "levels": raw_levels,
        "limitations": declaration.get("limitations"),
    }


def _resolve_assessment(root: Path, value: object) -> Path:
    record = _exact_mapping(
        value,
        required=_FILE_RECORD_FIELDS,
        field="scientific_evidence_ladder.assessment",
    )
    recorded = record.get("path")
    if not isinstance(recorded, str) or not recorded.strip():
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder.assessment.path must be a non-empty string"
        )
    relative = Path(recorded)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != recorded:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder assessment must be one direct sibling file"
        )
    target = root / relative
    if target.is_symlink() or not target.is_file():
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder assessment is missing or unsafe"
        )
    if record.get("sha256") != sha256_file(target):
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder assessment checksum mismatch"
        )
    size = record.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int):
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder assessment size_bytes must be an integer"
        )
    if size != target.stat().st_size:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder assessment size_bytes mismatch"
        )
    return target


def validate_characterization_evidence_ladder(
    *,
    manifest: dict[str, Any],
    bundle_root: Path,
    evidence_paths: dict[str, Path],
    instruments: list[str],
) -> dict[str, Any] | None:
    """Independently replay and cross-bind an optional producer ladder record."""
    raw_record = manifest.get("scientific_evidence_ladder")
    if raw_record is None:
        return None
    record = _exact_mapping(
        raw_record,
        required=_RECORD_FIELDS,
        field="scientific_evidence_ladder",
    )
    if record.get("contract") != CONTRACT:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder contract mismatch"
        )
    if record.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise CharacterizationEvidenceLadderError(
            "unsupported scientific_evidence_ladder schema_version"
        )
    assessment_path = _resolve_assessment(bundle_root.resolve(), record.get("assessment"))
    payload = _read_json(assessment_path, "scientific evidence-ladder assessment")
    declaration = payload.get("declaration")
    if not isinstance(declaration, Mapping):
        raise CharacterizationEvidenceLadderError(
            "scientific evidence-ladder assessment must contain a declaration object"
        )
    replayed = _evaluate_raw_declaration(_raw_declaration_for_replay(declaration))
    if payload != replayed:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence-ladder assessment does not exactly match consumer replay"
        )
    handoff = replayed["handoff"]
    expected_record = {
        "contract": CONTRACT,
        "schema_version": RECORD_SCHEMA_VERSION,
        "policy_version": replayed["policy_version"],
        "assessment": {
            "path": assessment_path.name,
            "sha256": sha256_file(assessment_path),
            "size_bytes": assessment_path.stat().st_size,
        },
        "declaration_id": replayed["declaration"]["declaration_id"],
        "declaration_sha256": replayed["declaration_sha256"],
        "assessment_sha256": replayed["assessment_sha256"],
        "subject": handoff["subject"],
        "source_bindings": handoff["source_bindings"],
        "highest_contiguous_supported_level": replayed[
            "highest_contiguous_supported_level"
        ],
        "first_blocking_level": replayed["first_blocking_level"],
        "readiness": replayed["readiness"],
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "lower_level_evidence_preserved": True,
    }
    if dict(record) != expected_record:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder manifest summary does not match consumer replay"
        )
    declaration_id = replayed["declaration"]["declaration_id"]
    if declaration_id != manifest.get("case_id"):
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder declaration_id does not match bundle case_id"
        )
    bindings = {
        item["role"]: item["sha256"]
        for item in replayed["declaration"]["source_bindings"]
    }
    for role, path in sorted(evidence_paths.items()):
        if bindings.get(role) != sha256_file(path):
            raise CharacterizationEvidenceLadderError(
                f"scientific_evidence_ladder source binding mismatch for {role}"
            )
    subject_modality = replayed["declaration"]["subject"]["modality"].strip().lower()
    normalized_instruments = sorted({item.strip().lower() for item in instruments})
    allowed_modalities = set(normalized_instruments)
    if len(normalized_instruments) > 1:
        allowed_modalities.update({"multimodal", "multi-modal"})
    if subject_modality not in allowed_modalities:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder subject.modality is not represented by bundle instruments"
        )
    return {
        "contract": CONTRACT,
        "schema_version": RECORD_SCHEMA_VERSION,
        "policy_version": replayed["policy_version"],
        "assessment_file": {
            "path": assessment_path.name,
            "sha256": sha256_file(assessment_path),
            "size_bytes": assessment_path.stat().st_size,
        },
        "declaration_id": declaration_id,
        "declaration_sha256": replayed["declaration_sha256"],
        "assessment_sha256": replayed["assessment_sha256"],
        "subject": replayed["declaration"]["subject"],
        "source_bindings": replayed["declaration"]["source_bindings"],
        "highest_contiguous_supported_level": replayed[
            "highest_contiguous_supported_level"
        ],
        "first_blocking_level": replayed["first_blocking_level"],
        "non_supported_levels": replayed["non_supported_levels"],
        "readiness": replayed["readiness"],
        "case_id_bound": True,
        "source_digests_bound": True,
        "subject_modality_bound": True,
        "assessment_replayed": True,
        "empirical_evidence_created": False,
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "lower_level_evidence_preserved": True,
    }


__all__ = [
    "CharacterizationEvidenceLadderError",
    "CONTRACT",
    "LEVELS",
    "validate_characterization_evidence_ladder",
]
