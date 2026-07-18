import copy
import json
import math
from pathlib import Path

import numpy as np

from src.platform_core.diffusion_1d_benchmark import (
    evaluate_diffusion_benchmark,
    evaluate_exact_solution,
    run_diffusion_benchmark,
    run_ftcs_diffusion,
    validate_diffusion_config,
    validate_diffusion_result,
)


def _config():
    return json.loads(Path("configs/examples/pgir_diffusion_1d_benchmark.json").read_text(encoding="utf-8"))


def _validated(config=None):
    value, result = validate_diffusion_config(config or _config())
    assert result["valid"] is True
    assert value is not None
    return value


def test_valid_si_dimensions_and_domain_are_accepted():
    validated = _validated()
    assert validated.length == 1.0
    assert validated.diffusivity == 0.1
    assert validated.dx == 0.05
    assert validated.dt == 0.01
    assert math.isclose(validated.stability_ratio, 0.4)


def test_invalid_dimensions_are_blocked_before_execution():
    for path, value in [
        (("parameters", "diffusivity", "unit"), "s"),
        (("parameters", "length", "unit"), "s"),
        (("grid", "time_unit"), "m"),
    ]:
        config = copy.deepcopy(_config())
        cursor = config
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
        validated, result = validate_diffusion_config(config)
        assert validated is None
        assert result["status"] == "blocked_dimension_mismatch"
        assert result["solver_executed"] is False

    config = copy.deepcopy(_config())
    config["field_unit"] = "fraction"
    validated, result = validate_diffusion_config(config)
    assert validated is None
    assert result["status"] == "blocked_dimension_mismatch"


def test_invalid_values_small_grids_and_incompatible_conditions_are_blocked():
    for parameter in ("length", "diffusivity", "final_time"):
        config = copy.deepcopy(_config())
        config["parameters"][parameter]["value"] = 0.0
        assert run_diffusion_benchmark(config)["execution_status"] == "blocked_invalid_domain"

    config = copy.deepcopy(_config())
    config["grid"]["spatial_points"] = 2
    assert run_diffusion_benchmark(config)["execution_status"] == "blocked_invalid_domain"

    config = copy.deepcopy(_config())
    config["boundary_condition_id"] = "periodic"
    assert run_diffusion_benchmark(config)["execution_status"] == "blocked_initial_boundary_incompatibility"

    config = copy.deepcopy(_config())
    config["parameters"]["amplitude"]["value"] = float("nan")
    assert run_diffusion_benchmark(config)["execution_status"] == "blocked_invalid_domain"


def test_exact_solution_reproduces_initial_condition_boundaries_and_decay():
    validated = _validated()
    result = evaluate_exact_solution(validated)
    values = np.asarray(result["values"])
    x = np.asarray(result["x"])

    np.testing.assert_allclose(values[0], np.sin(math.pi * x), atol=1e-15)
    np.testing.assert_array_equal(values[:, 0], 0.0)
    np.testing.assert_array_equal(values[:, -1], 0.0)
    midpoint = validated.spatial_points // 2
    expected = math.exp(-validated.diffusivity * math.pi**2 * validated.final_time)
    assert math.isclose(values[-1, midpoint], expected, rel_tol=1e-14)
    assert validate_diffusion_result(result)["valid"] is True


def test_exact_and_ftcs_results_are_deterministic():
    validated = _validated()
    exact_a = evaluate_exact_solution(validated)
    exact_b = evaluate_exact_solution(validated)
    ftcs_a = run_ftcs_diffusion(validated)
    ftcs_b = run_ftcs_diffusion(validated)

    assert exact_a["checksum_sha256"] == exact_b["checksum_sha256"]
    assert ftcs_a["checksum_sha256"] == ftcs_b["checksum_sha256"]


def test_stable_ftcs_executes_and_preserves_requested_grid_and_zero_boundaries():
    validated = _validated()
    result = run_ftcs_diffusion(validated)
    values = np.asarray(result["values"])

    assert result["execution_status"] == "benchmark_executed"
    assert result["silent_adjustment_performed"] is False
    assert result["requested_dt"] == result["effective_dt"]
    assert result["requested_dx"] == result["effective_dx"]
    assert np.isfinite(values).all()
    assert values.min() >= -1e-12
    np.testing.assert_array_equal(values[:, 0], 0.0)
    np.testing.assert_array_equal(values[:, -1], 0.0)


def test_unstable_ftcs_is_blocked_without_silent_adjustment():
    config = copy.deepcopy(_config())
    config["grid"]["time_steps"] = 20
    validated = _validated(config)
    assert validated.stability_ratio > 0.5

    result = run_ftcs_diffusion(validated)
    assert result["execution_status"] == "blocked_unstable_numerical_configuration"
    assert result["solver_executed"] is False
    assert result["silent_adjustment_performed"] is False
    assert result["requested_dt"] == result["effective_dt"]


def test_evaluator_reports_bounded_error_and_residuals():
    validated = _validated()
    exact = evaluate_exact_solution(validated)
    numerical = run_ftcs_diffusion(validated)
    result = evaluate_diffusion_benchmark(validated, exact, numerical)
    metrics = result["metrics"]

    assert result["execution_status"] == "benchmark_executed_with_documented_numerical_error"
    assert 0 < metrics["l2_error_final_profile"] < 0.001
    assert 0 < metrics["maximum_absolute_error_final_profile"] < 0.002
    assert metrics["boundary_residual_max"] == 0.0
    assert metrics["initial_condition_residual_max"] < 1e-14
    assert metrics["finite_value_check"] is True
    assert metrics["nonnegative_field_check"] is True


def test_result_checksum_mismatch_is_detected():
    payload = evaluate_exact_solution(_validated())
    payload["values"][1][1] += 1.0
    result = validate_diffusion_result(payload)
    assert result["status"] == "blocked_artifact_mismatch"
    assert "checksum_mismatch" in result["errors"]
