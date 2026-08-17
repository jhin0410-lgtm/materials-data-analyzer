"""Federated scientific-evidence classification without scientific promotion.

The federation layer lets heterogeneous sources participate in one research episode while
preserving their different epistemic strength.  It never converts discovery metadata,
reported literature values, digitized figures, simulations, or reference context into raw
experimental evidence.  Claim eligibility remains the responsibility of downstream
scientific gates.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from .kernel import ResearchLoopError

EVIDENCE_FEDERATION_SCHEMA_VERSION = "1.0"


class EvidenceFederationError(ResearchLoopError):
    """Raised when heterogeneous evidence cannot be represented without inference."""


class EvidenceClass(str, Enum):
    E0_RAW_EXPERIMENTAL = "E0_raw_experimental"
    E1_PROCESSED_EXPERIMENTAL = "E1_processed_experimental"
    E2_PUBLICATION_SUPPLEMENT = "E2_publication_supplement"
    E3_PAPER_TABLE = "E3_paper_table"
    E4_FIGURE_DIGITIZED = "E4_figure_digitized"
    E5_LITERATURE_CLAIM = "E5_literature_claim"
    E6_COMPUTATIONAL = "E6_computational"
    E7_REFERENCE_CONTEXT = "E7_reference_context"


_ALLOWED = {
    "source_authority": {"authoritative", "repository_curated", "peer_reviewed", "declared", "unknown"},
    "representation": {"raw", "processed", "supplementary", "table", "digitized", "narrative", "computational", "reference"},
    "sample_identity": {"exact", "partial", "unknown", "not_applicable"},
    "acquisition_identity": {"exact", "partial", "unknown", "not_applicable"},
    "calibration": {"traceable", "reported", "unknown", "not_applicable"},
    "independence": {"independent", "same_source", "unresolved", "not_applicable"},
    "comparability": {"exact", "adjacent", "incompatible", "unresolved"},
    "reuse": {"allowed", "restricted", "unknown"},
    "extraction": {"native", "underlying_data", "table", "digitized", "narrative", "computational", "reference"},
}

_MAXIMUM_USE = {
    EvidenceClass.E0_RAW_EXPERIMENTAL: "measurement_eligible_after_scientific_intake",
    EvidenceClass.E1_PROCESSED_EXPERIMENTAL: "measurement_eligible_after_scientific_intake",
    EvidenceClass.E2_PUBLICATION_SUPPLEMENT: "measurement_eligible_after_semantic_binding",
    EvidenceClass.E3_PAPER_TABLE: "reported_measurement_only",
    EvidenceClass.E4_FIGURE_DIGITIZED: "diagnostic_quantitative_only",
    EvidenceClass.E5_LITERATURE_CLAIM: "qualitative_claim_only",
    EvidenceClass.E6_COMPUTATIONAL: "computational_support_only",
    EvidenceClass.E7_REFERENCE_CONTEXT: "context_constraint_only",
}


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceFederationError(f"{field} must be non-empty text")
    if value != value.strip():
        raise EvidenceFederationError(f"{field} must not contain edge whitespace")
    return value


def _choice(value: object, field: str) -> str:
    text = _text(value, field)
    if text not in _ALLOWED[field]:
        raise EvidenceFederationError(f"{field} must be one of {sorted(_ALLOWED[field])}")
    return text


def canonical_sha256(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidenceFederationError("value must be canonical-JSON serializable") from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class EvidenceTrustVector:
    source_authority: str
    representation: str
    sample_identity: str
    acquisition_identity: str
    calibration: str
    independence: str
    comparability: str
    reuse: str
    extraction: str

    def __post_init__(self) -> None:
        for field in _ALLOWED:
            object.__setattr__(self, field, _choice(getattr(self, field), field))


@dataclass(frozen=True)
class FederatedEvidenceCandidate:
    provider: str
    source_id: str
    title: str
    evidence_class: EvidenceClass
    trust: EvidenceTrustVector
    source_locator: str
    artifact_sha256: str | None = None
    related_identifiers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in ("provider", "source_id", "title", "source_locator"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        if not isinstance(self.evidence_class, EvidenceClass):
            raise EvidenceFederationError("evidence_class must be EvidenceClass")
        if not isinstance(self.trust, EvidenceTrustVector):
            raise EvidenceFederationError("trust must be EvidenceTrustVector")
        if self.artifact_sha256 is not None:
            digest = self.artifact_sha256.lower()
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise EvidenceFederationError("artifact_sha256 must be lowercase SHA-256")
            object.__setattr__(self, "artifact_sha256", digest)
        normalized_related: list[str] = []
        for value in self.related_identifiers:
            text = _text(value, "related_identifier")
            if text not in normalized_related:
                normalized_related.append(text)
        object.__setattr__(self, "related_identifiers", tuple(normalized_related))

    @property
    def candidate_id(self) -> str:
        identity = {
            "provider": self.provider,
            "source_id": self.source_id,
            "source_locator": self.source_locator,
            "evidence_class": self.evidence_class.value,
            "artifact_sha256": self.artifact_sha256,
        }
        return "federated-evidence:" + canonical_sha256(identity)[:24]

    def record(self) -> dict[str, Any]:
        return {
            "schema_version": EVIDENCE_FEDERATION_SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "provider": self.provider,
            "source_id": self.source_id,
            "title": self.title,
            "evidence_class": self.evidence_class.value,
            "trust_vector": asdict(self.trust),
            "source_locator": self.source_locator,
            "artifact_sha256": self.artifact_sha256,
            "related_identifiers": list(self.related_identifiers),
            "maximum_use_before_additional_review": _MAXIMUM_USE[self.evidence_class],
            "requires_scientific_intake": True,
            "scientific_status_changed": False,
            "search_or_catalog_hit_is_scientific_evidence": False,
        }


def maximum_evidence_use(candidate: FederatedEvidenceCandidate) -> dict[str, Any]:
    """Return an upper bound, never an automatic scientific approval."""
    base = _MAXIMUM_USE[candidate.evidence_class]
    blockers: list[str] = []
    trust = candidate.trust
    if trust.reuse != "allowed":
        blockers.append("reuse_not_explicitly_allowed")
    if trust.comparability in {"incompatible", "unresolved"}:
        blockers.append("comparability_not_established")
    if candidate.evidence_class in {
        EvidenceClass.E0_RAW_EXPERIMENTAL,
        EvidenceClass.E1_PROCESSED_EXPERIMENTAL,
        EvidenceClass.E2_PUBLICATION_SUPPLEMENT,
    }:
        if trust.sample_identity != "exact":
            blockers.append("sample_identity_not_exact")
        if trust.acquisition_identity not in {"exact", "not_applicable"}:
            blockers.append("acquisition_identity_not_exact")
    external_validation_eligible = (
        not blockers
        and trust.independence == "independent"
        and trust.comparability == "exact"
        and candidate.evidence_class
        in {
            EvidenceClass.E0_RAW_EXPERIMENTAL,
            EvidenceClass.E1_PROCESSED_EXPERIMENTAL,
            EvidenceClass.E2_PUBLICATION_SUPPLEMENT,
        }
    )
    return {
        "candidate_id": candidate.candidate_id,
        "maximum_use": base,
        "blocker_codes": blockers,
        "external_validation_eligible_before_scientific_intake": False,
        "could_become_external_validation_eligible_after_intake": external_validation_eligible,
        "scientific_status_changed": False,
    }


__all__ = [
    "EVIDENCE_FEDERATION_SCHEMA_VERSION",
    "EvidenceClass",
    "EvidenceFederationError",
    "EvidenceTrustVector",
    "FederatedEvidenceCandidate",
    "canonical_sha256",
    "maximum_evidence_use",
]
