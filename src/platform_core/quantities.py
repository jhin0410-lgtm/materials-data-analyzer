"""Structured scientific quantities with unit and uncertainty metadata."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from .unit_backend import BuiltinUnitBackend, UnitBackend
from .uncertainty import UncertaintySpec, uncertainty_from_payload


QUANTITY_SCHEMA_VERSION = "2.2.2"


@dataclass(frozen=True)
class QuantityProvenance:
    source: str
    method: str = "declared"
    provenance_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "method": self.method,
            "provenance_refs": list(self.provenance_refs),
        }


@dataclass(frozen=True)
class QuantityArrayMetadata:
    artifact_ref: str
    shape: tuple[int, ...]
    dtype: str
    unit: str
    checksum_sha256: str
    axis_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.artifact_ref.startswith("/") or ":/" in self.artifact_ref or ":\\" in self.artifact_ref:
            raise ValueError("array artifact_ref must be relative")
        if not self.shape or any(int(dim) <= 0 for dim in self.shape):
            raise ValueError("array shape must contain positive dimensions")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_ref": self.artifact_ref,
            "shape": list(self.shape),
            "dtype": self.dtype,
            "unit": self.unit,
            "checksum_sha256": self.checksum_sha256,
            "axis_metadata": dict(self.axis_metadata),
        }


@dataclass(frozen=True)
class QuantityValue:
    value: float
    original_unit: str
    canonical_value: float
    canonical_unit: str
    dimension: str
    uncertainty: UncertaintySpec = field(default_factory=UncertaintySpec.unavailable)
    provenance_refs: tuple[str, ...] = ()
    validity_status: str = "valid"
    conversion_history: tuple[Mapping[str, Any], ...] = ()
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.value)):
            raise ValueError("quantity value must be finite")
        if not math.isfinite(float(self.canonical_value)):
            raise ValueError("canonical quantity value must be finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": QUANTITY_SCHEMA_VERSION,
            "value": self.value,
            "original_unit": self.original_unit,
            "canonical_value": self.canonical_value,
            "canonical_unit": self.canonical_unit,
            "dimension": self.dimension,
            "uncertainty": self.uncertainty.to_dict(),
            "provenance_refs": list(self.provenance_refs),
            "validity_status": self.validity_status,
            "conversion_history": [dict(item) for item in self.conversion_history],
            "missing_reason": self.missing_reason,
        }


@dataclass(frozen=True)
class ScientificQuantity:
    quantity_id: str
    value: QuantityValue | None = None
    array_metadata: QuantityArrayMetadata | None = None
    provenance: QuantityProvenance = field(default_factory=lambda: QuantityProvenance(source="metadata"))

    def __post_init__(self) -> None:
        if not self.quantity_id:
            raise ValueError("quantity_id is required")
        if (self.value is None) == (self.array_metadata is None):
            raise ValueError("exactly one of value or array_metadata must be provided")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": QUANTITY_SCHEMA_VERSION,
            "quantity_id": self.quantity_id,
            "value": self.value.to_dict() if self.value else None,
            "array_metadata": self.array_metadata.to_dict() if self.array_metadata else None,
            "provenance": self.provenance.to_dict(),
        }


def build_quantity_value(
    *,
    value: float,
    unit: str,
    uncertainty: Mapping[str, Any] | UncertaintySpec | None = None,
    backend: UnitBackend | None = None,
    provenance_refs: tuple[str, ...] = (),
) -> QuantityValue:
    backend = backend or BuiltinUnitBackend()
    canonical_value, canonical_unit = backend.normalize(float(value), unit)
    parsed = backend.parse_unit(unit)
    if isinstance(uncertainty, UncertaintySpec):
        uncertainty_spec = uncertainty
    else:
        uncertainty_spec = uncertainty_from_payload(uncertainty)
    conversion = {
        "backend": parsed.backend,
        "backend_version": parsed.backend_version,
        "from_unit": unit,
        "to_unit": canonical_unit,
    }
    return QuantityValue(
        value=float(value),
        original_unit=unit,
        canonical_value=canonical_value,
        canonical_unit=canonical_unit,
        dimension=parsed.dimension,
        uncertainty=uncertainty_spec,
        provenance_refs=provenance_refs,
        conversion_history=(conversion,),
    )


def validate_quantity_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if payload.get("schema_version") not in {QUANTITY_SCHEMA_VERSION, "2"}:
        errors.append("unsupported_schema_version")
    if not payload.get("quantity_id"):
        errors.append("missing:quantity_id")
    value = payload.get("value")
    array_metadata = payload.get("array_metadata")
    if (value is None) == (array_metadata is None):
        errors.append("exactly_one_value_or_array_metadata_required")
    if isinstance(value, Mapping):
        for key in ("original_unit", "canonical_unit", "dimension", "canonical_value"):
            if key not in value:
                errors.append(f"missing:value.{key}")
    if isinstance(array_metadata, Mapping):
        if str(array_metadata.get("artifact_ref", "")).startswith("/") or ":/" in str(array_metadata.get("artifact_ref", "")):
            errors.append("absolute_array_artifact_ref")
        if "shape" not in array_metadata:
            errors.append("missing:array_metadata.shape")
    return {"valid": not errors, "errors": errors}


def quantity_from_payload(payload: Mapping[str, Any], *, backend: UnitBackend | None = None) -> ScientificQuantity:
    validation = validate_quantity_payload(payload)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))
    value_payload = payload.get("value")
    if isinstance(value_payload, Mapping):
        quantity_value = build_quantity_value(
            value=float(value_payload["value"]),
            unit=str(value_payload["original_unit"]),
            uncertainty=value_payload.get("uncertainty"),
            backend=backend,
            provenance_refs=tuple(str(item) for item in value_payload.get("provenance_refs", ())),
        )
        return ScientificQuantity(str(payload["quantity_id"]), value=quantity_value)
    array_payload = payload["array_metadata"]
    if not isinstance(array_payload, Mapping):
        raise ValueError("validated array_metadata must be a mapping")
    array_metadata = QuantityArrayMetadata(
        artifact_ref=str(array_payload["artifact_ref"]),
        shape=tuple(int(item) for item in array_payload["shape"]),
        dtype=str(array_payload["dtype"]),
        unit=str(array_payload["unit"]),
        checksum_sha256=str(array_payload["checksum_sha256"]),
        axis_metadata=array_payload.get("axis_metadata", {}),
    )
    return ScientificQuantity(str(payload["quantity_id"]), array_metadata=array_metadata)
