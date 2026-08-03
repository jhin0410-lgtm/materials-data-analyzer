"""Bounded analytical and FTCS benchmark for one-dimensional diffusion.

The implementation supports one registered synthetic problem only. It is not
a general PDE engine and does not fit parameters, access a network, or infer
material properties.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .pgir_model_contracts import (
    DIFFUSION_MODEL_CONTRACT_ID,
    EVALUATOR_OPERATOR_ID,
    EXACT_OPERATOR_ID,
    FTCS_OPERATOR_ID,
    PGIRModelContract,
    build_diffusion_model_contract,
    canonical_json_sha256,
    validate_pgir_model_contract,
)
from .pgir_conformance import (
    PGIRRepresentationDeclaration,
    evaluate_capability,
    validate_declaration,
    validate_transition,
)
from .quantities import ScientificQuantity, build_quantity_value
from .unit_backend import BuiltinUnitBackend


DIFFUSION_BENCHMARK_VERSION = "2.4.2"
CONFIG_SCHEMA_VERSION = "1"
RESULT_SCHEMA_VERSION = "1"
MODEL_CONTRACT_PATH = "data/platform/pgir_diffusion_1d_model_contract_v1.json"
DEFAULT_OUTPUT_ROOT = "outputs/v2_4_diffusion_benchmark"

TRACKED_PATHS = {
    "model_contract_summary": "data/processed/v2_4_diffusion_model_contract_summary.json",
    "execution_summary": "data/processed/v2_4_diffusion_execution_summary.json",
    "error_summary": "data/processed/v2_4_diffusion_error_summary.csv",
    "refinement_summary": "data/processed/v2_4_diffusion_refinement_summary.csv",
    "trust_summary": "data/processed/v2_4_diffusion_trust_summary.json",
    "claim_evidence": "data/processed/v2_4_diffusion_claim_evidence.json",
    "report_summary": "data/processed/v2_4_diffusion_report_summary.md",
}

ALLOWED_EXECUTION_STATUSES = (
    "benchmark_executed",
    "benchmark_executed_with_documented_numerical_error",
    "blocked_invalid_model_contract",
    "blocked_dimension_mismatch",
    "blocked_invalid_domain",
    "blocked_initial_boundary_incompatibility",
    "blocked_unstable_numerical_configuration",
    "blocked_nonfinite_result",
    "blocked_nondeterministic_result",
    "blocked_artifact_mismatch",
)
_TOP_LEVEL_FIELDS = {
    "schema_version",
    "benchmark_id",
    "model_contract_id",
    "model_contract_version",
    "parameters",
    "field_unit",
    "grid",
    "initial_condition_id",
    "boundary_condition_id",
    "output_root",
    "synthetic_benchmark",
    "credential_policy",
}
_PARAMETER_FIELDS = {"value", "unit"}
_GRID_FIELDS = {"spatial_points", "time_steps", "spatial_unit", "time_unit"}
_REFINEMENT_FIELDS = {
    "schema_version",
    "audit_id",
    "model_contract_id",
    "model_contract_version",
    "parameters",
    "field_unit",
    "spatial_unit",
    "time_unit",
    "initial_condition_id",
    "boundary_condition_id",
    "cases",
    "output_root",
    "synthetic_benchmark",
    "credential_policy",
}
_CASE_FIELDS = {"case_id", "spatial_points", "time_steps"}
_CREDENTIAL_POLICY_FIELDS = {"store_credentials"}
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")

PRESERVED_V2_4_1_CANONICAL_SHA256 = {
    "data/processed/v2_4_external_source_contract_summary.json": "600f005b9c37b09927758fbb0f5cb7588645ef96e3fc0aeacd758312b7ed6e63",
    "data/processed/v2_4_source_provenance_summary.csv": "182fbfd63b119358676d57ce8d490f89fcc4e5bfa381bedefd960863456280ad",
    "data/processed/v2_4_materials_pgir_conformance_summary.csv": "adfb0b0d113fbc83ead9a0f70bcca845cc5acea56c26e29305f41a4d778d84c1",
    "data/processed/v2_4_cross_domain_reuse_evidence.json": "4c0bfd38971460c513e91f52054a150c6dc825c7e8ddd592bd3551ca8f0ae72d",
    "data/processed/v2_4_pgir_reuse_decision.json": "b6a61d97c5dbc5b52c999d234c591003c18cd16f2e61380e80a18da2e7667aa5",
    "data/processed/v2_4_report_summary.md": "2faf47e17caaa482e53d94b2e53433e0588a7528d7803712ed824494326f59f7",
}


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _checksum(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _assert_relative_path(value: str, field_name: str) -> None:
    normalized = value.replace("\\", "/")
    if normalized.startswith(("/", "//")) or _WINDOWS_ABSOLUTE.match(value):
        raise ValueError(f"{field_name} must be repository-relative")
    if ".." in Path(normalized).parts:
        raise ValueError(f"{field_name} cannot traverse parent directories")


def _strict_fields(payload: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unknown fields: {unknown}")


def _quantity(quantity_id: str, payload: Mapping[str, Any]) -> ScientificQuantity:
    _strict_fields(payload, _PARAMETER_FIELDS, quantity_id)
    if set(payload) != _PARAMETER_FIELDS:
        raise ValueError(f"{quantity_id} requires value and unit")
    return ScientificQuantity(
        quantity_id=quantity_id,
        value=build_quantity_value(
            value=float(payload["value"]),
            unit=str(payload["unit"]),
            provenance_refs=("synthetic_diffusion_benchmark_config",),
        ),
    )


def _quantity_summary(quantity: ScientificQuantity) -> dict[str, Any]:
    if quantity.value is None:
        raise ValueError("diffusion benchmark quantity requires a scalar value")
    return {
        "quantity_id": quantity.quantity_id,
        "value": quantity.value.value,
        "unit": quantity.value.original_unit,
        "canonical_value": quantity.value.canonical_value,
        "canonical_unit": quantity.value.canonical_unit,
        "dimension": quantity.value.dimension,
        "uncertainty": quantity.value.uncertainty.to_dict(),
    }


@dataclass(frozen=True)
class ValidatedDiffusionInput:
    benchmark_id: str
    length: float
    diffusivity: float
    amplitude: float
    final_time: float
    field_unit: str
    spatial_points: int
    time_steps: int
    output_root: str
    quantities: tuple[ScientificQuantity, ...]

    @property
    def dx(self) -> float:
        return self.length / (self.spatial_points - 1)

    @property
    def dt(self) -> float:
        return self.final_time / self.time_steps

    @property
    def stability_ratio(self) -> float:
        return self.diffusivity * self.dt / (self.dx**2)

    def compact_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "parameters": {item.quantity_id: _quantity_summary(item) for item in self.quantities},
            "field_unit": self.field_unit,
            "grid": {
                "spatial_points": self.spatial_points,
                "time_steps": self.time_steps,
                "dx_m": self.dx,
                "dt_s": self.dt,
                "stability_ratio": self.stability_ratio,
            },
            "output_root": self.output_root,
        }


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("configuration must be a JSON object")
    return payload


def validate_diffusion_config(
    config: Mapping[str, Any],
    contract: PGIRModelContract | None = None,
) -> tuple[ValidatedDiffusionInput | None, dict[str, Any]]:
    """Validate one bounded benchmark input without evaluating a field."""

    contract = contract or build_diffusion_model_contract()
    contract_validation = validate_pgir_model_contract(contract)
    if not contract_validation["valid"]:
        return None, {
            "status": "blocked_invalid_model_contract",
            "valid": False,
            "errors": contract_validation["errors"],
            "solver_executed": False,
        }
    try:
        _strict_fields(config, _TOP_LEVEL_FIELDS, "diffusion benchmark config")
        required = _TOP_LEVEL_FIELDS - {"output_root"}
        missing = sorted(required - set(config))
        if missing:
            raise ValueError(f"diffusion benchmark config missing fields: {missing}")
        if config["schema_version"] != CONFIG_SCHEMA_VERSION:
            raise ValueError(f"unsupported config schema_version: {config['schema_version']}")
        if config["model_contract_id"] != DIFFUSION_MODEL_CONTRACT_ID or config["model_contract_version"] != "1":
            raise ValueError("config references an unsupported model contract")
        if config["synthetic_benchmark"] is not True:
            raise ValueError("the registered benchmark must be marked synthetic")
        credential_policy = config["credential_policy"]
        if not isinstance(credential_policy, Mapping):
            raise ValueError("credential_policy must be an object")
        _strict_fields(credential_policy, _CREDENTIAL_POLICY_FIELDS, "credential_policy")
        if credential_policy != {"store_credentials": False}:
            raise ValueError("credential_policy must disable credential storage")
        if config["initial_condition_id"] != "single_sine_mode_zero_dirichlet_v1":
            return None, {
                "status": "blocked_initial_boundary_incompatibility",
                "valid": False,
                "errors": ["unsupported_initial_condition"],
                "solver_executed": False,
            }
        if config["boundary_condition_id"] != "homogeneous_zero_dirichlet":
            return None, {
                "status": "blocked_initial_boundary_incompatibility",
                "valid": False,
                "errors": ["unsupported_boundary_condition"],
                "solver_executed": False,
            }
        parameters = config["parameters"]
        if not isinstance(parameters, Mapping):
            raise ValueError("parameters must be an object")
        expected_parameters = {"length", "diffusivity", "amplitude", "final_time"}
        _strict_fields(parameters, expected_parameters, "parameters")
        missing_parameters = sorted(expected_parameters - set(parameters))
        if missing_parameters:
            raise ValueError(f"parameters missing fields: {missing_parameters}")
        for name in expected_parameters:
            raw_value = float(parameters[name]["value"])
            if not math.isfinite(raw_value):
                return None, {
                    "status": "blocked_invalid_domain",
                    "valid": False,
                    "errors": [f"{name} must be finite"],
                    "solver_executed": False,
                }
        quantities = tuple(_quantity(name, parameters[name]) for name in sorted(expected_parameters))
        quantity_map = {item.quantity_id: item for item in quantities}
        expected_dimensions = {
            "length": "length",
            "diffusivity": "diffusivity",
            "amplitude": "dimensionless",
            "final_time": "time",
        }
        dimension_errors = []
        for name, dimension in expected_dimensions.items():
            if quantity_map[name].value is None:
                raise ValueError(f"diffusion benchmark quantity {name} requires a scalar value")
            if quantity_map[name].value.dimension != dimension:
                dimension_errors.append(f"{name}:expected_{dimension}:got_{quantity_map[name].value.dimension}")
        backend = BuiltinUnitBackend()
        field_unit = str(config["field_unit"])
        if backend.dimensionality(field_unit) != quantity_map["amplitude"].value.dimension:
            dimension_errors.append("amplitude_and_field_unit_mismatch")
        if field_unit != quantity_map["amplitude"].value.original_unit:
            dimension_errors.append("amplitude_and_field_unit_must_match_exactly")
        grid = config["grid"]
        if not isinstance(grid, Mapping):
            raise ValueError("grid must be an object")
        _strict_fields(grid, _GRID_FIELDS, "grid")
        if set(grid) != _GRID_FIELDS:
            raise ValueError("grid requires spatial_points, time_steps, spatial_unit and time_unit")
        if backend.dimensionality(str(grid["spatial_unit"])) != "length":
            dimension_errors.append("spatial_grid_unit_not_length")
        if backend.dimensionality(str(grid["time_unit"])) != "time":
            dimension_errors.append("time_grid_unit_not_time")
        if dimension_errors:
            return None, {
                "status": "blocked_dimension_mismatch",
                "valid": False,
                "errors": dimension_errors,
                "solver_executed": False,
            }
        length = quantity_map["length"].value.canonical_value
        diffusivity = quantity_map["diffusivity"].value.canonical_value
        amplitude = quantity_map["amplitude"].value.canonical_value
        final_time = quantity_map["final_time"].value.canonical_value
        spatial_points = int(grid["spatial_points"])
        time_steps = int(grid["time_steps"])
        if length <= 0 or diffusivity <= 0 or final_time <= 0:
            return None, {
                "status": "blocked_invalid_domain",
                "valid": False,
                "errors": ["L, D and final_time must be positive"],
                "solver_executed": False,
            }
        if not math.isfinite(amplitude):
            return None, {
                "status": "blocked_invalid_domain",
                "valid": False,
                "errors": ["A must be finite"],
                "solver_executed": False,
            }
        if spatial_points < 3 or spatial_points > 1001 or time_steps < 1 or time_steps > 100000:
            return None, {
                "status": "blocked_invalid_domain",
                "valid": False,
                "errors": ["grid size is outside bounded contract limits"],
                "solver_executed": False,
            }
        output_root = str(config.get("output_root", DEFAULT_OUTPUT_ROOT))
        _assert_relative_path(output_root, "output_root")
        if not output_root.replace("\\", "/").startswith("outputs/v2_4_diffusion_benchmark"):
            raise ValueError("output_root must stay under outputs/v2_4_diffusion_benchmark")
        validated = ValidatedDiffusionInput(
            benchmark_id=str(config["benchmark_id"]),
            length=length,
            diffusivity=diffusivity,
            amplitude=amplitude,
            final_time=final_time,
            field_unit=field_unit,
            spatial_points=spatial_points,
            time_steps=time_steps,
            output_root=output_root.replace("\\", "/"),
            quantities=quantities,
        )
        return validated, {
            "status": "valid",
            "valid": True,
            "errors": [],
            "solver_executed": False,
            "model_contract_checksum": contract_validation["model_contract_checksum"],
            "input_checksum": _checksum(validated.compact_dict()),
        }
    except (KeyError, TypeError, ValueError) as exc:
        return None, {
            "status": "blocked_invalid_model_contract",
            "valid": False,
            "errors": [str(exc)],
            "solver_executed": False,
        }


def preview_diffusion_benchmark(config: Mapping[str, Any]) -> dict[str, Any]:
    validated, validation = validate_diffusion_config(config)
    contract = build_diffusion_model_contract()
    payload: dict[str, Any] = {
        "schema_version": DIFFUSION_BENCHMARK_VERSION,
        "status": validation["status"] if not validation["valid"] else "benchmark_preview_ready",
        "solver_executed": False,
        "network_called": False,
        "model_fitting_performed": False,
        "model_contract_id": contract.model_contract_id,
        "initial_condition": contract.initial_condition.to_dict(),
        "boundary_conditions": [item.to_dict() for item in contract.boundary_conditions],
        "output_policy": "field_arrays_local_only_compact_metadata_tracked",
        "allowed_claims": list(contract.allowed_claims),
        "prohibited_claims": list(contract.prohibited_claims),
        "errors": validation["errors"],
    }
    if validated is not None:
        payload["input"] = validated.compact_dict()
        payload["ftcs_stability"] = {
            "ratio": validated.stability_ratio,
            "requirement": "0 < D*dt/dx^2 <= 0.5",
            "stable": 0 < validated.stability_ratio <= 0.5,
            "silent_adjustment_allowed": False,
        }
    return payload


def _grid(validated: ValidatedDiffusionInput) -> tuple[np.ndarray, np.ndarray]:
    x = np.linspace(0.0, validated.length, validated.spatial_points, dtype=np.float64)
    t = np.linspace(0.0, validated.final_time, validated.time_steps + 1, dtype=np.float64)
    if not np.allclose(np.diff(x), validated.dx, rtol=0.0, atol=1e-14):
        raise ValueError("spatial grid is not uniform")
    if not np.allclose(np.diff(t), validated.dt, rtol=0.0, atol=1e-14):
        raise ValueError("time grid is not uniform")
    return x, t


def evaluate_exact_solution(validated: ValidatedDiffusionInput) -> dict[str, Any]:
    x, t = _grid(validated)
    decay = np.exp(-validated.diffusivity * (math.pi**2) * t / (validated.length**2))
    values = validated.amplitude * decay[:, None] * np.sin(math.pi * x[None, :] / validated.length)
    values[:, 0] = 0.0
    values[:, -1] = 0.0
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "result_id": f"{validated.benchmark_id}.exact",
        "result_type": "scalar_field_1d",
        "operator_id": EXACT_OPERATOR_ID,
        "operator_role": "Propagator",
        "execution_status": "benchmark_executed",
        "field_id": "scalar_field_c",
        "field_unit": validated.field_unit,
        "x_unit": "m",
        "time_unit": "s",
        "x": x.tolist(),
        "time": t.tolist(),
        "values": values.tolist(),
        "shape": list(values.shape),
        "deterministic": True,
        "network_called": False,
        "model_fitting_performed": False,
        "uncertainty": {"kind": "unavailable", "reason": "synthetic_exact_reference_has_no_empirical_uncertainty"},
    }
    payload["checksum_sha256"] = _checksum(payload)
    return payload


def run_ftcs_diffusion(validated: ValidatedDiffusionInput) -> dict[str, Any]:
    ratio = validated.stability_ratio
    if not (0 < ratio <= 0.5):
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "result_id": f"{validated.benchmark_id}.ftcs",
            "operator_id": FTCS_OPERATOR_ID,
            "operator_role": "Propagator",
            "execution_status": "blocked_unstable_numerical_configuration",
            "stability_ratio": ratio,
            "stability_requirement": "0 < D*dt/dx^2 <= 0.5",
            "requested_dx": validated.dx,
            "requested_dt": validated.dt,
            "effective_dx": validated.dx,
            "effective_dt": validated.dt,
            "silent_adjustment_performed": False,
            "solver_executed": False,
            "network_called": False,
            "model_fitting_performed": False,
        }
    x, t = _grid(validated)
    values = np.zeros((len(t), len(x)), dtype=np.float64)
    values[0, :] = validated.amplitude * np.sin(math.pi * x / validated.length)
    values[0, 0] = 0.0
    values[0, -1] = 0.0
    for index in range(validated.time_steps):
        values[index + 1, 1:-1] = values[index, 1:-1] + ratio * (
            values[index, 2:] - (2.0 * values[index, 1:-1]) + values[index, :-2]
        )
        values[index + 1, 0] = 0.0
        values[index + 1, -1] = 0.0
    status = "benchmark_executed" if np.isfinite(values).all() else "blocked_nonfinite_result"
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "result_id": f"{validated.benchmark_id}.ftcs",
        "result_type": "scalar_field_1d",
        "operator_id": FTCS_OPERATOR_ID,
        "operator_role": "Propagator",
        "execution_status": status,
        "field_id": "scalar_field_c",
        "field_unit": validated.field_unit,
        "x_unit": "m",
        "time_unit": "s",
        "x": x.tolist(),
        "time": t.tolist(),
        "values": values.tolist(),
        "shape": list(values.shape),
        "stability_ratio": ratio,
        "stability_requirement": "0 < D*dt/dx^2 <= 0.5",
        "requested_dx": validated.dx,
        "requested_dt": validated.dt,
        "effective_dx": validated.dx,
        "effective_dt": validated.dt,
        "silent_adjustment_performed": False,
        "deterministic": True,
        "solver_executed": True,
        "network_called": False,
        "model_fitting_performed": False,
        "uncertainty": {
            "kind": "unavailable",
            "reason": "source_does_not_provide_uncertainty_numerical_error_reported_separately",
        },
    }
    payload["checksum_sha256"] = _checksum(payload)
    return payload


def validate_diffusion_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "result_id",
        "operator_id",
        "operator_role",
        "execution_status",
    }
    errors = [f"missing:{key}" for key in sorted(required - set(payload))]
    status = payload.get("execution_status")
    if status not in ALLOWED_EXECUTION_STATUSES:
        errors.append(f"unsupported_execution_status:{status}")
    if status in {"benchmark_executed", "benchmark_executed_with_documented_numerical_error"}:
        for key in ("x", "time", "values", "shape", "checksum_sha256"):
            if key not in payload:
                errors.append(f"missing:{key}")
        if not errors:
            checksum_payload = dict(payload)
            claimed = checksum_payload.pop("checksum_sha256")
            if _checksum(checksum_payload) != claimed:
                errors.append("checksum_mismatch")
            values = np.asarray(payload["values"], dtype=float)
            if list(values.shape) != list(payload["shape"]):
                errors.append("shape_mismatch")
            if not np.isfinite(values).all():
                errors.append("nonfinite_field_values")
    return {
        "status": "valid" if not errors else "blocked_artifact_mismatch",
        "valid": not errors,
        "errors": errors,
        "result_id": payload.get("result_id"),
    }


def evaluate_diffusion_benchmark(
    validated: ValidatedDiffusionInput,
    exact: Mapping[str, Any],
    numerical: Mapping[str, Any],
) -> dict[str, Any]:
    if numerical.get("execution_status") != "benchmark_executed":
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "evaluation_id": f"{validated.benchmark_id}.evaluation",
            "operator_id": EVALUATOR_OPERATOR_ID,
            "execution_status": numerical.get("execution_status"),
            "errors": ["numerical propagator did not execute"],
            "evaluator_executed": False,
        }
    exact_values = np.asarray(exact["values"], dtype=float)
    numerical_values = np.asarray(numerical["values"], dtype=float)
    if exact_values.shape != numerical_values.shape:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "evaluation_id": f"{validated.benchmark_id}.evaluation",
            "operator_id": EVALUATOR_OPERATOR_ID,
            "execution_status": "blocked_artifact_mismatch",
            "errors": ["exact and numerical shapes differ"],
            "evaluator_executed": False,
        }
    error = numerical_values - exact_values
    initial_expected = validated.amplitude * np.sin(
        math.pi * np.asarray(exact["x"], dtype=float) / validated.length
    )
    boundary_residual = float(
        max(np.abs(numerical_values[:, 0]).max(), np.abs(numerical_values[:, -1]).max())
    )
    initial_residual = float(np.abs(numerical_values[0] - initial_expected).max())
    final_error = error[-1]
    l2_error = float(np.sqrt(np.mean(final_error**2)))
    max_abs_error = float(np.abs(final_error).max())
    global_l2_error = float(np.sqrt(np.mean(error**2)))
    finite = bool(np.isfinite(numerical_values).all())
    minimum_value = float(numerical_values.min())
    nonnegative = minimum_value >= -1e-12 if validated.amplitude >= 0 else True
    status = "benchmark_executed_with_documented_numerical_error"
    if not finite:
        status = "blocked_nonfinite_result"
    elif boundary_residual > 1e-12 or initial_residual > 1e-12:
        status = "blocked_artifact_mismatch"
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "evaluation_id": f"{validated.benchmark_id}.evaluation",
        "operator_id": EVALUATOR_OPERATOR_ID,
        "operator_role": "Evaluator",
        "execution_status": status,
        "evaluator_executed": True,
        "benchmark_id": validated.benchmark_id,
        "exact_result_checksum": exact["checksum_sha256"],
        "numerical_result_checksum": numerical["checksum_sha256"],
        "metrics": {
            "l2_error_final_profile": l2_error,
            "maximum_absolute_error_final_profile": max_abs_error,
            "l2_error_all_grid_points": global_l2_error,
            "boundary_residual_max": boundary_residual,
            "initial_condition_residual_max": initial_residual,
            "finite_value_check": finite,
            "nonnegative_field_check": nonnegative,
            "minimum_numerical_value": minimum_value,
        },
        "stability_ratio": validated.stability_ratio,
        "uncertainty": {
            "kind": "unavailable",
            "reason": "no_empirical_uncertainty_numerical_error_reported_against_exact_reference",
        },
        "claim_boundary": {
            "synthetic_benchmark": True,
            "battery_mechanism": False,
            "real_material_diffusivity": False,
            "cross_domain_physical_operator_reuse": False,
            "independent_validation": False,
            "production_validation": False,
        },
    }
    payload["deterministic_checksum_sha256"] = _checksum(payload)
    return payload


def run_diffusion_benchmark(
    config: Mapping[str, Any],
    *,
    repo_root: str | Path = ".",
    write_local: bool = False,
) -> dict[str, Any]:
    validated, validation = validate_diffusion_config(config)
    if validated is None:
        return {
            "schema_version": DIFFUSION_BENCHMARK_VERSION,
            "execution_status": validation["status"],
            "validation": validation,
            "solver_executed": False,
        }
    if not (0 < validated.stability_ratio <= 0.5):
        numerical = run_ftcs_diffusion(validated)
        return {
            "schema_version": DIFFUSION_BENCHMARK_VERSION,
            "execution_status": numerical["execution_status"],
            "validation": validation,
            "input": validated.compact_dict(),
            "numerical": numerical,
            "solver_executed": False,
        }
    exact = evaluate_exact_solution(validated)
    numerical = run_ftcs_diffusion(validated)
    evaluation = evaluate_diffusion_benchmark(validated, exact, numerical)
    contract = build_diffusion_model_contract()
    execution = {
        "schema_version": DIFFUSION_BENCHMARK_VERSION,
        "execution_id": f"{validated.benchmark_id}.execution",
        "execution_status": evaluation["execution_status"],
        "model_contract_id": contract.model_contract_id,
        "model_contract_checksum": canonical_json_sha256(contract.to_dict()),
        "input_checksum": validation["input_checksum"],
        "operator_ids": [EXACT_OPERATOR_ID, FTCS_OPERATOR_ID, EVALUATOR_OPERATOR_ID],
        "exact_result_checksum": exact["checksum_sha256"],
        "numerical_result_checksum": numerical["checksum_sha256"],
        "evaluator_result_checksum": evaluation["deterministic_checksum_sha256"],
        "solver_executed": True,
        "physical_operator_execution_demonstrated": True,
        "network_called": False,
        "model_fitting_performed": False,
        "cross_domain_physical_operator_reuse": False,
        "independent_validation": False,
        "production_validation": False,
        "input": validated.compact_dict(),
        "exact": exact,
        "numerical": numerical,
        "evaluation": evaluation,
    }
    execution["pgir_conformance"] = _build_pgir_conformance(execution)
    execution["execution_checksum_sha256"] = _checksum(execution)
    if write_local:
        _write_local_benchmark(Path(repo_root), validated, config, contract, exact, numerical, evaluation, execution)
    return execution


def _build_pgir_conformance(execution: Mapping[str, Any]) -> dict[str, Any]:
    contract_id = str(execution["model_contract_id"])
    common = {
        "declaration_version": "1",
        "domain_context": "synthetic_scalar_diffusion_software_benchmark",
        "measurement_context": "synthetic_declared_scalar_field",
        "mechanism_context": "not_a_real_material_mechanism",
        "temporal_context": "declared_time_grid_from_zero",
        "spatial_context": "bounded_one_dimensional_uniform_grid",
        "validation_context": "analytical_reference_comparison",
        "provenance_refs": (contract_id, str(execution["input_checksum"])),
        "limitations": (
            "single sine mode",
            "constant synthetic diffusivity",
            "zero Dirichlet absorbing boundaries",
        ),
        "prohibited_interpretations": (
            "Battery diffusion mechanism",
            "real-material diffusivity",
            "cross-domain physical-operator reuse",
            "independent validation",
            "production validation",
        ),
    }
    declarations = (
        PGIRRepresentationDeclaration(
            declaration_id="diffusion_1d_model_declaration_v1",
            pgir_concept_id="model",
            representation_schema_id="pgir_model_contract_schema_v1",
            representation_schema_version="1",
            entity_or_artifact_ref=MODEL_CONTRACT_PATH,
            current_maturity_level="physically_admissible",
            claimed_capabilities=("bounded_physical_propagation",),
            evidence_refs=(str(execution["model_contract_checksum"]),),
            uncertainty_refs=("synthetic_parameter_uncertainty_unavailable",),
            **common,
        ),
        PGIRRepresentationDeclaration(
            declaration_id="diffusion_1d_exact_field_declaration_v1",
            pgir_concept_id="field",
            representation_schema_id="scalar_field_1d_result_schema_v1",
            representation_schema_version="1",
            entity_or_artifact_ref="outputs/v2_4_diffusion_benchmark/exact/exact_scalar_field.json",
            current_maturity_level="scientifically_evaluated",
            evidence_refs=(str(execution["exact_result_checksum"]),),
            uncertainty_refs=("synthetic_exact_reference_uncertainty_unavailable",),
            claimed_capabilities=(),
            **common,
        ),
        PGIRRepresentationDeclaration(
            declaration_id="diffusion_1d_ftcs_field_declaration_v1",
            pgir_concept_id="field",
            representation_schema_id="scalar_field_1d_result_schema_v1",
            representation_schema_version="1",
            entity_or_artifact_ref="outputs/v2_4_diffusion_benchmark/numerical/ftcs_scalar_field.json",
            current_maturity_level="scientifically_evaluated",
            evidence_refs=(str(execution["numerical_result_checksum"]),),
            uncertainty_refs=("discretization_error_evaluated_against_exact_reference",),
            claimed_capabilities=(),
            **common,
        ),
        PGIRRepresentationDeclaration(
            declaration_id="diffusion_1d_benchmark_result_declaration_v1",
            pgir_concept_id="result",
            representation_schema_id="analytical_numerical_benchmark_schema_v1",
            representation_schema_version="1",
            entity_or_artifact_ref="outputs/v2_4_diffusion_benchmark/trust/benchmark_evaluation.json",
            current_maturity_level="scientifically_evaluated",
            evidence_refs=(str(execution["evaluator_result_checksum"]),),
            uncertainty_refs=("empirical_uncertainty_unavailable_numerical_error_documented",),
            claimed_capabilities=("bounded_physical_validation",),
            **common,
        ),
    )
    declaration_records = []
    for declaration in declarations:
        findings = validate_declaration(declaration)
        declaration_records.append(
            {
                "declaration": declaration.to_dict(),
                "valid": not any(item.severity == "error" for item in findings),
                "findings": [item.to_dict() for item in findings],
            }
        )
    transition_inputs = (
        {
            "transition_id": EXACT_OPERATOR_ID,
            "metadata_available": ("model_contract_id", "input_checksum", "exact_result_checksum"),
        },
        {
            "transition_id": FTCS_OPERATOR_ID,
            "metadata_available": ("model_contract_id", "stability_ratio", "numerical_result_checksum"),
        },
        {
            "transition_id": EVALUATOR_OPERATOR_ID,
            "metadata_available": ("exact_result_checksum", "numerical_result_checksum", "evaluation_metrics"),
        },
    )
    transitions = [validate_transition(item).to_dict() for item in transition_inputs]
    capability = evaluate_capability(
        declarations[0],
        "bounded_physical_propagation",
        context={
            "registered_model_contract": True,
            "registered_operator": True,
            "bounded_execution_policy": True,
        },
    ).to_dict()
    valid = (
        all(item["valid"] for item in declaration_records)
        and all(item["transition_allowed"] for item in transitions)
        and capability["status"] == "eligible"
    )
    return {
        "status": "bounded_pgir_execution_conformant" if valid else "blocked_pgir_conformance",
        "valid": valid,
        "declarations": declaration_records,
        "transitions": transitions,
        "capability": capability,
        "result_maturity": "scientifically_evaluated" if valid else "physically_admissible",
        "platform_wide_independent_validation": False,
        "platform_wide_production_validation": False,
    }


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    temp.replace(path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    temp.replace(path)


def _write_csv_atomic(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})
    temp.replace(path)


def _write_local_benchmark(
    root: Path,
    validated: ValidatedDiffusionInput,
    config: Mapping[str, Any],
    contract: PGIRModelContract,
    exact: Mapping[str, Any],
    numerical: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> None:
    output = root / validated.output_root
    _write_json_atomic(output / "inputs" / "benchmark_config.json", config)
    _write_json_atomic(output / "inputs" / "model_contract.json", contract.to_dict())
    _write_json_atomic(output / "exact" / "exact_scalar_field.json", exact)
    _write_json_atomic(output / "numerical" / "ftcs_scalar_field.json", numerical)
    _write_json_atomic(output / "trust" / "benchmark_evaluation.json", evaluation)
    compact = build_compact_execution_summary(execution)
    _write_json_atomic(output / "reports" / "execution_summary.json", compact)
    _write_text_atomic(output / "reports" / "benchmark_report.md", render_benchmark_report(compact))


def _refinement_case_config(config: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": config["schema_version"],
        "benchmark_id": f"{config['audit_id']}.{case['case_id']}",
        "model_contract_id": config["model_contract_id"],
        "model_contract_version": config["model_contract_version"],
        "parameters": config["parameters"],
        "field_unit": config["field_unit"],
        "grid": {
            "spatial_points": case["spatial_points"],
            "time_steps": case["time_steps"],
            "spatial_unit": config["spatial_unit"],
            "time_unit": config["time_unit"],
        },
        "initial_condition_id": config["initial_condition_id"],
        "boundary_condition_id": config["boundary_condition_id"],
        "output_root": config.get("output_root", DEFAULT_OUTPUT_ROOT),
        "synthetic_benchmark": config["synthetic_benchmark"],
        "credential_policy": config["credential_policy"],
    }


def run_refinement_audit(
    config: Mapping[str, Any],
    *,
    repo_root: str | Path = ".",
    write_local: bool = False,
) -> dict[str, Any]:
    try:
        _strict_fields(config, _REFINEMENT_FIELDS, "refinement config")
        if set(config) != _REFINEMENT_FIELDS:
            raise ValueError(f"refinement config requires fields: {sorted(_REFINEMENT_FIELDS)}")
        cases = config["cases"]
        if not isinstance(cases, list) or len(cases) < 3:
            raise ValueError("refinement audit requires at least three predeclared cases")
        rows = []
        executions = []
        for order, case in enumerate(cases):
            if not isinstance(case, Mapping):
                raise ValueError("each refinement case must be an object")
            _strict_fields(case, _CASE_FIELDS, "refinement case")
            if set(case) != _CASE_FIELDS:
                raise ValueError("refinement case requires case_id, spatial_points and time_steps")
            execution = run_diffusion_benchmark(_refinement_case_config(config, case), repo_root=repo_root, write_local=False)
            executions.append(execution)
            if execution["execution_status"] != "benchmark_executed_with_documented_numerical_error":
                return {
                    "schema_version": DIFFUSION_BENCHMARK_VERSION,
                    "audit_id": config["audit_id"],
                    "execution_status": execution["execution_status"],
                    "errors": [f"refinement case blocked: {case['case_id']}"],
                    "solver_executed": bool(execution.get("solver_executed")),
                }
            metrics = execution["evaluation"]["metrics"]
            input_summary = execution["input"]
            rows.append(
                {
                    "refinement_order": order,
                    "case_id": case["case_id"],
                    "spatial_points": input_summary["grid"]["spatial_points"],
                    "time_steps": input_summary["grid"]["time_steps"],
                    "dx_m": input_summary["grid"]["dx_m"],
                    "dt_s": input_summary["grid"]["dt_s"],
                    "stability_ratio": input_summary["grid"]["stability_ratio"],
                    "l2_error_final_profile": metrics["l2_error_final_profile"],
                    "maximum_absolute_error_final_profile": metrics["maximum_absolute_error_final_profile"],
                    "execution_status": execution["execution_status"],
                    "execution_checksum_sha256": execution["execution_checksum_sha256"],
                }
            )
        errors = [float(row["l2_error_final_profile"]) for row in rows]
        decreasing = all(right < left for left, right in zip(errors, errors[1:]))
        fine_lower_than_coarse = errors[-1] < errors[0]
        audit = {
            "schema_version": DIFFUSION_BENCHMARK_VERSION,
            "audit_id": config["audit_id"],
            "execution_status": (
                "benchmark_executed_with_documented_numerical_error"
                if decreasing and fine_lower_than_coarse
                else "blocked_artifact_mismatch"
            ),
            "predeclared_case_count": len(rows),
            "cases": rows,
            "error_strictly_decreases": decreasing,
            "fine_error_lower_than_coarse": fine_lower_than_coarse,
            "exact_convergence_order_claimed": False,
            "solver_executed": True,
            "network_called": False,
            "model_fitting_performed": False,
        }
        audit["audit_checksum_sha256"] = _checksum(audit)
        if write_local:
            output = Path(repo_root) / str(config["output_root"]) / "refinement"
            _write_json_atomic(output / "refinement_audit.json", audit)
        return audit
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "schema_version": DIFFUSION_BENCHMARK_VERSION,
            "execution_status": "blocked_invalid_model_contract",
            "errors": [str(exc)],
            "solver_executed": False,
        }


def build_compact_execution_summary(execution: Mapping[str, Any]) -> dict[str, Any]:
    evaluation = execution.get("evaluation", {})
    numerical = execution.get("numerical", {})
    conformance = execution.get("pgir_conformance", {})
    return {
        "schema_version": DIFFUSION_BENCHMARK_VERSION,
        "status": execution.get("execution_status"),
        "benchmark_id": execution.get("input", {}).get("benchmark_id"),
        "model_contract_id": execution.get("model_contract_id"),
        "model_contract_checksum": execution.get("model_contract_checksum"),
        "input_checksum": execution.get("input_checksum"),
        "operator_ids": list(execution.get("operator_ids", ())),
        "parameters": execution.get("input", {}).get("parameters", {}),
        "grid": execution.get("input", {}).get("grid", {}),
        "stability_ratio": numerical.get("stability_ratio"),
        "metrics": evaluation.get("metrics", {}),
        "exact_result_checksum": execution.get("exact_result_checksum"),
        "numerical_result_checksum": execution.get("numerical_result_checksum"),
        "evaluator_result_checksum": execution.get("evaluator_result_checksum"),
        "execution_checksum_sha256": execution.get("execution_checksum_sha256"),
        "pgir_conformance": {
            "status": conformance.get("status"),
            "valid": conformance.get("valid"),
            "declaration_count": len(conformance.get("declarations", ())),
            "transition_count": len(conformance.get("transitions", ())),
            "transitions_allowed": all(
                item.get("transition_allowed") for item in conformance.get("transitions", ())
            ) if conformance.get("transitions") else False,
            "capability_status": conformance.get("capability", {}).get("status"),
            "result_maturity": conformance.get("result_maturity"),
        },
        "physical_operator_execution_demonstrated": execution.get("physical_operator_execution_demonstrated", False),
        "cross_domain_physical_operator_reuse": False,
        "independent_validation": False,
        "production_validation": False,
        "field_arrays_tracked": False,
        "network_called": False,
        "model_fitting_performed": False,
    }


def evaluate_diffusion_claims(execution: Mapping[str, Any], refinement: Mapping[str, Any] | None = None) -> dict[str, Any]:
    execution_status = execution.get("execution_status", execution.get("status"))
    status_ok = execution_status == "benchmark_executed_with_documented_numerical_error"
    metrics = execution.get("evaluation", {}).get("metrics", execution.get("metrics", {}))
    refinement_ok = bool(
        refinement
        and refinement.get("error_strictly_decreases")
        and refinement.get("fine_error_lower_than_coarse")
    )
    evidence = [
        {"claim_id": "bounded_model_contract_execution", "supported": status_ok, "status": "supported_bounded" if status_ok else "not_supported"},
        {"claim_id": "analytical_numerical_comparison", "supported": bool(metrics), "status": "supported_bounded" if metrics else "not_supported"},
        {"claim_id": "declared_refinement_reduces_error", "supported": refinement_ok, "status": "supported_bounded" if refinement_ok else "not_evaluated"},
        {"claim_id": "battery_diffusion_mechanism", "supported": False, "status": "prohibited"},
        {"claim_id": "real_material_diffusivity", "supported": False, "status": "prohibited"},
        {"claim_id": "cross_domain_physical_operator_reuse", "supported": False, "status": "not_demonstrated"},
        {"claim_id": "independent_validation", "supported": False, "status": "not_demonstrated"},
        {"claim_id": "production_validation", "supported": False, "status": "prohibited"},
    ]
    return {
        "schema_version": DIFFUSION_BENCHMARK_VERSION,
        "status": "bounded_claim_evidence_recorded" if status_ok else "insufficient_execution_evidence",
        "evidence": evidence,
        "physical_operator_execution_demonstrated": status_ok,
        "cross_domain_physical_operator_reuse": False,
        "independent_validation": False,
        "production_validation": False,
    }


def build_trust_summary(execution: Mapping[str, Any], refinement: Mapping[str, Any]) -> dict[str, Any]:
    claims = evaluate_diffusion_claims(execution, refinement)
    checks = execution.get("evaluation", {}).get("metrics", {})
    valid = (
        execution.get("execution_status") == "benchmark_executed_with_documented_numerical_error"
        and bool(checks.get("finite_value_check"))
        and bool(checks.get("nonnegative_field_check"))
        and refinement.get("error_strictly_decreases") is True
    )
    return {
        "schema_version": DIFFUSION_BENCHMARK_VERSION,
        "status": "bounded_benchmark_validated" if valid else "bounded_benchmark_validation_incomplete",
        "maturity": "scientifically_evaluated_bounded_result" if valid else "physically_admissible",
        "physical_operator_execution_demonstrated": valid,
        "cross_domain_physical_operator_reuse": False,
        "independent_validation": False,
        "production_validation": False,
        "uncertainty_status": "empirical_uncertainty_unavailable_numerical_error_documented",
        "claim_evidence_status": claims["status"],
        "limitations": [
            "synthetic single-mode scalar field only",
            "fixed zero Dirichlet absorbing boundaries",
            "explicit FTCS backend only",
            "no empirical parameter uncertainty",
            "no Battery or real-material mechanism interpretation",
        ],
    }


def render_benchmark_report(summary: Mapping[str, Any]) -> str:
    metrics = summary.get("metrics", {})
    grid = summary.get("grid", {})
    return (
        "# PGIR 1D Diffusion Benchmark Summary\n\n"
        "This is a synthetic platform-validation benchmark, not a Battery or real-material diffusion model.\n\n"
        f"- Status: `{summary.get('status')}`\n"
        f"- Model contract: `{summary.get('model_contract_id')}`\n"
        f"- Grid: {grid.get('spatial_points')} spatial points, {grid.get('time_steps')} time steps\n"
        f"- FTCS stability ratio: {grid.get('stability_ratio')}\n"
        f"- Final-profile L2 error: {metrics.get('l2_error_final_profile')}\n"
        f"- Final-profile maximum absolute error: {metrics.get('maximum_absolute_error_final_profile')}\n"
        f"- Boundary residual: {metrics.get('boundary_residual_max')}\n"
        f"- Initial-condition residual: {metrics.get('initial_condition_residual_max')}\n"
        "- Cross-domain physical-operator reuse: not demonstrated\n"
        "- Independent validation: not demonstrated\n"
        "- Production validation: not demonstrated\n"
    )


def _error_rows(execution: Mapping[str, Any]) -> list[dict[str, Any]]:
    metrics = execution["evaluation"]["metrics"]
    return [
        {
            "schema_version": DIFFUSION_BENCHMARK_VERSION,
            "benchmark_id": execution["input"]["benchmark_id"],
            "metric_id": metric_id,
            "value": value,
            "scope": "final_profile" if "final_profile" in metric_id else "all_grid_points_or_boundary",
            "status": execution["execution_status"],
            "provenance_ref": execution["execution_checksum_sha256"],
        }
        for metric_id, value in sorted(metrics.items())
    ]


def export_diffusion_benchmark_summary(
    benchmark_config: Mapping[str, Any],
    refinement_config: Mapping[str, Any],
    *,
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    root = Path(repo_root)
    execution = run_diffusion_benchmark(benchmark_config, repo_root=root, write_local=True)
    refinement = run_refinement_audit(refinement_config, repo_root=root, write_local=True)
    if execution.get("execution_status") != "benchmark_executed_with_documented_numerical_error":
        return {"status": execution.get("execution_status"), "written": []}
    if refinement.get("execution_status") != "benchmark_executed_with_documented_numerical_error":
        return {"status": refinement.get("execution_status"), "written": []}
    contract = build_diffusion_model_contract()
    contract_summary = {
        "schema_version": DIFFUSION_BENCHMARK_VERSION,
        "status": "registered_bounded_benchmark",
        "model_contract_id": contract.model_contract_id,
        "model_contract_version": contract.model_contract_version,
        "model_contract_checksum": canonical_json_sha256(contract.to_dict()),
        "governing_relation_id": contract.governing_relation_id,
        "state_field": contract.scalar_field.to_dict(),
        "parameter_count": len(contract.parameters),
        "boundary_condition_count": len(contract.boundary_conditions),
        "operator_ids": [item.operator_id for item in contract.operator_requirements],
        "analytical_reference_available": True,
        "field_arrays_tracked": False,
    }
    compact = build_compact_execution_summary(execution)
    trust = build_trust_summary(execution, refinement)
    claims = evaluate_diffusion_claims(execution, refinement)
    payloads = {
        "model_contract_summary": contract_summary,
        "execution_summary": compact,
        "trust_summary": trust,
        "claim_evidence": claims,
    }
    written: list[str] = []
    _write_json_atomic(root / MODEL_CONTRACT_PATH, contract.to_dict())
    written.append(MODEL_CONTRACT_PATH)
    for key, payload in payloads.items():
        path = root / TRACKED_PATHS[key]
        _write_json_atomic(path, payload)
        written.append(TRACKED_PATHS[key])
    error_rows = _error_rows(execution)
    error_fields = ["schema_version", "benchmark_id", "metric_id", "value", "scope", "status", "provenance_ref"]
    _write_csv_atomic(root / TRACKED_PATHS["error_summary"], error_rows, error_fields)
    written.append(TRACKED_PATHS["error_summary"])
    refinement_fields = [
        "refinement_order",
        "case_id",
        "spatial_points",
        "time_steps",
        "dx_m",
        "dt_s",
        "stability_ratio",
        "l2_error_final_profile",
        "maximum_absolute_error_final_profile",
        "execution_status",
        "execution_checksum_sha256",
    ]
    _write_csv_atomic(root / TRACKED_PATHS["refinement_summary"], refinement["cases"], refinement_fields)
    written.append(TRACKED_PATHS["refinement_summary"])
    report = render_benchmark_report(compact) + (
        "\n## Refinement\n\n"
        f"- Predeclared cases: {refinement['predeclared_case_count']}\n"
        f"- Error strictly decreases: {str(refinement['error_strictly_decreases']).lower()}\n"
        f"- Fine error below coarse error: {str(refinement['fine_error_lower_than_coarse']).lower()}\n"
        "- Exact convergence order claimed: false\n"
    )
    _write_text_atomic(root / TRACKED_PATHS["report_summary"], report)
    written.append(TRACKED_PATHS["report_summary"])
    return {
        "status": "benchmark_summary_exported",
        "execution": compact,
        "refinement": refinement,
        "trust": trust,
        "claim_evidence": claims,
        "written": written,
    }


def validate_preserved_v2_4_1_results(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root)
    checks = []
    for relative_path, expected in sorted(PRESERVED_V2_4_1_CANONICAL_SHA256.items()):
        path = root / relative_path
        actual = None
        if path.exists():
            if path.suffix == ".json":
                actual = _checksum(json.loads(path.read_text(encoding="utf-8")))
            elif path.suffix == ".csv":
                with path.open(encoding="utf-8", newline="") as handle:
                    actual = _checksum(list(csv.reader(handle)))
            else:
                text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
                actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
        checks.append(
            {
                "relative_path": relative_path,
                "expected": expected,
                "actual": actual,
                "preserved": actual == expected,
            }
        )
    return {
        "status": "preserved" if all(item["preserved"] for item in checks) else "checksum_mismatch",
        "check_count": len(checks),
        "checks": checks,
    }
