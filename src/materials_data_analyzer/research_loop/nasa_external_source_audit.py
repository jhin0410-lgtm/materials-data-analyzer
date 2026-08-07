"""Fail-closed audit of external battery-source candidates for NASA research."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
AUDIT_SCHEMA_VERSION = "1.0"
_ALLOWED_SEMANTIC_STATUS = {
    "unresolved",
    "confirmed_match",
    "confirmed_mismatch",
}


class NasaExternalSourceAuditError(ValueError):
    """Raised when an external-source candidate or requirement is invalid."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NasaExternalSourceAuditError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_json(path: str | Path) -> Any:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise NasaExternalSourceAuditError(
            f"invalid JSON in {resolved}: {exc}"
        ) from exc


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NasaExternalSourceAuditError(f"{field} must be a JSON object")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise NasaExternalSourceAuditError(f"{field} must be boolean")
    return value


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise NasaExternalSourceAuditError(f"{field} must be a positive integer")
    return value


def _require_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NasaExternalSourceAuditError(f"{field} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise NasaExternalSourceAuditError(f"{field} must be finite")
    return normalized


def _validate_requirement(value: Any) -> dict[str, Any]:
    requirement = _require_dict(value, "external evidence requirement")
    if requirement.get("schema_version") != SCHEMA_VERSION:
        raise NasaExternalSourceAuditError("unsupported requirement schema_version")
    if requirement.get("blocker") != "protocol_groups_too_small":
        raise NasaExternalSourceAuditError(
            "source audit currently supports protocol_groups_too_small only"
        )
    if requirement.get("current_evidence_level") != "Unsupported":
        raise NasaExternalSourceAuditError(
            "source audit may not start from upgraded predictive evidence"
        )
    if requirement.get("status") != "Diagnostic":
        raise NasaExternalSourceAuditError(
            "external evidence requirement must remain Diagnostic"
        )

    source_design = _require_dict(
        requirement.get("source_cohort_design"), "source_cohort_design"
    )
    if not _require_bool(
        source_design.get("unrelated_source_cohort_counts_may_not_be_pooled"),
        "source_cohort_design.unrelated_source_cohort_counts_may_not_be_pooled",
    ):
        raise NasaExternalSourceAuditError(
            "requirement must prohibit unrelated-source count pooling"
        )
    if not _require_bool(
        source_design.get("temperature_and_source_cohort_must_not_be_perfectly_confounded"),
        "source_cohort_design.temperature_and_source_cohort_must_not_be_perfectly_confounded",
    ):
        raise NasaExternalSourceAuditError(
            "requirement must guard source-temperature confounding"
        )
    _require_positive_int(
        source_design.get("new_source_cohort_minimum_exact_groups"),
        "source_cohort_design.new_source_cohort_minimum_exact_groups",
    )
    _require_positive_int(
        source_design.get("new_source_cohort_minimum_evaluated_batteries_per_exact_group"),
        "source_cohort_design.new_source_cohort_minimum_evaluated_batteries_per_exact_group",
    )
    return requirement


def _validate_registry(value: Any) -> dict[str, Any]:
    registry = _require_dict(value, "candidate registry")
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise NasaExternalSourceAuditError("unsupported candidate registry schema_version")
    candidates = registry.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise NasaExternalSourceAuditError("candidate registry must contain candidates")
    identifiers: list[str] = []
    for index, raw_candidate in enumerate(candidates):
        candidate = _require_dict(raw_candidate, f"candidates[{index}]")
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise NasaExternalSourceAuditError(
                f"candidates[{index}].candidate_id must be a non-empty string"
            )
        identifiers.append(candidate_id)
    if len(identifiers) != len(set(identifiers)):
        raise NasaExternalSourceAuditError("candidate_id values must be unique")
    return registry


def _semantic_value(metadata: dict[str, Any], field: str) -> str:
    value = metadata.get(field)
    if value not in _ALLOWED_SEMANTIC_STATUS:
        raise NasaExternalSourceAuditError(
            f"candidate {field} has unsupported value"
        )
    return str(value)


def _audit_candidate(
    candidate: dict[str, Any], requirement: dict[str, Any]
) -> dict[str, Any]:
    source_design = _require_dict(
        requirement["source_cohort_design"], "source_cohort_design"
    )
    minimum_groups = _require_positive_int(
        source_design["new_source_cohort_minimum_exact_groups"],
        "new_source_cohort_minimum_exact_groups",
    )
    minimum_per_group = _require_positive_int(
        source_design["new_source_cohort_minimum_evaluated_batteries_per_exact_group"],
        "new_source_cohort_minimum_evaluated_batteries_per_exact_group",
    )

    design = _require_dict(candidate.get("cyclic_design"), "candidate.cyclic_design")
    metadata = _require_dict(
        candidate.get("metadata_assertions"), "candidate.metadata_assertions"
    )
    temperatures = design.get("temperatures_c")
    if not isinstance(temperatures, list):
        raise NasaExternalSourceAuditError(
            "candidate.cyclic_design.temperatures_c must be a JSON array"
        )
    normalized_temperatures = [
        _require_number(value, "candidate.cyclic_design.temperatures_c item")
        for value in temperatures
    ]
    if len(normalized_temperatures) != len(set(normalized_temperatures)):
        raise NasaExternalSourceAuditError(
            "candidate exact-temperature values must not contain duplicates"
        )

    lower_bound = _require_positive_int(
        design.get("minimum_batteries_per_temperature_lower_bound"),
        "candidate.cyclic_design.minimum_batteries_per_temperature_lower_bound",
    )

    structural_checks = {
        "independent_source_cohort": _require_bool(
            metadata.get("independent_from_nasa"),
            "candidate.metadata_assertions.independent_from_nasa",
        ),
        "source_cohort_identity_confirmed": _require_bool(
            metadata.get("source_cohort_identity_confirmed"),
            "candidate.metadata_assertions.source_cohort_identity_confirmed",
        ),
        "stable_battery_identifier_available": _require_bool(
            metadata.get("stable_battery_identifier_available"),
            "candidate.metadata_assertions.stable_battery_identifier_available",
        ),
        "source_recorded_temperature_available": _require_bool(
            metadata.get("source_recorded_temperature_available"),
            "candidate.metadata_assertions.source_recorded_temperature_available",
        ),
        "capacity_measurements_available": _require_bool(
            metadata.get("result_data_contains_capacity_measurements"),
            "candidate.metadata_assertions.result_data_contains_capacity_measurements",
        ),
        "license_confirmed": _require_bool(
            metadata.get("license_confirmed"),
            "candidate.metadata_assertions.license_confirmed",
        ),
        "minimum_exact_groups_met": len(normalized_temperatures) >= minimum_groups,
        "minimum_support_per_exact_group_met": lower_bound >= minimum_per_group,
        "source_temperature_crossing_confirmed": _require_bool(
            design.get("temperature_crossed_with_other_factors"),
            "candidate.cyclic_design.temperature_crossed_with_other_factors",
        ),
    }
    structural_blockers = [
        name for name, passed in structural_checks.items() if not passed
    ]

    semantic_status = {
        "protocol_temperature_semantics": _semantic_value(
            metadata, "protocol_temperature_semantics"
        ),
        "exact_horizon_semantics": _semantic_value(
            metadata, "exact_horizon_semantics"
        ),
        "target_reference_semantics": _semantic_value(
            metadata, "target_reference_semantics"
        ),
    }
    semantic_blockers: list[str] = []
    for field, status in semantic_status.items():
        if status == "unresolved":
            semantic_blockers.append(f"{field}_unresolved")
        elif status == "confirmed_mismatch":
            semantic_blockers.append(f"{field}_mismatch")

    if structural_blockers:
        disposition = "structurally_ineligible"
    elif "confirmed_mismatch" in set(semantic_status.values()):
        disposition = "scientifically_ineligible"
    elif semantic_blockers:
        disposition = "semantics_audit_required"
    else:
        disposition = "predeclared_diagnostic_eligible"

    known_events = candidate.get("known_data_quality_events", [])
    if not isinstance(known_events, list) or not all(
        isinstance(item, str) and item.strip() for item in known_events
    ):
        raise NasaExternalSourceAuditError(
            "candidate.known_data_quality_events must contain non-empty strings"
        )

    return {
        "candidate_id": candidate["candidate_id"],
        "title": candidate.get("title"),
        "source_cohort_id": candidate.get("source_cohort_id"),
        "disposition": disposition,
        "eligible_for_predeclared_diagnostic": (
            disposition == "predeclared_diagnostic_eligible"
        ),
        "eligible_for_external_validation_claim": False,
        "structural_checks": structural_checks,
        "structural_blockers": structural_blockers,
        "semantic_status": semantic_status,
        "semantic_blockers": semantic_blockers,
        "exact_temperatures_c": normalized_temperatures,
        "minimum_batteries_per_temperature_lower_bound": lower_bound,
        "known_data_quality_events": known_events,
        "required_next_step": (
            "Verify protocol-temperature, exact-horizon, and target/reference "
            "semantics from authoritative source documentation and the result-file "
            "schema before any model ingestion."
            if disposition == "semantics_audit_required"
            else None
        ),
    }


def audit_external_source_candidates(
    requirement_file: str | Path,
    registry_file: str | Path,
) -> dict[str, Any]:
    """Audit candidates without downloading data or upgrading scientific evidence."""
    requirement = _validate_requirement(_load_json(requirement_file))
    registry = _validate_registry(_load_json(registry_file))
    audits = [
        _audit_candidate(_require_dict(candidate, "candidate"), requirement)
        for candidate in registry["candidates"]
    ]
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "audit_type": "nasa_external_source_candidate_audit",
        "requirement_blocker": requirement["blocker"],
        "input_evidence_level": requirement["current_evidence_level"],
        "output_evidence_level": "Unsupported",
        "scientific_status": "Diagnostic",
        "registry_id": registry.get("registry_id"),
        "candidate_count": len(audits),
        "candidates": audits,
        "scientific_boundary": (
            "Candidate screening does not create external validation evidence. "
            "A candidate is blocked until protocol-temperature, exact-horizon, and "
            "target/reference semantics match the predeclared NASA analysis contract. "
            "Unrelated source cohorts are never pooled to fill NASA temperature deficits."
        ),
    }
