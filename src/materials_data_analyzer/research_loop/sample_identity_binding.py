"""Provenance-bearing physical sample identity and characterization normalization."""
from __future__ import annotations

from dataclasses import dataclass

from materials_data_analyzer.characterization_use_contract import (
    CharacterizationUseEligibility,
)

from .kernel import ResearchLoopError
from .scientific_evidence_normalization import (
    MaterialDescriptor,
    NormalizedMeasurement,
    ProvenanceLocator,
)

SCHEMA_VERSION = "1.1"
_RELATIONSHIPS = {"specimen", "aliquot", "field_of_view"}
_MODALITIES = {
    "xrd",
    "sem",
    "tem",
    "raman",
    "eds",
    "saed",
    "optical_microscopy",
    "optical_microscopy_metrology",
}


class SampleIdentityBindingError(ResearchLoopError):
    """Raised when multimodal measurements cannot be bound to one physical sample."""


@dataclass(frozen=True)
class SampleBinding:
    parent_sample_id: str
    child_sample_id: str
    relationship: str
    provenance: ProvenanceLocator

    def __post_init__(self) -> None:
        if not self.parent_sample_id.strip() or not self.child_sample_id.strip():
            raise SampleIdentityBindingError("sample ids must be non-empty")
        if self.parent_sample_id == self.child_sample_id:
            raise SampleIdentityBindingError("sample binding cannot self-reference")
        relationship = self.relationship.strip().lower()
        if relationship not in _RELATIONSHIPS:
            raise SampleIdentityBindingError(
                "unsupported sample binding relationship"
            )
        object.__setattr__(self, "relationship", relationship)


class SampleIdentityRegistry:
    def __init__(self) -> None:
        self._by_child: dict[str, SampleBinding] = {}

    def bind(self, binding: SampleBinding) -> None:
        existing = self._by_child.get(binding.child_sample_id)
        if existing is not None and existing != binding:
            raise SampleIdentityBindingError(
                "child sample has ambiguous physical parentage"
            )
        current = binding.parent_sample_id
        seen = {binding.child_sample_id}
        while current in self._by_child:
            if current in seen:
                raise SampleIdentityBindingError("sample identity cycle detected")
            seen.add(current)
            current = self._by_child[current].parent_sample_id
        if current == binding.child_sample_id:
            raise SampleIdentityBindingError("sample identity cycle detected")
        self._by_child[binding.child_sample_id] = binding

    def canonical_sample_id(self, sample_id: str) -> str:
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise SampleIdentityBindingError("sample_id must be non-empty")
        current = sample_id.strip()
        seen: set[str] = set()
        while current in self._by_child:
            if current in seen:
                raise SampleIdentityBindingError("sample identity cycle detected")
            seen.add(current)
            current = self._by_child[current].parent_sample_id
        return current

    @property
    def bindings(self) -> tuple[SampleBinding, ...]:
        return tuple(self._by_child[key] for key in sorted(self._by_child))


def normalize_characterization_measurement(
    *,
    modality: str,
    sample_id: str,
    property_name: str,
    value: float,
    unit: str,
    material: MaterialDescriptor,
    instrument_model: str,
    calibration_id: str | None,
    process_signature: str | None,
    standard_uncertainty: float | None,
    provenance: ProvenanceLocator,
    eligibility: CharacterizationUseEligibility,
    identity_registry: SampleIdentityRegistry | None = None,
) -> NormalizedMeasurement:
    """Normalize characterization only after the existing producer policy allows use."""
    modality = modality.strip().lower()
    if modality not in _MODALITIES:
        raise SampleIdentityBindingError(
            "unsupported characterization modality"
        )
    if not eligibility.allowed:
        raise SampleIdentityBindingError(
            "characterization downstream-use policy blocks this evidence"
        )
    if eligibility.review_status != "reviewed":
        raise SampleIdentityBindingError(
            "characterization evidence requires reviewed status"
        )
    if eligibility.evidence_level not in {"Supported", "Diagnostic"}:
        raise SampleIdentityBindingError(
            "characterization evidence level is not usable for normalization"
        )
    canonical_sample = (
        identity_registry.canonical_sample_id(sample_id)
        if identity_registry is not None
        else sample_id
    )
    return NormalizedMeasurement(
        material=material,
        sample_id=canonical_sample,
        property_name=property_name,
        value=value,
        unit=unit,
        method=modality,
        instrument_model=instrument_model,
        calibration_id=calibration_id,
        process_signature=process_signature,
        standard_uncertainty=standard_uncertainty,
        provenance=provenance,
    )


__all__ = [
    "SCHEMA_VERSION",
    "SampleBinding",
    "SampleIdentityBindingError",
    "SampleIdentityRegistry",
    "normalize_characterization_measurement",
]
