"""Fail-closed contracts for requirement-conditioned external evidence screening.

This module is intentionally domain-neutral. It evaluates whether a registered
candidate is sufficiently documented and semantically compatible to justify a
separate, predeclared acquisition/evaluation stage. It never downloads data,
fits a model, or authorizes an external-validation claim by itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"
CHECK_STATUSES = ("confirmed_match", "confirmed_mismatch", "unresolved")
SOURCE_INDEPENDENCE_STATUSES = (
    "confirmed_independent",
    "confirmed_not_independent",
    "unresolved",
)
AVAILABILITY_STATUSES = ("available", "unavailable")
LICENSE_STATUSES = ("confirmed_reusable", "restricted", "unresolved")
DISPOSITIONS = (
    "eligible",
    "diagnostic_only",
    "semantics_audit_required",
    "metadata_incomplete",
    "scientifically_ineligible",
    "unavailable",
)

_REQUIREMENT_FIELDS = {
    "schema_version",
    "requirement_id",
    "domain",
    "objective",
    "scientific_evidence_level",
    "source_independence_required",
    "prohibited_source_systems",
    "required_metadata_checks",
    "required_semantic_checks",
    "domain_requirements",
    "automatic_acquisition_authorized",
    "model_fit_authorized",
    "external_validation_claim_authorized",
    "source_binding",
    "scientific_boundary",
}
_CANDIDATE_FIELDS = {
    "schema_version",
    "candidate_id",
    "title",
    "source_system",
    "availability",
    "source_independence",
    "license_status",
    "metadata_checks",
    "semantic_checks",
    "notes",
}


class ExternalEvidenceContractError(ValueError):
    """Raised when an external-evidence requirement or candidate is malformed."""


@dataclass(frozen=True)
class ExternalEvidenceAssessment:
    requirement_id: str
    candidate_id: str
    disposition: str
    eligible_for_requirement: bool
    source_independence_satisfied: bool
    unresolved_metadata: tuple[str, ...]
    unresolved_semantics: tuple[str, ...]
    mismatches: tuple[str, ...]
    automatic_acquisition_authorized: bool
    model_fit_authorized: bool
    external_validation_claim_authorized: bool
    next_action: str
    scientific_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExternalEvidenceContractError(f"{field} must be a non-empty string")
    return value.strip()


def _string_list(value: object, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "a list" if allow_empty else "a non-empty list"
        raise ExternalEvidenceContractError(f"{field} must be {qualifier} of strings")
    normalized: list[str] = []
    for item in value:
        text = _nonempty_text(item, f"{field} item")
        if text in normalized:
            raise ExternalEvidenceContractError(f"{field} must not contain duplicates")
        normalized.append(text)
    return tuple(normalized)


def _status_map(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ExternalEvidenceContractError(f"{field} must be an object")
    result: dict[str, str] = {}
    for key, raw_status in value.items():
        name = _nonempty_text(key, f"{field} key")
        status = _nonempty_text(raw_status, f"{field}.{name}")
        if status not in CHECK_STATUSES:
            raise ExternalEvidenceContractError(
                f"{field}.{name} has unsupported status: {status!r}"
            )
        result[name] = status
    return result


def validate_external_evidence_requirement(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the stable generic requirement schema and fail closed on stronger actions."""
    if set(payload) != _REQUIREMENT_FIELDS:
        missing = sorted(_REQUIREMENT_FIELDS - set(payload))
        unknown = sorted(set(payload) - _REQUIREMENT_FIELDS)
        raise ExternalEvidenceContractError(
            f"external evidence requirement keys mismatch: missing={missing}, unknown={unknown}"
        )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ExternalEvidenceContractError("unsupported external evidence requirement schema_version")
    if payload.get("source_independence_required") is not True:
        raise ExternalEvidenceContractError("source_independence_required must be true")
    for field in (
        "automatic_acquisition_authorized",
        "model_fit_authorized",
        "external_validation_claim_authorized",
    ):
        if payload.get(field) is not False:
            raise ExternalEvidenceContractError(f"{field} must remain false at screening stage")

    requirement_id = _nonempty_text(payload.get("requirement_id"), "requirement_id")
    domain = _nonempty_text(payload.get("domain"), "domain")
    objective = _nonempty_text(payload.get("objective"), "objective")
    evidence_level = _nonempty_text(
        payload.get("scientific_evidence_level"), "scientific_evidence_level"
    )
    prohibited = _string_list(
        payload.get("prohibited_source_systems"), "prohibited_source_systems"
    )
    metadata_checks = _string_list(
        payload.get("required_metadata_checks"), "required_metadata_checks"
    )
    semantic_checks = _string_list(
        payload.get("required_semantic_checks"), "required_semantic_checks"
    )
    boundary = _string_list(payload.get("scientific_boundary"), "scientific_boundary")
    domain_requirements = payload.get("domain_requirements")
    source_binding = payload.get("source_binding")
    if not isinstance(domain_requirements, Mapping) or not domain_requirements:
        raise ExternalEvidenceContractError("domain_requirements must be a non-empty object")
    if not isinstance(source_binding, Mapping) or not source_binding:
        raise ExternalEvidenceContractError("source_binding must be a non-empty object")

    return {
        **dict(payload),
        "requirement_id": requirement_id,
        "domain": domain,
        "objective": objective,
        "scientific_evidence_level": evidence_level,
        "prohibited_source_systems": list(prohibited),
        "required_metadata_checks": list(metadata_checks),
        "required_semantic_checks": list(semantic_checks),
        "scientific_boundary": list(boundary),
        "domain_requirements": dict(domain_requirements),
        "source_binding": dict(source_binding),
    }


def evaluate_external_source_candidate(
    requirement: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> ExternalEvidenceAssessment:
    """Evaluate one candidate without downloading data or upgrading scientific evidence."""
    req = validate_external_evidence_requirement(requirement)
    if set(candidate) != _CANDIDATE_FIELDS:
        missing = sorted(_CANDIDATE_FIELDS - set(candidate))
        unknown = sorted(set(candidate) - _CANDIDATE_FIELDS)
        raise ExternalEvidenceContractError(
            f"external source candidate keys mismatch: missing={missing}, unknown={unknown}"
        )
    if candidate.get("schema_version") != SCHEMA_VERSION:
        raise ExternalEvidenceContractError("unsupported external source candidate schema_version")

    candidate_id = _nonempty_text(candidate.get("candidate_id"), "candidate_id")
    _nonempty_text(candidate.get("title"), "title")
    source_system = _nonempty_text(candidate.get("source_system"), "source_system")
    availability = _nonempty_text(candidate.get("availability"), "availability")
    if availability not in AVAILABILITY_STATUSES:
        raise ExternalEvidenceContractError(f"unsupported availability: {availability!r}")
    independence = _nonempty_text(candidate.get("source_independence"), "source_independence")
    if independence not in SOURCE_INDEPENDENCE_STATUSES:
        raise ExternalEvidenceContractError(
            f"unsupported source_independence: {independence!r}"
        )
    license_status = _nonempty_text(candidate.get("license_status"), "license_status")
    if license_status not in LICENSE_STATUSES:
        raise ExternalEvidenceContractError(
            f"unsupported license_status: {license_status!r}"
        )
    metadata = _status_map(candidate.get("metadata_checks"), "metadata_checks")
    semantics = _status_map(candidate.get("semantic_checks"), "semantic_checks")
    _string_list(candidate.get("notes"), "notes", allow_empty=True)

    required_metadata = set(req["required_metadata_checks"])
    required_semantics = set(req["required_semantic_checks"])
    missing_metadata = sorted(required_metadata - set(metadata))
    missing_semantics = sorted(required_semantics - set(semantics))
    if missing_metadata or missing_semantics:
        raise ExternalEvidenceContractError(
            "candidate does not cover all required checks: "
            f"metadata={missing_metadata}, semantics={missing_semantics}"
        )

    unresolved_metadata = tuple(
        sorted(name for name in required_metadata if metadata[name] == "unresolved")
    )
    unresolved_semantics = tuple(
        sorted(name for name in required_semantics if semantics[name] == "unresolved")
    )
    mismatches = tuple(
        sorted(
            [name for name in required_metadata if metadata[name] == "confirmed_mismatch"]
            + [name for name in required_semantics if semantics[name] == "confirmed_mismatch"]
        )
    )
    prohibited_source = source_system in set(req["prohibited_source_systems"])
    source_independence_satisfied = (
        independence == "confirmed_independent" and not prohibited_source
    )

    if availability == "unavailable":
        disposition = "unavailable"
        next_action = "Record source unavailability and continue requirement-conditioned search."
    elif license_status == "restricted":
        disposition = "scientifically_ineligible"
        next_action = (
            "Preserve the reuse restriction; do not acquire or fit this candidate for the requirement."
        )
    elif mismatches:
        disposition = "scientifically_ineligible"
        next_action = "Preserve the mismatch; do not acquire or fit this candidate for the requirement."
    elif independence == "confirmed_not_independent" or prohibited_source:
        disposition = "diagnostic_only"
        next_action = (
            "Candidate may support diagnostics only; confirmed source dependence prevents it from "
            "satisfying source-disjoint external evidence."
        )
    elif license_status == "unresolved" or independence == "unresolved" or unresolved_metadata:
        disposition = "metadata_incomplete"
        next_action = "Resolve authoritative provenance, reuse, and metadata before data acquisition."
    elif unresolved_semantics:
        disposition = "semantics_audit_required"
        next_action = "Resolve target/method semantics before data acquisition or model fitting."
    else:
        disposition = "eligible"
        next_action = (
            "Predeclare and freeze a controlled acquisition/evaluation protocol before retrieving "
            "candidate target data."
        )

    return ExternalEvidenceAssessment(
        requirement_id=str(req["requirement_id"]),
        candidate_id=candidate_id,
        disposition=disposition,
        eligible_for_requirement=disposition == "eligible",
        source_independence_satisfied=source_independence_satisfied,
        unresolved_metadata=unresolved_metadata,
        unresolved_semantics=unresolved_semantics,
        mismatches=mismatches,
        automatic_acquisition_authorized=False,
        model_fit_authorized=False,
        external_validation_claim_authorized=False,
        next_action=next_action,
        scientific_boundary=(
            "Candidate screening establishes requirement compatibility only. It does not establish "
            "dataset-level independence, predictive validity, causal validity, or external-validation "
            "evidence, and it never authorizes automatic acquisition or model fitting."
        ),
    )


__all__ = [
    "DISPOSITIONS",
    "ExternalEvidenceAssessment",
    "ExternalEvidenceContractError",
    "evaluate_external_source_candidate",
    "validate_external_evidence_requirement",
]
