"""Bounded cylindrical rod model with measured boundary temperature (SI units)."""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import eigh_tridiagonal
from scipy.optimize import least_squares
from scipy.sparse import diags

from .kernel import ResearchLoopError


class RodNumericalError(ResearchLoopError):
    """The declared numerical verification did not pass."""


def _matrices(spec, k, h, n):
    capacity = spec["density"] * spec["specific_heat"]
    diffusion = k / capacity / (spec["length"] / n) ** 2
    sink = 4 * h / (capacity * spec["diameter"])
    return diffusion, np.full(n, -2 * diffusion - sink)


def _sample(values, spec, n):
    grid = np.linspace(spec["length"] / n, spec["length"], n)
    return np.stack([np.interp(spec["positions"], grid, row) for row in values])


def predict(t, boundary, spec, k, h, n):
    """Exact semidiscrete evolution for a piecewise-linear input."""
    scale, diagonal = _matrices(spec, k, h, n)
    off = np.full(n - 1, scale)
    off[-1] *= np.sqrt(2)
    eigen, vectors = eigh_tridiagonal(diagonal, off)
    weight = np.ones(n)
    weight[-1] = np.sqrt(0.5)
    state = vectors.T @ (np.full(n, boundary[0]) * weight)
    forcing = scale * vectors[0]
    # Project eigenmodes to downstream sensor positions once.
    projected = _sample((vectors / weight[:, None]).T, spec, n).T
    out = [projected @ state]
    cache = {}
    for i, dt in enumerate(np.diff(t)):
        dt = round(float(dt), 12)
        if dt not in cache:
            u = np.expm1(eigen * dt)
            first = u / eigen
            cache[dt] = (1 + u, forcing * first, forcing * (first / dt - 1) / eigen)
        decay, constant, linear = cache[dt]
        state = (
            decay * state
            + constant * boundary[i]
            + linear * (boundary[i + 1] - boundary[i])
        )
        out.append(projected @ state)
    return np.asarray(out)


def sampled_bdf_prediction(t, boundary, spec, k, h, n):
    """Independent integrator evaluated at deterministic time samples."""
    scale, diagonal = _matrices(spec, k, h, n)
    lower = np.full(n - 1, scale)
    lower[-1] *= 2
    matrix = diags([lower, diagonal, np.full(n - 1, scale)], [-1, 0, 1], format="csc")

    def rhs(time, y):
        derivative = matrix @ y
        derivative[0] += scale * np.interp(time, t, boundary)
        return derivative

    sample = np.unique(
        np.r_[np.linspace(0, len(t) - 1, min(101, len(t)), dtype=int), len(t) - 1]
    )
    ode = solve_ivp(
        rhs,
        (t[0], t[-1]),
        np.full(n, boundary[0]),
        t_eval=t[sample],
        method="BDF",
        rtol=1e-7,
        atol=1e-7,
        jac=matrix,
    )
    if not ode.success:
        raise RodNumericalError("Independent BDF solver failed")
    return sample, _sample(ode.y.T, spec, n), matrix, scale


def verify_prediction(t, boundary, spec, k, h, n, predicted):
    sample, independent, matrix, scale = sampled_bdf_prediction(
        t, boundary, spec, k, h, n
    )
    integration = float(np.max(abs(independent - predicted[sample])))
    coarse = predict(t, boundary, spec, k, h, n // 2)
    refined = predict(t, boundary, spec, k, h, n * 2)
    spatial = float(np.max(abs(refined - predicted)))
    # Direct discrete steady solve compared to the analytical finite-fin profile.
    steady = -np.linalg.solve(matrix.toarray(), np.r_[scale, np.zeros(n - 1)])
    m = np.sqrt(4 * h / (k * spec["diameter"]))
    x = np.asarray(spec["positions"])
    # Stable form of cosh(m (L-x))/cosh(mL).
    analytic = (np.exp(-m * x) + np.exp(-m * (2 * spec["length"] - x))) / (
        1 + np.exp(-2 * m * spec["length"])
    )
    steady_error = float(np.max(abs(_sample(steady[None, :], spec, n)[0] - analytic)))
    errors = {
        "refined_grid_K": spatial,
        "coarse_grid_K": float(np.max(abs(coarse - predicted))),
        "bdf_K": integration,
        "steady_normalized": steady_error,
    }
    if (
        not all(np.isfinite(list(errors.values())))
        or spatial > spec["grid_tol"]
        or integration > spec["bdf_tol"]
        or steady_error > 0.002
    ):
        raise RodNumericalError(f"Rod numerical tolerance exceeded: {errors}")
    return errors


def calibrate(data, spec):
    t, boundary, observed = data[:, 0], data[:, 1], data[:, 2:]
    models = {}
    for name, loss in (("conduction", False), ("distributed_loss", True)):
        low = [spec["k_bounds"][0]] + ([0.0] if loss else [])
        high = [spec["k_bounds"][1]] + ([spec["h_max"]] if loss else [])

        def residual(parameters, apply_loss=loss):
            k = parameters[0]
            h = parameters[1] if apply_loss else 0.0
            return (predict(t, boundary, spec, k, h, spec["grid"]) - observed).ravel()

        fits = [
            least_squares(
                residual,
                np.asarray(low) + f * (np.asarray(high) - low),
                bounds=(low, high),
                ftol=1e-10,
                xtol=1e-9,
                max_nfev=60,
            )
            for f in (0.25, 0.75)
        ]
        chosen = min(fits, key=lambda result: result.cost)
        if any(
            not result.success or result.cost - chosen.cost > 0.01 for result in fits
        ):
            raise RodNumericalError(
                "Rod fit did not converge consistently from both starts"
            )
        k, h = float(chosen.x[0]), float(chosen.x[1]) if loss else 0.0
        prediction = predict(t, boundary, spec, k, h, spec["grid"])
        jac = chosen.jac
        norms = np.linalg.norm(jac, axis=0)
        if np.any(norms <= np.finfo(float).eps):
            raise RodNumericalError("Rod fit has a numerically zero sensitivity column")
        singular = np.linalg.svd(jac / norms, compute_uv=False)
        models[name] = {
            "k_W_mK": k,
            "h_effective_W_m2K": h,
            "calibration_rmse_K": float(np.sqrt(np.mean(chosen.fun**2))),
            "active_bounds": chosen.active_mask.tolist(),
            "normalized_sensitivity_singular_values": singular.tolist(),
            "k_h_sensitivity_cosine": float(
                jac[:, 0] @ jac[:, 1] / (norms[0] * norms[1])
            )
            if loss
            else None,
            "numerical_checks": verify_prediction(
                t, boundary, spec, k, h, spec["grid"], prediction
            ),
        }
    return models
