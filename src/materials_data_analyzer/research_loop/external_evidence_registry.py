"""Deterministic no-network audit for registered external-evidence candidates."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from config import PROJECT_ROOT
from materials_data_analyzer.research_loop.external_evidence_contract import (
    ExternalEvidenceContractError,
    evaluate_external_source_candidate,
    validate_external_evidence_requirement,
)
from platform_core.output_safety import transactional_output_directory

SCHEMA_VERSION = "1.0"
JSON_OUTPUT_NAME = "external_source_candidate_assessments.json"
CSV_OUTPUT_NAME = "external_source_candidate_assessments.csv"
_REGISTRY_FIELDS = {
    "schema_version",
    "registry_id",
    "scientific_scope",
    "candidates",
}


class ExternalEvidenceRegistryError(ValueError):
    """Raised when a registry or deterministic candidate audit is malformed."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExternalEvidenceRegistryError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise ExternalEvidenceRegistryError(f"invalid JSON in {resolved}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExternalEvidenceRegistryError(f"JSON root must be an object: {resolved}")
    return payload


def _validate_registry(payload: Mapping[str, Any]) -> dict[str, Any]:
    if set(payload) != _REGISTRY_FIELDS:
        missing = sorted(_REGISTRY_FIELDS - set(payload))
        unknown = sorted(set(payload) - _REGISTRY_FIELDS)
        raise ExternalEvidenceRegistryError(
            f"external evidence registry keys mismatch: missing={missing}, unknown={unknown}"
        )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ExternalEvidenceRegistryError("unsupported external evidence registry schema_version")
    registry_id = payload.get("registry_id")
    scientific_scope = payload.get("scientific_scope")
    if not isinstance(registry_id, str) or not registry_id.strip():
        raise ExternalEvidenceRegistryError("registry_id must be a non-empty string")
    if not isinstance(scientific_scope, str) or not scientific_scope.strip():
        raise ExternalEvidenceRegistryError("scientific_scope must be a non-empty string")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ExternalEvidenceRegistryError("candidates must be a non-empty list")
    candidate_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw in candidates:
        if not isinstance(raw, Mapping):
            raise ExternalEvidenceRegistryError("each candidate must be an object")
        candidate = dict(raw)
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise ExternalEvidenceRegistryError("candidate_id must be a non-empty string")
        if candidate_id in candidate_ids:
            raise ExternalEvidenceRegistryError(f"duplicate candidate_id: {candidate_id}")
        candidate_ids.add(candidate_id)
        normalized.append(candidate)
    return {
        "schema_version": SCHEMA_VERSION,
        "registry_id": registry_id.strip(),
        "scientific_scope": scientific_scope.strip(),
        "candidates": normalized,
    }


def audit_external_evidence_registry(
    *,
    requirement_path: str | Path,
    registry_path: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Evaluate all registered candidates without network access or target retrieval."""
    requirement_resolved = Path(requirement_path).expanduser().resolve(strict=True)
    registry_resolved = Path(registry_path).expanduser().resolve(strict=True)
    try:
        requirement = validate_external_evidence_requirement(_load_json(requirement_resolved))
    except ExternalEvidenceContractError as exc:
        raise ExternalEvidenceRegistryError(str(exc)) from exc
    registry = _validate_registry(_load_json(registry_resolved))

    assessments: list[dict[str, Any]] = []
    for candidate in registry["candidates"]:
        try:
            decision = evaluate_external_source_candidate(requirement, candidate)
        except ExternalEvidenceContractError as exc:
            candidate_id = candidate.get("candidate_id", "<unknown>")
            raise ExternalEvidenceRegistryError(
                f"candidate {candidate_id!r} violates external-evidence contract: {exc}"
            ) from exc
        assessments.append(decision.to_dict())

    disposition_counts: dict[str, int] = {}
    for assessment in assessments:
        disposition = str(assessment["disposition"])
        disposition_counts[disposition] = disposition_counts.get(disposition, 0) + 1

    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "external_source_candidate_screening_completed",
        "requirement_id": requirement["requirement_id"],
        "registry_id": registry["registry_id"],
        "candidate_count": len(assessments),
        "eligible_candidate_count": sum(
            1 for assessment in assessments if assessment["eligible_for_requirement"]
        ),
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "network_access_performed": False,
        "target_values_retrieved": False,
        "model_fit_performed": False,
        "external_validation_claim_authorized": False,
        "assessments": assessments,
        "scientific_boundary": (
            "This artifact records source-screening dispositions only. It does not establish "
            "dataset-level independence, target comparability beyond the registered evidence, "
            "predictive validity, or external-validation evidence."
        ),
    }

    with transactional_output_directory(
        output_dir,
        overwrite=overwrite,
        protected_paths=(requirement_resolved, registry_resolved, PROJECT_ROOT),
        recognized_markers=(JSON_OUTPUT_NAME,),
    ) as staging:
        (staging / JSON_OUTPUT_NAME).write_text(
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        with (staging / CSV_OUTPUT_NAME).open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            fieldnames = [
                "candidate_id",
                "disposition",
                "eligible_for_requirement",
                "source_independence_satisfied",
                "unresolved_metadata",
                "unresolved_semantics",
                "mismatches",
                "next_action",
            ]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for assessment in assessments:
                writer.writerow(
                    {
                        "candidate_id": assessment["candidate_id"],
                        "disposition": assessment["disposition"],
                        "eligible_for_requirement": assessment[
                            "eligible_for_requirement"
                        ],
                        "source_independence_satisfied": assessment[
                            "source_independence_satisfied"
                        ],
                        "unresolved_metadata": ";".join(
                            assessment["unresolved_metadata"]
                        ),
                        "unresolved_semantics": ";".join(
                            assessment["unresolved_semantics"]
                        ),
                        "mismatches": ";".join(assessment["mismatches"]),
                        "next_action": assessment["next_action"],
                    }
                )
    return result


__all__ = [
    "ExternalEvidenceRegistryError",
    "audit_external_evidence_registry",
]
