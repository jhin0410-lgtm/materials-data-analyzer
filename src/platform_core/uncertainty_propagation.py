"""Bounded uncertainty propagation pilots for registered scientific operators."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .quantities import QuantityValue, build_quantity_value
from .uncertainty import (
    UncertaintyBudgetItem,
    UncertaintyPropagationResult,
    UncertaintySpec,
    first_order_independent,
    uncertainty_from_payload,
)
from .unit_backend import BuiltinUnitBackend, UnitBackend


def _quantity(payload: Mapping[str, Any], *, backend: UnitBackend) -> QuantityValue:
    return build_quantity_value(
        value=float(payload["value"]),
        unit=str(payload["unit"]),
        uncertainty=payload.get("uncertainty"),
        backend=backend,
        provenance_refs=tuple(str(item) for item in payload.get("provenance_refs", ())),
    )


def _absolute_sigma(quantity: QuantityValue, *, output_unit: str, backend: UnitBackend) -> float | None:
    uncertainty = quantity.uncertainty
    if uncertainty.kind == "absolute" and uncertainty.value is not None:
        source_unit = uncertainty.unit or quantity.original_unit
        return abs(backend.convert(float(uncertainty.value), source_unit, output_unit))
    if uncertainty.kind in {"standard_uncertainty", "standard_deviation"} and uncertainty.value is not None:
        source_unit = uncertainty.unit or quantity.original_unit
        return abs(backend.convert(float(uncertainty.value), source_unit, output_unit))
    return None


def propagate_bragg_uncertainty(config: Mapping[str, Any], *, backend: UnitBackend | None = None) -> dict[str, Any]:
    """Propagate d-spacing uncertainty for d = n*lambda/(2*sin(two_theta/2))."""

    backend = backend or BuiltinUnitBackend()
    wavelength = _quantity(config["wavelength"], backend=backend)
    two_theta = _quantity(config["two_theta"], backend=backend)
    order = int(config.get("diffraction_order", 1))
    output_unit = str(config.get("output_unit", wavelength.original_unit))
    warnings: list[str] = []
    if order <= 0:
        return _unavailable("bragg_uncertainty", "invalid_diffraction_order", warnings=("diffraction_order_must_be_positive",))
    wavelength_out = backend.convert(wavelength.value, wavelength.original_unit, output_unit)
    two_theta_rad = backend.convert(two_theta.value, two_theta.original_unit, "rad")
    theta = two_theta_rad / 2.0
    if theta <= 0 or theta >= math.pi / 2 or abs(math.sin(theta)) < 1e-12:
        return _unavailable("bragg_uncertainty", "invalid_or_singular_angle", warnings=("two_theta_outside_supported_domain",))
    d_spacing = order * wavelength_out / (2.0 * math.sin(theta))
    sigma_lambda = _absolute_sigma(wavelength, output_unit=output_unit, backend=backend)
    sigma_two_theta = _absolute_sigma(two_theta, output_unit="rad", backend=backend)
    if sigma_lambda is None or sigma_two_theta is None:
        missing = []
        if sigma_lambda is None:
            missing.append("wavelength_uncertainty")
        if sigma_two_theta is None:
            missing.append("two_theta_uncertainty")
        return UncertaintyPropagationResult(
            status="unavailable",
            method="first_order_independent",
            output_uncertainty=UncertaintySpec.unavailable(method="missing_input_uncertainty"),
            budget=(),
            assumptions=("Bragg scalar geometry only",),
            warnings=tuple(missing),
            value=d_spacing,
            unit=output_unit,
        ).to_dict()
    sensitivity_lambda = order / (2.0 * math.sin(theta))
    sensitivity_two_theta = -order * wavelength_out * math.cos(theta) / (4.0 * math.sin(theta) ** 2)
    budget = (
        UncertaintyBudgetItem(
            input_id="wavelength",
            sensitivity=sensitivity_lambda,
            standard_uncertainty=sigma_lambda,
            unit=output_unit,
            contribution=(sensitivity_lambda * sigma_lambda) ** 2,
        ),
        UncertaintyBudgetItem(
            input_id="two_theta",
            sensitivity=sensitivity_two_theta,
            standard_uncertainty=sigma_two_theta,
            unit="rad",
            contribution=(sensitivity_two_theta * sigma_two_theta) ** 2,
        ),
    )
    result = first_order_independent(
        value=d_spacing,
        unit=output_unit,
        budget=budget,
        assumptions=("input uncertainties are independent", "theta is one half of two_theta", "small-uncertainty first-order approximation"),
        provenance_refs=("relation:xrd.bragg.d_spacing",),
    )
    if result.warnings:
        warnings.extend(result.warnings)
    payload = result.to_dict()
    payload["operator_id"] = "xrd_bragg_uncertainty_v2_2"
    payload["warnings"] = sorted(set(payload["warnings"] + warnings))
    return payload


def scherrer_uncertainty_eligibility(config: Mapping[str, Any], *, backend: UnitBackend | None = None) -> dict[str, Any]:
    """Return structured eligibility for Scherrer uncertainty without overclaiming."""

    backend = backend or BuiltinUnitBackend()
    required = ("wavelength", "fwhm", "two_theta", "shape_factor")
    missing = [name for name in required if name not in config]
    warnings: list[str] = []
    if missing:
        return {
            "operator_id": "xrd_scherrer_uncertainty_v2_2",
            "status": "unavailable",
            "uncertainty_status": "missing_budget",
            "missing_inputs": missing,
            "warnings": ["Scherrer numeric propagation not attempted without complete budget"],
            "prohibited_claims": ["particle_size", "grain_size", "model_form_certainty"],
        }
    wavelength = _quantity(config["wavelength"], backend=backend)
    fwhm = _quantity(config["fwhm"], backend=backend)
    two_theta = _quantity(config["two_theta"], backend=backend)
    shape_factor = _quantity(config["shape_factor"], backend=backend)
    instrumental = config.get("instrumental_broadening")
    if instrumental is None:
        warnings.append("instrumental_broadening_uncertainty_missing")
    values = {
        "wavelength": wavelength,
        "fwhm": fwhm,
        "two_theta": two_theta,
        "shape_factor": shape_factor,
    }
    missing_uncertainty = [name for name, value in values.items() if uncertainty_from_payload(value.uncertainty.to_dict()).kind == "unavailable"]
    beta = backend.convert(fwhm.value, fwhm.original_unit, "rad")
    if beta <= 0:
        return {
            "operator_id": "xrd_scherrer_uncertainty_v2_2",
            "status": "invalid_input",
            "uncertainty_status": "unavailable",
            "warnings": ["fwhm_must_be_positive"],
            "prohibited_claims": ["particle_size", "grain_size"],
        }
    if instrumental is not None:
        inst_q = _quantity(instrumental, backend=backend)
        inst = backend.convert(inst_q.value, inst_q.original_unit, "rad")
        if beta <= inst:
            return {
                "operator_id": "xrd_scherrer_uncertainty_v2_2",
                "status": "invalid_input",
                "uncertainty_status": "unavailable",
                "warnings": ["instrumental_broadening_exceeds_observed_fwhm"],
                "prohibited_claims": ["particle_size", "grain_size"],
            }
    status = "partial" if missing_uncertainty or warnings else "eligible"
    return {
        "operator_id": "xrd_scherrer_uncertainty_v2_2",
        "status": status,
        "uncertainty_status": "partial" if status == "partial" else "eligible_for_first_order_estimate",
        "missing_uncertainty": missing_uncertainty,
        "warnings": warnings + ["model_form_uncertainty_not_resolved", "strain_broadening_not_resolved"],
        "assumptions": ["small-angle uncertainty", "independent inputs if propagation is later enabled"],
        "prohibited_claims": ["particle_size", "grain_size", "root_cause", "model_form_certainty"],
    }


def _unavailable(operator_id: str, method: str, *, warnings: tuple[str, ...]) -> dict[str, Any]:
    return UncertaintyPropagationResult(
        status="unavailable",
        method=method,
        output_uncertainty=UncertaintySpec.unavailable(method=method),
        warnings=warnings,
    ).to_dict() | {"operator_id": operator_id}
