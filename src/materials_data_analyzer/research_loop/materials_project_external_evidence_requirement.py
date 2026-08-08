"""Generate an external-evidence requirement after Materials Project same-source exhaustion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from config import PROJECT_ROOT
from materials_data_analyzer.research_loop.external_evidence_contract import (
    ExternalEvidenceContractError,
    validate_external_evidence_requirement,
)
from platform_core.output_safety import transactional_output_directory

SCHEMA_VERSION = "1.0"
OUTPUT_NAME = "external_evidence_requirement.json"
_CONFIG_FIELDS = {
    "schema_version",
    "requirement_id",
    "expected_readiness_id",
    "expected_source_outcome",
    "domain",
    "objective",
    "scientific_evidence_level",
    "prohibited_source_systems",
    "required_metadata_checks",
    "required_semantic_checks",
    "domain_requirements",
    "scientific_boundary",
}


class MaterialsProjectExternalEvidenceRequirementError(ValueError):
    """Raised when the Materials Project readiness result cannot justify this requirement."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MaterialsProjectExternalEvidenceRequirementError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise MaterialsProjectExternalEvidenceRequirementError(
            f"invalid JSON in {resolved}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise MaterialsProjectExternalEvidenceRequirementError(
            f"JSON root must be an object: {resolved}"
        )
    return payload


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    if set(config) != _CONFIG_FIELDS or config.get("schema_version") != SCHEMA_VERSION:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "Materials Project external evidence config keys/schema do not match contract"
        )
    for field in (
        "requirement_id",
        "expected_readiness_id",
        "expected_source_outcome",
        "domain",
        "objective",
        "scientific_evidence_level",
    ):
        value = config.get(field)
        if not isinstance(value, str) or not value.strip():
            raise MaterialsProjectExternalEvidenceRequirementError(
                f"config field must be a non-empty string: {field}"
            )
    for field in (
        "prohibited_source_systems",
        "required_metadata_checks",
        "required_semantic_checks",
        "scientific_boundary",
    ):
        value = config.get(field)
        if not isinstance(value, list) or not value or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise MaterialsProjectExternalEvidenceRequirementError(
                f"config field must be a non-empty string list: {field}"
            )
        if len(value) != len(set(value)):
            raise MaterialsProjectExternalEvidenceRequirementError(
                f"config field must not contain duplicates: {field}"
            )
    if not isinstance(config.get("domain_requirements"), Mapping) or not config[
        "domain_requirements"
    ]:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "domain_requirements must be a non-empty object"
        )
    return config


def _require_mapping(parent: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = parent.get(field)
    if not isinstance(value, Mapping):
        raise MaterialsProjectExternalEvidenceRequirementError(
            f"readiness field must be an object: {field}"
        )
    return value


def _validate_readiness(readiness: dict[str, Any], config: Mapping[str, Any]) -> None:
    if readiness.get("schema_version") != SCHEMA_VERSION:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "unsupported Materials Project readiness schema_version"
        )
    if readiness.get("readiness_id") != config["expected_readiness_id"]:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "readiness_id does not match the external-evidence requirement contract"
        )
    if readiness.get("execution_status") != "same_source_identity_inventory_completed":
        raise MaterialsProjectExternalEvidenceRequirementError(
            "same-source identity inventory must be completed first"
        )
    if readiness.get("scientific_evidence_level") != "DevelopmentDiagnostic":
        raise MaterialsProjectExternalEvidenceRequirementError(
            "unexpected readiness scientific evidence level"
        )
    if readiness.get("source_outcome") != config["expected_source_outcome"]:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "source-disjoint requirement is only valid after no new same-source cohort is found"
        )

    independence = _require_mapping(readiness, "cohort_independence")
    if independence.get("same_source_system") is not True:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "readiness result no longer represents a same-source Materials Project inventory"
        )
    if independence.get("source_system") != "Materials Project":
        raise MaterialsProjectExternalEvidenceRequirementError(
            "unexpected readiness source system"
        )
    if independence.get("source_independence_established") is not False:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "readiness result unexpectedly claims source independence"
        )
    if independence.get("external_validation_ready") is not False:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "readiness result unexpectedly claims external-validation readiness"
        )

    current = _require_mapping(readiness, "current_identity_query")
    if current.get("identity_fields_only") is not True:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "readiness must remain an identity-only query"
        )
    for field in ("target_property_queried", "model_fit", "policy_executed"):
        if current.get(field) is not False:
            raise MaterialsProjectExternalEvidenceRequirementError(
                f"readiness boundary violated: {field}"
            )

    overlap = _require_mapping(readiness, "overlap")
    candidates = _require_mapping(readiness, "independent_candidate_inventory")
    if overlap.get("new_material_ids_after_original_exclusion") != 0:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "new same-source material IDs exist; source-disjoint exhaustion is not established"
        )
    if candidates.get("rows") != 0 or candidates.get("target_values_used") is not False:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "same-source candidate inventory must be empty and target-blind"
        )
    if readiness.get("policy_v2_freeze_authorized") is not False:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "policy-v2 freeze must remain unauthorized"
        )
    if readiness.get("independent_benchmark_execution_authorized") is not False:
        raise MaterialsProjectExternalEvidenceRequirementError(
            "independent benchmark execution must remain unauthorized"
        )


def build_materials_project_external_evidence_requirement(
    *,
    readiness_path: str | Path,
    config_path: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create the exact source-disjoint requirement without querying candidate targets."""
    readiness_resolved = Path(readiness_path).expanduser().resolve(strict=True)
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    readiness = _load_json(readiness_resolved)
    _validate_readiness(readiness, config)

    original = _require_mapping(readiness, "original_benchmark")
    current = _require_mapping(readiness, "current_identity_query")
    overlap = _require_mapping(readiness, "overlap")
    source_binding = {
        "readiness_filename": readiness_resolved.name,
        "readiness_sha256": _sha256_file(readiness_resolved),
        "requirement_config_sha256": _sha256_file(config_resolved),
        "readiness_id": readiness["readiness_id"],
        "materials_project_database_version": readiness.get(
            "materials_project_database_version"
        ),
        "original_benchmark_id": original.get("benchmark_id"),
        "original_benchmark_rows": original.get("rows"),
        "current_identity_rows": current.get("rows"),
        "new_same_source_material_ids": overlap.get(
            "new_material_ids_after_original_exclusion"
        ),
    }
    requirement = {
        "schema_version": SCHEMA_VERSION,
        "requirement_id": config["requirement_id"],
        "domain": config["domain"],
        "objective": config["objective"],
        "scientific_evidence_level": config["scientific_evidence_level"],
        "source_independence_required": True,
        "prohibited_source_systems": list(config["prohibited_source_systems"]),
        "required_metadata_checks": list(config["required_metadata_checks"]),
        "required_semantic_checks": list(config["required_semantic_checks"]),
        "domain_requirements": dict(config["domain_requirements"]),
        "automatic_acquisition_authorized": False,
        "model_fit_authorized": False,
        "external_validation_claim_authorized": False,
        "source_binding": source_binding,
        "scientific_boundary": list(config["scientific_boundary"]),
    }
    try:
        validated = validate_external_evidence_requirement(requirement)
    except ExternalEvidenceContractError as exc:
        raise MaterialsProjectExternalEvidenceRequirementError(str(exc)) from exc

    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        protected_paths=(readiness_resolved, config_resolved, PROJECT_ROOT),
        recognized_markers=(OUTPUT_NAME,),
    ) as staging:
        (staging / OUTPUT_NAME).write_text(
            json.dumps(validated, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return validated


__all__ = [
    "MaterialsProjectExternalEvidenceRequirementError",
    "build_materials_project_external_evidence_requirement",
]
