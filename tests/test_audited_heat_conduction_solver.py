from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.heat_conduction_solver import (
    HeatConductionSolverError,
    run_reference_heat_conduction_request,
)
from materials_data_analyzer.research_loop.scientific_simulation_registry import (
    SolverContractRegistry,
    repository_design_simulation_contract,
    repository_heat_conduction_contract,
)
from materials_data_analyzer.research_loop.heat_conduction_solver import (
    run_reference_heat_conduction_request as heat_implementation,
)
from materials_data_analyzer.research_loop.design_simulation import simulate_design_structure


def _request() -> dict:
    return {
        "schema_version": "1.0",
        "solver_id": "heat_conduction_1d_explicit_ftcs",
        "solver_version": "1.0",
        "units": {
            "length": "m",
            "time": "s",
            "temperature": "K",
            "thermal_diffusivity": "m^2/s",
        },
        "domain": {"length_m": 1.0, "node_count": 11},
        "time": {"duration_s": 1.0, "time_step_s": 0.1},
        "material": {"thermal_diffusivity_m2_s": 0.01},
        "initial_condition": {
            "kind": "sine_mode",
            "baseline_temperature_K": 300.0,
            "amplitude_K": 10.0,
        },
        "boundary_conditions": {
            "left": {"kind": "fixed_temperature", "temperature_K": 300.0},
            "right": {"kind": "fixed_temperature", "temperature_K": 300.0},
        },
        "validation": {
            "kind": "sine_eigenmode_analytical",
            "max_abs_error_tolerance_K": 0.1,
        },
    }


def test_sine_mode_matches_analytical_reference_and_is_deterministic() -> None:
    first = run_reference_heat_conduction_request(_request())
    second = run_reference_heat_conduction_request(_request())
    assert first == second
    assert first["run_status"] == "completed"
    assert first["numerical_stability"]["stable"] is True
    assert first["numerical_stability"]["fourier_number"] == pytest.approx(0.1)
    assert first["validation"]["passed"] is True
    assert first["validation"]["max_abs_error_K"] <= 0.1
    assert len(first["request_sha256"]) == 64
    assert len(first["result_sha256"]) == 64
    assert first["autonomy_boundary"]["empirical_evidence_created"] is False
    assert first["autonomy_boundary"]["scientific_status_changed"] is False


def test_unstable_ftcs_request_is_structured_rejection_without_time_marching() -> None:
    request = _request()
    request["time"] = {"duration_s": 1.0, "time_step_s": 0.6}
    # Keep duration an integer multiple while forcing Fo > 0.5.
    request["time"] = {"duration_s": 1.2, "time_step_s": 0.6}
    result = run_reference_heat_conduction_request(request)
    assert result["run_status"] == "rejected_numerically_unstable"
    assert result["numerical_stability"]["stable"] is False
    assert result["exit_state"]["completed_step_count"] == 0
    assert result["final_temperature_K"] is None
    assert result["validation"]["state"] == "not_run_due_to_stability_rejection"


def test_units_and_material_property_contract_fail_closed() -> None:
    wrong_units = _request()
    wrong_units["units"]["length"] = "mm"
    with pytest.raises(HeatConductionSolverError, match="SI contract"):
        run_reference_heat_conduction_request(wrong_units)

    ambiguous_properties = _request()
    ambiguous_properties["material"] = {
        "thermal_diffusivity_m2_s": 0.01,
        "thermal_conductivity_W_mK": 10.0,
        "density_kg_m3": 1000.0,
        "specific_heat_J_kgK": 1000.0,
    }
    with pytest.raises(HeatConductionSolverError, match="exactly"):
        run_reference_heat_conduction_request(ambiguous_properties)


def test_derived_diffusivity_is_explicit_and_auditable() -> None:
    request = _request()
    request["units"] = {
        "length": "m",
        "time": "s",
        "temperature": "K",
        "thermal_conductivity": "W/(m*K)",
        "density": "kg/m^3",
        "specific_heat": "J/(kg*K)",
    }
    request["material"] = {
        "thermal_conductivity_W_mK": 10.0,
        "density_kg_m3": 1000.0,
        "specific_heat_J_kgK": 1000.0,
    }
    result = run_reference_heat_conduction_request(request)
    resolution = result["material_property_resolution"]
    assert resolution["mode"] == "derived_from_k_rho_cp"
    assert resolution["thermal_diffusivity_m2_s"] == pytest.approx(1.0e-5)
    assert resolution["derivation"] == "alpha = k / (rho * cp)"


def test_request_tampering_changes_request_and_result_sha() -> None:
    first = run_reference_heat_conduction_request(_request())
    modified = copy.deepcopy(_request())
    modified["initial_condition"]["amplitude_K"] = 11.0
    second = run_reference_heat_conduction_request(modified)
    assert first["request_sha256"] != second["request_sha256"]
    assert first["result_sha256"] != second["result_sha256"]


def test_registry_distinguishes_structural_shell_from_true_physics_solver() -> None:
    structural = repository_design_simulation_contract()
    heat = repository_heat_conduction_contract()
    assert structural.physics_solver is False
    assert structural.governing_equation is None
    assert heat.physics_solver is True
    assert heat.governing_equation == "dT/dt = alpha * d2T/dx2"
    assert heat.empirical_validation_status == "not_established"

    registry = SolverContractRegistry()
    registry.register_attested(structural, implementation=simulate_design_structure)
    registry.register_attested(heat, implementation=heat_implementation)
    assert registry.get(heat.solver_id) == heat
