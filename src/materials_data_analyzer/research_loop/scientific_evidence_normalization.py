"""Canonical, provenance-bearing scientific evidence normalization.

This module does not replace :mod:`epistemic_graph`. It provides a strict row-level
normalization layer that emits evidence nodes compatible with that existing graph.
No unit, composition basis, sample identity, or measurement semantics are inferred.
A source-declared material identity can be represented without fabricating an elemental
composition when the source does not provide one.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, TypeAlias

from .kernel import ResearchLoopError

SCHEMA_VERSION = "1.1"
_COMPOSITION_BASES = {
    "mass_fraction",
    "atomic_fraction",
    "mass_percent",
    "atomic_percent",
}
_IDENTITY_BASES = {
    "source_declared_label",
    "catalog_identifier",
    "standard_designation",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ScientificEvidenceNormalizationError(ResearchLoopError):
    """Raised when a row cannot be normalized without scientific inference."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScientificEvidenceNormalizationError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScientificEvidenceNormalizationError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ScientificEvidenceNormalizationError(f"{field} must be finite")
    return result


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProvenanceLocator:
    source_id: str
    artifact_sha256: str
    record_locator: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text(self.source_id, "source_id"))
        digest = self.artifact_sha256.strip().lower()
        if not _SHA256_RE.fullmatch(digest):
            raise ScientificEvidenceNormalizationError(
                "artifact_sha256 must be lowercase SHA-256"
            )
        object.__setattr__(self, "artifact_sha256", digest)
        object.__setattr__(
            self,
            "record_locator",
            _text(self.record_locator, "record_locator"),
        )


@dataclass(frozen=True)
class MaterialIdentity:
    """A source-declared material identity with no inferred composition."""

    material_name: str
    declared_identifier: str
    identity_basis: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "material_name",
            _text(self.material_name, "material_name"),
        )
        object.__setattr__(
            self,
            "declared_identifier",
            _text(self.declared_identifier, "declared_identifier"),
        )
        basis = _text(self.identity_basis, "identity_basis")
        if basis not in _IDENTITY_BASES:
            raise ScientificEvidenceNormalizationError(
                f"identity_basis must be one of {sorted(_IDENTITY_BASES)}"
            )
        object.__setattr__(self, "identity_basis", basis)

    @property
    def material_id(self) -> str:
        return "material:" + canonical_sha256(asdict(self))[:24]


@dataclass(frozen=True)
class MaterialComposition:
    material_name: str
    basis: str
    components: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "material_name",
            _text(self.material_name, "material_name"),
        )
        basis = self.basis.strip()
        if basis not in _COMPOSITION_BASES:
            raise ScientificEvidenceNormalizationError(
                f"composition basis must be one of {sorted(_COMPOSITION_BASES)}"
            )
        object.__setattr__(self, "basis", basis)
        if not self.components:
            raise ScientificEvidenceNormalizationError(
                "composition components must not be empty"
            )
        normalized: dict[str, float] = {}
        for raw_name, raw_value in self.components.items():
            name = _text(raw_name, "composition component")
            value = _finite(raw_value, f"composition[{name}]")
            if value < 0:
                raise ScientificEvidenceNormalizationError(
                    "composition values must be non-negative"
                )
            normalized[name] = value
        upper = 100.0 if basis.endswith("percent") else 1.0
        total = sum(normalized.values())
        if total > upper + max(1e-9, upper * 1e-6):
            raise ScientificEvidenceNormalizationError(
                "declared composition exceeds its explicit basis total"
            )
        object.__setattr__(self, "components", normalized)

    @property
    def material_id(self) -> str:
        return "material:" + canonical_sha256(asdict(self))[:24]


MaterialDescriptor: TypeAlias = MaterialIdentity | MaterialComposition


@dataclass(frozen=True)
class NormalizedMeasurement:
    material: MaterialDescriptor
    sample_id: str
    property_name: str
    value: float
    unit: str
    method: str
    instrument_model: str
    calibration_id: str | None
    process_signature: str | None
    standard_uncertainty: float | None
    provenance: ProvenanceLocator

    def __post_init__(self) -> None:
        if not isinstance(self.material, (MaterialIdentity, MaterialComposition)):
            raise ScientificEvidenceNormalizationError(
                "material must be a MaterialIdentity or MaterialComposition"
            )
        for field in (
            "sample_id",
            "property_name",
            "unit",
            "method",
            "instrument_model",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(self, "value", _finite(self.value, "value"))
        if self.standard_uncertainty is not None:
            uncertainty = _finite(
                self.standard_uncertainty,
                "standard_uncertainty",
            )
            if uncertainty < 0:
                raise ScientificEvidenceNormalizationError(
                    "standard_uncertainty must be non-negative"
                )
            object.__setattr__(self, "standard_uncertainty", uncertainty)
        for field in ("calibration_id", "process_signature"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _text(value, field))

    @property
    def measurement_id(self) -> str:
        return "measurement:" + canonical_sha256(asdict(self))[:24]

    def metadata(self) -> dict[str, Any]:
        composition_known = isinstance(self.material, MaterialComposition)
        return {
            "scientific_evidence_schema_version": SCHEMA_VERSION,
            "measurement_id": self.measurement_id,
            "material_id": self.material.material_id,
            "material": asdict(self.material),
            "material_identity_kind": (
                "explicit_composition" if composition_known else "source_declared_identity"
            ),
            "material_composition_known": composition_known,
            "composition_inferred": False,
            "sample_id": self.sample_id,
            "property_name": self.property_name,
            "value": self.value,
            "unit": self.unit,
            "method": self.method,
            "instrument_model": self.instrument_model,
            "calibration_id": self.calibration_id,
            "process_signature": self.process_signature,
            "standard_uncertainty": self.standard_uncertainty,
            "record_locator": self.provenance.record_locator,
            "source_id": self.provenance.source_id,
            "source_artifact_sha256": self.provenance.artifact_sha256,
            "semantic_inference_performed": False,
        }


def build_epistemic_evidence_node(
    measurement: NormalizedMeasurement,
    *,
    workstream_id: str,
    evidence_role: str,
    evidence_quality: str,
) -> dict[str, Any]:
    """Emit an evidence node for the existing epistemic graph.

    The evidence binding is pinned to the same artifact SHA as the row provenance; the
    graph validator remains responsible for checking that binding against program state.
    """
    if evidence_quality not in {
        "supported",
        "diagnostic",
        "inconclusive",
        "unsupported",
    }:
        raise ScientificEvidenceNormalizationError("unsupported evidence_quality")
    workstream_id = _text(workstream_id, "workstream_id")
    evidence_role = _text(evidence_role, "evidence_role")
    return {
        "node_id": "evidence:"
        + measurement.measurement_id.removeprefix("measurement:"),
        "node_type": "evidence",
        "statement": (
            f"Observed {measurement.property_name} for explicitly identified sample "
            f"{measurement.sample_id}; value and unit are source-declared."
        ),
        "evidence_binding": {
            "workstream_id": workstream_id,
            "role": evidence_role,
            "sha256": measurement.provenance.artifact_sha256,
        },
        "evidence_quality": evidence_quality,
        "metadata": measurement.metadata(),
    }


__all__ = [
    "MaterialComposition",
    "MaterialDescriptor",
    "MaterialIdentity",
    "NormalizedMeasurement",
    "ProvenanceLocator",
    "SCHEMA_VERSION",
    "ScientificEvidenceNormalizationError",
    "build_epistemic_evidence_node",
    "canonical_sha256",
]
