"""Local identifiability of existing rod parameters, without refitting."""

import numpy as np

from .rod_thermal_contract import load_bound_view, require
from .rod_thermal_solver import predict, sampled_bdf_prediction

ACTION = "diagnose_rod_parameter_identifiability"
DESCRIPTION = (
    "Evaluate the local joint sensitivity of rod conductivity and effective heat loss."
)
RESULT = "identifiability.json"
LOG_STEP = 0.01
CONDITION_LIMIT = 10.0


def interior(model, spec):
    k, h = model["k_W_mK"], model["h_effective_W_m2K"]
    factor = np.exp(LOG_STEP)
    return (
        model["active_bounds"] == [0, 0]
        and spec["k_bounds"][0] < k / factor < k * factor < spec["k_bounds"][1]
        and 0 < h / factor < h * factor < spec["h_max"]
    )


def _spectrum(jacobian):
    column_norms = np.linalg.norm(jacobian, axis=0)
    if len(jacobian) < 2 or np.any(column_norms < 1e-10):
        return None
    normalized = jacobian / column_norms
    singular = np.linalg.svd(normalized, compute_uv=False)
    _, log_singular, vectors = np.linalg.svd(jacobian, full_matrices=False)
    weak = vectors[-1]
    if weak[0] < 0:
        weak = -weak
    return {
        "rows": len(jacobian),
        "column_normalized_singular_values": singular.tolist(),
        "column_normalized_condition": (
            float(singular[0] / singular[-1]) if singular[-1] > 1e-12 else None
        ),
        "log_parameter_rms_singular_values_K": (
            log_singular / np.sqrt(len(jacobian))
        ).tolist(),
        "weak_log_parameter_direction": weak.tolist(),
    }


def diagnose(directory, calibration, model, spec, bindings):
    require(interior(model, spec), "Rod diagnostic requires a bounded interior fit")
    view = load_bound_view(
        directory, calibration, "series", ["time_s", "boundary", *spec["sensors"]], spec
    )
    t, boundary = view[:, :2].T
    base = np.array([model["k_W_mK"], model["h_effective_W_m2K"]])
    n = spec["grid"]
    grids = {n: [], 2 * n: []}
    checks = []
    for direction in np.eye(2):
        offsets = [
            (base * np.exp(sign * LOG_STEP * direction)).tolist() for sign in (-1, 1)
        ]
        for grid, columns in grids.items():
            lo, hi = [predict(t, boundary, spec, *p, grid) for p in offsets]
            columns.append((hi - lo) / (2 * LOG_STEP))
        independent = []
        for p in offsets:
            sample, values, _, _ = sampled_bdf_prediction(t, boundary, spec, *p, n)
            independent.append(values)
        derivative = (independent[1] - independent[0]) / (2 * LOG_STEP)
        derivative_error = np.linalg.norm(derivative - grids[n][-1][sample])
        derivative_scale = np.linalg.norm(grids[n][-1][sample])
        refined_error = np.linalg.norm(grids[2 * n][-1] - grids[n][-1])
        refined_scale = np.linalg.norm(grids[n][-1])
        require(min(derivative_scale, refined_scale) > 0, "Vanishing rod derivative")
        checks.append(
            {
                "bdf_relative_l2_error": float(derivative_error / derivative_scale),
                "refined_grid_relative_l2_error": float(refined_error / refined_scale),
            }
        )
    require(
        all(np.isfinite(v) and v <= 0.05 for check in checks for v in check.values()),
        "Rod derivatives failed independent BDF or refined-grid verification",
    )
    jac = np.stack(grids[n], axis=-1)
    full = _spectrum(jac.reshape(-1, 2))
    fine = _spectrum(np.stack(grids[2 * n], axis=-1).reshape(-1, 2))
    require(
        full is not None and fine is not None, "Unresolved rod sensitivity spectrum"
    )
    coarse_ratio = full["column_normalized_condition"]
    fine_ratio = fine["column_normalized_condition"]
    poor = coarse_ratio is None or coarse_ratio >= CONDITION_LIMIT
    require(
        poor == (fine_ratio is None or fine_ratio >= CONDITION_LIMIT),
        "Rod identification decision changes under grid refinement",
    )
    split = t < spec["late_start"]
    return {
        "bindings": bindings,
        "method": "centered_log_parameter_differences",
        "log_step": LOG_STEP,
        "condition_limit": CONDITION_LIMIT,
        "calibration_acquisition": calibration["id"],
        "k_W_mK": float(base[0]),
        "h_effective_W_m2K": float(base[1]),
        "calibration_rmse_K": model["calibration_rmse_K"],
        "full": full,
        "refined_full": fine,
        "early": _spectrum(jac[split].reshape(-1, 2)) if np.any(split) else None,
        "late": _spectrum(jac[~split].reshape(-1, 2)) if np.any(~split) else None,
        "by_sensor": {
            key: _spectrum(jac[:, i, :]) for i, key in enumerate(spec["sensors"])
        },
        "verification": checks,
        "decision": "independent_k_and_loss_measurements_required"
        if poor
        else "local_separation_only_validate_metrology",
        "evaluation_response_accessed": False,
        "scientific_status_promoted": False,
    }
