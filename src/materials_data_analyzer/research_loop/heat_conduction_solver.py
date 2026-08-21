"""Audited reference solver for one-dimensional transient heat conduction.

This module implements a deliberately bounded continuum-physics reference problem:
constant-property one-dimensional diffusion with fixed-temperature boundaries, solved
with the explicit FTCS finite-difference scheme.  It is not an LPBF, melt-pool, phase-
change, convection, radiation, or material-calibration model.

Malformed scientific inputs fail closed.  A well-formed request that violates the FTCS
stability criterion is retained as a checksum-bound rejected numerical run so negative
solver evidence is not silently discarded.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from .kernel import ResearchLoopError

HEAT_SOLVER_SCHEMA_VERSION = "1.0"
HEAT_SOLVER_ID = "heat_conduction_1d_explicit_ftcs"
HEAT_SOLVER_VERSION = "1.0"
HEAT_SOLVER_ACTION_TYPE = "reference_heat_conduction_simulation"
HEAT_SOLVER_ACTION_VERSION = "1.0"
FTCS_STABILITY_LIMIT = 0.5

_REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "solver_id",
    "solver_version",
    "units",
    "domain",
    "time",
    "material",
    "initial_condition",
    "boundary_conditions",
    "validation",
}


class HeatConductionSolverError(ResearchLoopError):
    """Raised when a heat-solver request is malformed or scientifically ambiguous."""


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HeatConductionSolverError(
            "heat-solver request/result must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise HeatConductionSolverError(f"{field} must be an object")
    return dict(value)


def _exact_keys(value: Mapping[str, Any], *, field: str, keys: set[str]) -> None:
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing:
        raise HeatConductionSolverError(
            f"{field} is missing required keys: {', '.join(missing)}"
        )
    if unknown:
        raise HeatConductionSolverError(
            f"{field} has unknown keys: {', '.join(unknown)}"
        )


def _finite(value: object, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HeatConductionSolverError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise HeatConductionSolverError(f"{field} must be finite")
    if positive and result <= 0.0:
        raise HeatConductionSolverError(f"{field} must be positive")
    return result


def _kelvin(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0.0:
        raise HeatConductionSolverError(f"{field} cannot be below absolute zero")
    return result


def _positive_integer(value: object, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HeatConductionSolverError(f"{field} must be an integer >= {minimum}")
    return value


def _resolve_material(
    material: Mapping[str, Any],
    units: Mapping[str, Any],
) -> tuple[float, dict[str, Any]]:
    direct_keys = {"thermal_diffusivity_m2_s"}
    derived_keys = {
        "thermal_conductivity_W_mK",
        "density_kg_m3",
        "specific_heat_J_kgK",
    }
    keys = set(material)
    if keys == direct_keys:
        expected_units = {
            "length": "m",
            "time": "s",
            "temperature": "K",
            "thermal_diffusivity": "m^2/s",
        }
        if dict(units) != expected_units:
            raise HeatConductionSolverError(
                "units must exactly match the direct-diffusivity SI contract"
            )
        alpha = _finite(
            material["thermal_diffusivity_m2_s"],
            "material.thermal_diffusivity_m2_s",
            positive=True,
        )
        return alpha, {
            "mode": "explicit_thermal_diffusivity",
            "thermal_diffusivity_m2_s": alpha,
            "derivation": None,
        }
    if keys == derived_keys:
        expected_units = {
            "length": "m",
            "time": "s",
            "temperature": "K",
            "thermal_conductivity": "W/(m*K)",
            "density": "kg/m^3",
            "specific_heat": "J/(kg*K)",
        }
        if dict(units) != expected_units:
            raise HeatConductionSolverError(
                "units must exactly match the k/rho/cp SI contract"
            )
        conductivity = _finite(
            material["thermal_conductivity_W_mK"],
            "material.thermal_conductivity_W_mK",
            positive=True,
        )
        density = _finite(
            material["density_kg_m3"],
            "material.density_kg_m3",
            positive=True,
        )
        heat_capacity = _finite(
            material["specific_heat_J_kgK"],
            "material.specific_heat_J_kgK",
            positive=True,
        )
        alpha = conductivity / (density * heat_capacity)
        if not math.isfinite(alpha) or alpha <= 0.0:
            raise HeatConductionSolverError(
                "derived thermal diffusivity is not finite and positive"
            )
        return alpha, {
            "mode": "derived_from_k_rho_cp",
            "thermal_diffusivity_m2_s": alpha,
            "thermal_conductivity_W_mK": conductivity,
            "density_kg_m3": density,
            "specific_heat_J_kgK": heat_capacity,
            "derivation": "alpha = k / (rho * cp)",
        }
    raise HeatConductionSolverError(
        "material must declare exactly thermal_diffusivity_m2_s or exactly k/rho/cp"
    )


def _parse_boundaries(value: object) -> tuple[float, float, dict[str, Any]]:
    boundaries = _mapping(value, "boundary_conditions")
    _exact_keys(boundaries, field="boundary_conditions", keys={"left", "right"})
    normalized: dict[str, Any] = {}
    temperatures: list[float] = []
    for side in ("left", "right"):
        record = _mapping(boundaries[side], f"boundary_conditions.{side}")
        _exact_keys(
            record,
            field=f"boundary_conditions.{side}",
            keys={"kind", "temperature_K"},
        )
        if record["kind"] != "fixed_temperature":
            raise HeatConductionSolverError(
                "v1 supports fixed_temperature Dirichlet boundaries only"
            )
        temperature = _kelvin(
            record["temperature_K"],
            f"boundary_conditions.{side}.temperature_K",
        )
        temperatures.append(temperature)
        normalized[side] = {
            "kind": "fixed_temperature",
            "temperature_K": temperature,
        }
    return temperatures[0], temperatures[1], normalized


def _initial_field(
    initial: Mapping[str, Any],
    *,
    grid: list[float],
    length_m: float,
    left_K: float,
    right_K: float,
) -> tuple[list[float], dict[str, Any]]:
    kind = initial.get("kind")
    if kind == "uniform":
        _exact_keys(
            initial,
            field="initial_condition",
            keys={"kind", "temperature_K"},
        )
        temperature = _kelvin(initial["temperature_K"], "initial_condition.temperature_K")
        field = [temperature for _ in grid]
        normalized = {"kind": "uniform", "temperature_K": temperature}
    elif kind == "sine_mode":
        _exact_keys(
            initial,
            field="initial_condition",
            keys={"kind", "baseline_temperature_K", "amplitude_K"},
        )
        baseline = _kelvin(
            initial["baseline_temperature_K"],
            "initial_condition.baseline_temperature_K",
        )
        amplitude = _finite(initial["amplitude_K"], "initial_condition.amplitude_K")
        if baseline + min(0.0, amplitude) < 0.0:
            raise HeatConductionSolverError(
                "sine_mode initial field would cross below absolute zero"
            )
        if not math.isclose(left_K, baseline, rel_tol=0.0, abs_tol=1e-12) or not math.isclose(
            right_K, baseline, rel_tol=0.0, abs_tol=1e-12
        ):
            raise HeatConductionSolverError(
                "sine_mode requires both fixed boundaries to equal baseline_temperature_K"
            )
        field = [
            baseline + amplitude * math.sin(math.pi * position / length_m)
            for position in grid
        ]
        normalized = {
            "kind": "sine_mode",
            "baseline_temperature_K": baseline,
            "amplitude_K": amplitude,
        }
    else:
        raise HeatConductionSolverError(
            "initial_condition.kind must be uniform or sine_mode"
        )
    field[0] = left_K
    field[-1] = right_K
    return field, normalized


def _parse_validation(
    value: object,
    *,
    initial: Mapping[str, Any],
) -> dict[str, Any]:
    validation = _mapping(value, "validation")
    kind = validation.get("kind")
    if kind == "none":
        _exact_keys(validation, field="validation", keys={"kind"})
        return {"kind": "none"}
    if kind == "sine_eigenmode_analytical":
        _exact_keys(
            validation,
            field="validation",
            keys={"kind", "max_abs_error_tolerance_K"},
        )
        if initial.get("kind") != "sine_mode":
            raise HeatConductionSolverError(
                "sine_eigenmode_analytical validation requires sine_mode initial condition"
            )
        tolerance = _finite(
            validation["max_abs_error_tolerance_K"],
            "validation.max_abs_error_tolerance_K",
            positive=True,
        )
        return {
            "kind": "sine_eigenmode_analytical",
            "max_abs_error_tolerance_K": tolerance,
        }
    raise HeatConductionSolverError(
        "validation.kind must be none or sine_eigenmode_analytical"
    )


def _finalize_result(result: dict[str, Any]) -> dict[str, Any]:
    result["result_sha256"] = _canonical_sha256(result)
    return result


def run_reference_heat_conduction_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and execute one deterministic, bounded heat-diffusion request."""
    value = _mapping(request, "request")
    _exact_keys(value, field="request", keys=_REQUIRED_TOP_LEVEL_KEYS)
    if value["schema_version"] != HEAT_SOLVER_SCHEMA_VERSION:
        raise HeatConductionSolverError("unsupported heat-solver schema_version")
    if value["solver_id"] != HEAT_SOLVER_ID:
        raise HeatConductionSolverError("solver_id does not match the audited solver")
    if value["solver_version"] != HEAT_SOLVER_VERSION:
        raise HeatConductionSolverError("solver_version does not match the audited solver")

    units = _mapping(value["units"], "units")
    material = _mapping(value["material"], "material")
    alpha, material_resolution = _resolve_material(material, units)

    domain = _mapping(value["domain"], "domain")
    _exact_keys(domain, field="domain", keys={"length_m", "node_count"})
    length_m = _finite(domain["length_m"], "domain.length_m", positive=True)
    node_count = _positive_integer(domain["node_count"], "domain.node_count", minimum=3)
    dx_m = length_m / float(node_count - 1)

    time = _mapping(value["time"], "time")
    _exact_keys(time, field="time", keys={"duration_s", "time_step_s"})
    duration_s = _finite(time["duration_s"], "time.duration_s", positive=True)
    dt_s = _finite(time["time_step_s"], "time.time_step_s", positive=True)
    raw_steps = duration_s / dt_s
    step_count = int(round(raw_steps))
    if step_count < 1 or not math.isclose(raw_steps, float(step_count), rel_tol=1e-12, abs_tol=1e-12):
        raise HeatConductionSolverError(
            "time.duration_s must be an integer multiple of time.time_step_s in v1"
        )

    left_K, right_K, normalized_boundaries = _parse_boundaries(
        value["boundary_conditions"]
    )
    grid = [dx_m * index for index in range(node_count)]
    grid[-1] = length_m
    initial_record = _mapping(value["initial_condition"], "initial_condition")
    field, normalized_initial = _initial_field(
        initial_record,
        grid=grid,
        length_m=length_m,
        left_K=left_K,
        right_K=right_K,
    )
    validation = _parse_validation(value["validation"], initial=normalized_initial)

    request_sha = _canonical_sha256(value)
    fourier_number = alpha * dt_s / (dx_m * dx_m)
    common: dict[str, Any] = {
        "schema_version": HEAT_SOLVER_SCHEMA_VERSION,
        "solver_identity": {
            "solver_id": HEAT_SOLVER_ID,
            "solver_version": HEAT_SOLVER_VERSION,
            "method": "explicit_ftcs_finite_difference",
            "equation": "dT/dt = alpha * d2T/dx2",
            "dimension": "1D",
            "constant_properties": True,
        },
        "request_sha256": request_sha,
        "units": dict(units),
        "material_property_resolution": material_resolution,
        "domain": {"length_m": length_m, "node_count": node_count, "dx_m": dx_m},
        "time": {
            "duration_s": duration_s,
            "time_step_s": dt_s,
            "requested_step_count": step_count,
        },
        "boundary_conditions": normalized_boundaries,
        "initial_condition": normalized_initial,
        "numerical_stability": {
            "fourier_number": fourier_number,
            "criterion": "alpha * dt / dx^2 <= 0.5",
            "limit": FTCS_STABILITY_LIMIT,
            "stable": fourier_number <= FTCS_STABILITY_LIMIT,
        },
        "autonomy_boundary": {
            "network_accessed": False,
            "physical_experiment_executed": False,
            "empirical_evidence_created": False,
            "scientific_status_changed": False,
            "material_identity_inferred": False,
            "process_specific_validity_claimed": False,
        },
    }

    if fourier_number > FTCS_STABILITY_LIMIT:
        return _finalize_result(
            {
                **common,
                "run_status": "rejected_numerically_unstable",
                "exit_state": {
                    "kind": "preflight_stability_rejection",
                    "completed_step_count": 0,
                    "requested_step_count": step_count,
                },
                "spatial_grid_m": grid,
                "final_temperature_K": None,
                "validation": {
                    "kind": validation["kind"],
                    "state": "not_run_due_to_stability_rejection",
                    "max_abs_error_K": None,
                    "tolerance_K": validation.get("max_abs_error_tolerance_K"),
                    "passed": None,
                },
                "deterministic_log": [
                    "request_contract_validated",
                    "material_and_units_contract_validated",
                    "ftcs_stability_limit_exceeded",
                    "time_marching_not_started",
                ],
            }
        )

    current = list(field)
    for _ in range(step_count):
        updated = list(current)
        for index in range(1, node_count - 1):
            updated[index] = current[index] + fourier_number * (
                current[index + 1] - 2.0 * current[index] + current[index - 1]
            )
        updated[0] = left_K
        updated[-1] = right_K
        if any(not math.isfinite(item) or item < 0.0 for item in updated):
            raise HeatConductionSolverError(
                "solver produced a non-finite or below-absolute-zero temperature"
            )
        current = updated

    validation_result: dict[str, Any]
    if validation["kind"] == "sine_eigenmode_analytical":
        baseline = float(normalized_initial["baseline_temperature_K"])
        amplitude = float(normalized_initial["amplitude_K"])
        decay = math.exp(-alpha * math.pi * math.pi * duration_s / (length_m * length_m))
        analytical = [
            baseline + amplitude * decay * math.sin(math.pi * position / length_m)
            for position in grid
        ]
        analytical[0] = left_K
        analytical[-1] = right_K
        max_error = max(abs(numeric - exact) for numeric, exact in zip(current, analytical))
        tolerance = float(validation["max_abs_error_tolerance_K"])
        validation_result = {
            "kind": "sine_eigenmode_analytical",
            "state": "passed" if max_error <= tolerance else "failed",
            "max_abs_error_K": max_error,
            "tolerance_K": tolerance,
            "passed": max_error <= tolerance,
            "analytical_final_temperature_K": analytical,
        }
    else:
        validation_result = {
            "kind": "none",
            "state": "not_requested",
            "max_abs_error_K": None,
            "tolerance_K": None,
            "passed": None,
        }

    return _finalize_result(
        {
            **common,
            "run_status": "completed",
            "exit_state": {
                "kind": "completed_time_horizon",
                "completed_step_count": step_count,
                "requested_step_count": step_count,
            },
            "spatial_grid_m": grid,
            "final_temperature_K": current,
            "validation": validation_result,
            "deterministic_log": [
                "request_contract_validated",
                "material_and_units_contract_validated",
                "ftcs_stability_criterion_satisfied",
                "time_horizon_completed",
                f"validation_state:{validation_result['state']}",
            ],
        }
    )


__all__ = [
    "FTCS_STABILITY_LIMIT",
    "HEAT_SOLVER_ACTION_TYPE",
    "HEAT_SOLVER_ACTION_VERSION",
    "HEAT_SOLVER_ID",
    "HEAT_SOLVER_SCHEMA_VERSION",
    "HEAT_SOLVER_VERSION",
    "HeatConductionSolverError",
    "run_reference_heat_conduction_request",
]
