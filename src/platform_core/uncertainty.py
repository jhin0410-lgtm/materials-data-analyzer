"""Structured uncertainty metadata and bounded propagation helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping


UNCERTAINTY_KINDS = (
    "none",
    "absolute",
    "relative",
    "standard_uncertainty",
    "standard_deviation",
    "confidence_interval",
    "prediction_interval",
    "quantile_interval",
    "distribution_reference",
    "epistemic",
    "aleatoric",
    "unavailable",
)


@dataclass(frozen=True)
class UncertaintyInterval:
    lower: float
    upper: float
    unit: str | None = None
    confidence_level: float | None = None

    def __post_init__(self) -> None:
        if self.lower > self.upper:
            raise ValueError("uncertainty interval lower must be <= upper")
        if self.confidence_level is not None and not (0 < self.confidence_level < 1):
            raise ValueError("confidence_level must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "unit": self.unit,
            "confidence_level": self.confidence_level,
        }


@dataclass(frozen=True)
class UncertaintySpec:
    kind: str
    value: float | None = None
    unit: str | None = None
    interval: UncertaintyInterval | None = None
    confidence_level: float | None = None
    coverage_factor: float | None = None
    distribution: str | None = None
    method: str = "declared"
    source: str = "metadata"
    assumptions: tuple[str, ...] = ()
    correlation_status: str = "unspecified"
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in UNCERTAINTY_KINDS:
            raise ValueError(f"unsupported uncertainty kind: {self.kind}")
        if self.value is not None and (not math.isfinite(float(self.value)) or float(self.value) < 0):
            raise ValueError("uncertainty value must be finite and non-negative")
        if self.confidence_level is not None and not (0 < self.confidence_level < 1):
            raise ValueError("confidence_level must be between 0 and 1")
        if self.kind in {"confidence_interval", "prediction_interval", "quantile_interval"} and self.interval is None:
            raise ValueError(f"{self.kind} requires an interval")
        if self.kind not in {"confidence_interval", "prediction_interval", "quantile_interval"} and self.confidence_level is not None:
            raise ValueError("confidence_level is only valid for interval uncertainty kinds")

    @classmethod
    def unavailable(cls, *, method: str = "unavailable", source: str = "metadata") -> "UncertaintySpec":
        return cls(kind="unavailable", method=method, source=source)

    @classmethod
    def absolute(cls, value: float, unit: str | None = None, *, method: str = "declared") -> "UncertaintySpec":
        return cls(kind="absolute", value=float(value), unit=unit, method=method)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "unit": self.unit,
            "interval": self.interval.to_dict() if self.interval else None,
            "confidence_level": self.confidence_level,
            "coverage_factor": self.coverage_factor,
            "distribution": self.distribution,
            "method": self.method,
            "source": self.source,
            "assumptions": list(self.assumptions),
            "correlation_status": self.correlation_status,
            "provenance_refs": list(self.provenance_refs),
        }


@dataclass(frozen=True)
class UncertaintyBudgetItem:
    input_id: str
    sensitivity: float | None
    standard_uncertainty: float | None
    unit: str | None
    contribution: float | None
    status: str = "used"

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "sensitivity": self.sensitivity,
            "standard_uncertainty": self.standard_uncertainty,
            "unit": self.unit,
            "contribution": self.contribution,
            "status": self.status,
        }


@dataclass(frozen=True)
class UncertaintyPropagationResult:
    status: str
    method: str
    output_uncertainty: UncertaintySpec
    budget: tuple[UncertaintyBudgetItem, ...] = ()
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    value: float | None = None
    unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "method": self.method,
            "value": self.value,
            "unit": self.unit,
            "output_uncertainty": self.output_uncertainty.to_dict(),
            "budget": [item.to_dict() for item in self.budget],
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "provenance_refs": list(self.provenance_refs),
        }


def uncertainty_from_payload(payload: Mapping[str, Any] | None) -> UncertaintySpec:
    if not payload:
        return UncertaintySpec.unavailable(method="missing_uncertainty")
    kind = str(payload.get("kind", "unavailable"))
    interval_payload = payload.get("interval")
    interval = None
    if isinstance(interval_payload, Mapping):
        interval = UncertaintyInterval(
            lower=float(interval_payload["lower"]),
            upper=float(interval_payload["upper"]),
            unit=interval_payload.get("unit"),
            confidence_level=interval_payload.get("confidence_level"),
        )
    return UncertaintySpec(
        kind=kind,
        value=None if payload.get("value") is None else float(payload["value"]),
        unit=payload.get("unit"),
        interval=interval,
        confidence_level=payload.get("confidence_level"),
        coverage_factor=payload.get("coverage_factor"),
        distribution=payload.get("distribution"),
        method=str(payload.get("method", "declared")),
        source=str(payload.get("source", "metadata")),
        assumptions=tuple(str(item) for item in payload.get("assumptions", ())),
        correlation_status=str(payload.get("correlation_status", "unspecified")),
        provenance_refs=tuple(str(item) for item in payload.get("provenance_refs", ())),
    )


def first_order_independent(
    *,
    value: float,
    unit: str,
    budget: tuple[UncertaintyBudgetItem, ...],
    assumptions: tuple[str, ...],
    provenance_refs: tuple[str, ...] = (),
) -> UncertaintyPropagationResult:
    if any(item.contribution is None for item in budget):
        return UncertaintyPropagationResult(
            status="unavailable",
            method="first_order_independent",
            output_uncertainty=UncertaintySpec.unavailable(method="missing_budget_item"),
            budget=budget,
            assumptions=assumptions,
            provenance_refs=provenance_refs,
            value=value,
            unit=unit,
        )
    variance = sum(float(item.contribution) for item in budget)
    sigma = math.sqrt(max(variance, 0.0))
    warnings: list[str] = []
    if abs(value) > 0 and sigma / abs(value) > 0.5:
        warnings.append("relative_uncertainty_exceeds_50_percent")
    return UncertaintyPropagationResult(
        status="propagated",
        method="first_order_independent",
        output_uncertainty=UncertaintySpec(
            kind="standard_uncertainty",
            value=sigma,
            unit=unit,
            method="first_order_independent",
            assumptions=assumptions,
            correlation_status="assumed_independent",
            provenance_refs=provenance_refs,
        ),
        budget=budget,
        assumptions=assumptions,
        warnings=tuple(warnings),
        provenance_refs=provenance_refs,
        value=value,
        unit=unit,
    )
