"""Independently replay and validate characterization L0-L8 handoff evidence.

This module intentionally does not import ``materials-characterization-analyzer``.  The
consumer recomputes the producer's versioned evidence-ladder contract from the persisted
declaration and rejects any summary, source, subject, or byte substitution.

The ladder is planning metadata about evidence maturity.  It is not empirical evidence,
does not promote scientific status, and does not authorize downstream use.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .characterization_features import sha256_file

SCHEMA_VERSION = "1.0"
POLICY_VERSION = "1.0"
CONTRACT = "materials-characterization-scientific-evidence-ladder"
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
_REQUIRED_BUNDLE_BINDING_ROLES = {
    "source_manifest",
    "analysis_manifest",
    "comparability_matrix",
}


class CharacterizationEvidenceLadderError(ValueError):
    """Raised when the independent L0-L8 consumer cannot preserve the trust boundary."""


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
        raise CharacterizationEvidenceLadderError(
            "evidence ladder must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _exact_mapping(value: object, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CharacterizationEvidenceLadderError(f"{label} must be an object")
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    if missing:
        raise CharacterizationEvidenceLadderError(f"{label} is missing field: {missing[0]}")
    if unknown:
        raise CharacterizationEvidenceLadderError(f"{label} contains unknown field: {unknown[0]}")
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
    subject = _exact_mapping(value, _REQUIRED_SUBJECT_FIELDS, "subject")
    return {
        field: _text(subject[field], f"subject.{field}")
        for field in sorted(_REQUIRED_SUBJECT_FIELDS)
    }


def _normalize_bindings(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise CharacterizationEvidenceLadderError("source_bindings must be a non-empty list")
    result: list[dict[str, str]] = []
    roles: set[str] = set()
    for index, raw in enumerate(value):
        item = _exact_mapping(
            raw,
            _REQUIRED_BINDING_FIELDS,
            f"source_bindings[{index}]",
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
            _REQUIRED_LEVEL_FIELDS,
            f"levels.{level}",
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


def validate_evidence_ladder_declaration(value: object) -> dict[str, Any]:
    """Validate the strict declaration schema without promoting evidence."""
    root = _exact_mapping(value, _REQUIRED_ROOT_FIELDS, "evidence ladder declaration")
    if _text(root["schema_version"], "schema_version") != SCHEMA_VERSION:
        raise CharacterizationEvidenceLadderError(
            "unsupported evidence ladder schema_version"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "declaration_id": _text(root["declaration_id"], "declaration_id"),
        "subject": _normalize_subject(root["subject"]),
        "source_bindings": _normalize_bindings(root["source_bindings"]),
        "levels": _normalize_levels(root["levels"]),
        "limitations": _text_list(root["limitations"], "limitations", allow_empty=True),
    }


def evaluate_evidence_ladder(value: object) -> dict[str, Any]:
    """Recompute the producer contract deterministically from declaration input."""
    declaration = validate_evidence_ladder_declaration(value)
    highest_index = -1
    for index, level in enumerate(LEVELS):
        if declaration["levels"][level]["assessment"] != "Supported":
            break
        highest_index = index

    highest = LEVELS[highest_index] if highest_index >= 0 else None
    first_blocking = LEVELS[highest_index + 1] if highest_index + 1 < len(LEVELS) else None
    non_supported = [
        {
            "level": level,
            "assessment": declaration["levels"][level]["assessment"],
            "limitations": declaration["levels"][level]["limitations"],
        }
        for level in LEVELS
        if declaration["levels"][level]["assessment"] != "Supported"
    ]
    result = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "declaration": declaration,
        "declaration_sha256": _canonical_sha256(declaration),
        "highest_contiguous_supported_level": highest,
        "highest_contiguous_supported_index": highest_index,
        "first_blocking_level": first_blocking,
        "non_supported_levels": non_supported,
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
            "scientific evidence-ladder assessment declaration.levels must be an object"
        )
    raw_levels: dict[str, dict[str, Any]] = {}
    for level in LEVELS:
        item = levels.get(level)
        if not isinstance(item, Mapping):
            raise CharacterizationEvidenceLadderError(
                f"scientific evidence-ladder assessment declaration is missing level: {level}"
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


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise CharacterizationEvidenceLadderError(
            f"{label} must be a regular non-symlink file"
        )
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CharacterizationEvidenceLadderError(f"could not read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise CharacterizationEvidenceLadderError(f"{label} root must be an object")
    return payload


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CharacterizationEvidenceLadderError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _validated_assessment(path: Path) -> dict[str, Any]:
    payload = _load_json_object(path, "scientific evidence-ladder assessment")
    declaration = payload.get("declaration")
    if not isinstance(declaration, Mapping):
        raise CharacterizationEvidenceLadderError(
            "scientific evidence-ladder assessment must contain a declaration object"
        )
    replayed = evaluate_evidence_ladder(_raw_declaration_for_replay(declaration))
    if payload != replayed:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence-ladder assessment does not exactly match deterministic replay"
        )
    handoff = replayed.get("handoff")
    if not isinstance(handoff, dict):
        raise CharacterizationEvidenceLadderError("replayed evidence-ladder handoff is missing")
    if handoff.get("contract") != CONTRACT:
        raise CharacterizationEvidenceLadderError("evidence-ladder handoff contract mismatch")
    if handoff.get("scientific_status_promoted") is not False:
        raise CharacterizationEvidenceLadderError(
            "evidence ladder must not promote scientific status"
        )
    if handoff.get("downstream_use_authorized") is not False:
        raise CharacterizationEvidenceLadderError(
            "evidence ladder must not authorize downstream use"
        )
    if handoff.get("lower_level_evidence_preserved") is not True:
        raise CharacterizationEvidenceLadderError(
            "evidence ladder must preserve lower-level evidence"
        )
    return replayed


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _build_expected_record(path: Path, assessment: Mapping[str, Any]) -> dict[str, Any]:
    declaration = assessment["declaration"]
    handoff = assessment["handoff"]
    return {
        "contract": CONTRACT,
        "schema_version": RECORD_SCHEMA_VERSION,
        "policy_version": assessment["policy_version"],
        "assessment": _file_record(path),
        "declaration_id": declaration["declaration_id"],
        "declaration_sha256": assessment["declaration_sha256"],
        "assessment_sha256": assessment["assessment_sha256"],
        "subject": handoff["subject"],
        "source_bindings": handoff["source_bindings"],
        "highest_contiguous_supported_level": assessment[
            "highest_contiguous_supported_level"
        ],
        "first_blocking_level": assessment["first_blocking_level"],
        "readiness": assessment["readiness"],
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "lower_level_evidence_preserved": True,
    }


def _safe_assessment_path(root: Path, file_record: Mapping[str, Any]) -> Path:
    recorded = file_record.get("path")
    if not isinstance(recorded, str) or not recorded.strip():
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder.assessment.path must be a non-empty string"
        )
    normalized = recorded.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if relative.is_absolute() or len(relative.parts) != 1 or ".." in relative.parts or normalized in {"", "."}:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder assessment must be one direct safe sibling file"
        )
    path = root / relative.as_posix()
    if not path.is_file() or path.is_symlink():
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder assessment file is missing or unsafe"
        )
    try:
        path.resolve().relative_to(root)
    except ValueError as exc:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder assessment escapes bundle directory"
        ) from exc
    return path


def validate_scientific_evidence_ladder_record(
    *,
    bundle_root: str | Path,
    value: object,
    case_id: str,
    evidence_references: Mapping[str, Mapping[str, Any]],
    instruments: Sequence[str],
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    """Validate the complete schema-1.1 ladder extension and exact bundle binding."""
    root = Path(bundle_root).resolve()
    record = _exact_mapping(value, _RECORD_FIELDS, "scientific_evidence_ladder")
    if record.get("contract") != CONTRACT:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder contract mismatch"
        )
    if record.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise CharacterizationEvidenceLadderError(
            "unsupported scientific_evidence_ladder schema_version"
        )
    if record.get("policy_version") != POLICY_VERSION:
        raise CharacterizationEvidenceLadderError(
            "unsupported scientific_evidence_ladder policy_version"
        )

    file_record = _exact_mapping(
        record.get("assessment"),
        _FILE_RECORD_FIELDS,
        "scientific_evidence_ladder.assessment",
    )
    path = _safe_assessment_path(root, file_record)
    expected_sha = file_record.get("sha256")
    if not isinstance(expected_sha, str) or expected_sha != sha256_file(path):
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder assessment checksum mismatch"
        )
    expected_size = file_record.get("size_bytes")
    if isinstance(expected_size, bool) or not isinstance(expected_size, int):
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder assessment size_bytes must be an integer"
        )
    if expected_size != path.stat().st_size:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder assessment size_bytes mismatch"
        )

    assessment = _validated_assessment(path)
    expected_record = _build_expected_record(path, assessment)
    if dict(record) != expected_record:
        raise CharacterizationEvidenceLadderError(
            "scientific_evidence_ladder manifest summary does not match the replayed assessment"
        )
    if expected_record["declaration_id"] != case_id:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence-ladder declaration_id must equal bundle case_id"
        )

    binding_by_role = {
        str(item["role"]): str(item["sha256"])
        for item in expected_record["source_bindings"]
        if isinstance(item, Mapping) and "role" in item and "sha256" in item
    }
    for role in sorted(_REQUIRED_BUNDLE_BINDING_ROLES):
        reference = evidence_references.get(role)
        if not isinstance(reference, Mapping):
            raise CharacterizationEvidenceLadderError(
                f"bundle evidence reference is missing for ladder binding role: {role}"
            )
        if binding_by_role.get(role) != reference.get("sha256"):
            raise CharacterizationEvidenceLadderError(
                f"scientific evidence-ladder source binding does not match bundle evidence: {role}"
            )

    subject = expected_record.get("subject")
    if not isinstance(subject, Mapping):
        raise CharacterizationEvidenceLadderError(
            "scientific evidence-ladder subject must be an object"
        )
    modality = subject.get("modality")
    if not isinstance(modality, str) or not modality.strip():
        raise CharacterizationEvidenceLadderError(
            "scientific evidence-ladder subject.modality must be non-empty"
        )
    normalized_instruments = sorted(
        {item.strip().lower() for item in instruments if isinstance(item, str) and item.strip()}
    )
    allowed = set(normalized_instruments)
    if len(normalized_instruments) > 1:
        allowed.update({"multimodal", "multi-modal"})
    if modality.strip().lower() not in allowed:
        raise CharacterizationEvidenceLadderError(
            "scientific evidence-ladder subject.modality is not represented by bundle instruments"
        )

    return expected_record, path, assessment


__all__ = [
    "ASSESSMENTS",
    "CONTRACT",
    "LEVELS",
    "POLICY_VERSION",
    "RECORD_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "CharacterizationEvidenceLadderError",
    "evaluate_evidence_ladder",
    "validate_evidence_ladder_declaration",
    "validate_scientific_evidence_ladder_record",
]
