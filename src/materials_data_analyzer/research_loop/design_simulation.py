"""Response-free structural simulation for two-factor experimental designs.

The simulator evaluates only design-matrix structure. It never synthesizes or consumes
response values, estimates coefficients/effect sizes, performs optimization, or grants
causal/predictive claims. It is intended to answer a narrower question: which model
terms become structurally estimable after a proposed set of process conditions and
replicates is added?
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .kernel import ResearchLoopError

DESIGN_SIMULATION_SCHEMA_VERSION = "1.0"
DESIGN_SIMULATION_POLICY_VERSION = "1.0"

_ALLOWED_MODELS = ("intercept", "main_effects", "interaction", "quadratic")
_PARAMETER_COUNTS = {
    "intercept": 1,
    "main_effects": 3,
    "interaction": 4,
    "quadratic": 6,
}


class DesignSimulationError(ResearchLoopError):
    """Raised when a structural design-simulation contract is invalid."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DesignSimulationError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _parse_json_bytes(raw_bytes: bytes, path: Path) -> dict[str, Any]:
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DesignSimulationError(f"invalid UTF-8 in {path}: {exc}") from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise DesignSimulationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DesignSimulationError(f"JSON root must be an object: {path}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    return _parse_json_bytes(path.read_bytes(), path)


def _load_json_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    """Read one immutable byte snapshot and derive both JSON and SHA-256 from it."""
    raw_bytes = path.read_bytes()
    return _parse_json_bytes(raw_bytes, path), hashlib.sha256(raw_bytes).hexdigest()


def _exact_object(
    value: object,
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DesignSimulationError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise DesignSimulationError(f"{field} is missing required keys: {', '.join(missing)}")
    if unknown:
        raise DesignSimulationError(f"{field} has unknown keys: {', '.join(unknown)}")
    return value


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DesignSimulationError(f"{field} must be a non-empty string")
    return value.strip()


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DesignSimulationError(f"{field} must be a finite numeric value")
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as exc:
        raise DesignSimulationError(f"{field} must be representable as a finite float") from exc
    if not math.isfinite(numeric):
        raise DesignSimulationError(f"{field} must be finite")
    return numeric


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DesignSimulationError(f"{field} must be a positive integer")
    return value


def _factor_contract(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) != 2:
        raise DesignSimulationError("factors must contain exactly two factor definitions")
    factors: list[dict[str, str]] = []
    names: set[str] = set()
    for index, raw in enumerate(value):
        item = _exact_object(
            raw,
            required={"name", "unit"},
            allowed={"name", "unit"},
            field=f"factors[{index}]",
        )
        name = _nonempty_text(item["name"], f"factors[{index}].name")
        unit = _nonempty_text(item["unit"], f"factors[{index}].unit")
        if name in names:
            raise DesignSimulationError(f"duplicate factor name: {name}")
        names.add(name)
        factors.append({"name": name, "unit": unit})
    return factors


def _cell_contract(
    value: object,
    *,
    field: str,
    factor_names: tuple[str, str],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise DesignSimulationError(f"{field} must be a list")
    cells: list[dict[str, Any]] = []
    ids: set[str] = set()
    coordinates: set[tuple[float, float]] = set()
    for index, raw in enumerate(value):
        item = _exact_object(
            raw,
            required={"cell_id", "factor_values", "replicates"},
            allowed={"cell_id", "factor_values", "replicates"},
            field=f"{field}[{index}]",
        )
        cell_id = _nonempty_text(item["cell_id"], f"{field}[{index}].cell_id")
        if cell_id in ids:
            raise DesignSimulationError(f"duplicate cell_id in {field}: {cell_id}")
        ids.add(cell_id)
        factor_values = _exact_object(
            item["factor_values"],
            required=set(factor_names),
            allowed=set(factor_names),
            field=f"{field}[{index}].factor_values",
        )
        values = tuple(
            _finite_number(
                factor_values[name], f"{field}[{index}].factor_values.{name}"
            )
            for name in factor_names
        )
        if values in coordinates:
            raise DesignSimulationError(
                f"duplicate factor-value cell in {field}: {values}"
            )
        coordinates.add(values)
        cells.append(
            {
                "cell_id": cell_id,
                "factor_values": {
                    factor_names[0]: values[0],
                    factor_names[1]: values[1],
                },
                "replicates": _positive_int(
                    item["replicates"], f"{field}[{index}].replicates"
                ),
            }
        )
    return cells


def validate_design_simulation_config(value: object) -> dict[str, Any]:
    """Validate a response-free two-factor design-simulation specification."""
    root = _exact_object(
        value,
        required={
            "schema_version",
            "simulation_id",
            "research_question",
            "factors",
            "observed_cells",
            "proposed_cells",
            "models",
            "scientific_boundary",
        },
        allowed={
            "schema_version",
            "simulation_id",
            "research_question",
            "factors",
            "observed_cells",
            "proposed_cells",
            "models",
            "scientific_boundary",
            "metadata",
        },
        field="design simulation",
    )
    if root["schema_version"] != DESIGN_SIMULATION_SCHEMA_VERSION:
        raise DesignSimulationError(
            f"unsupported schema_version: {root['schema_version']!r}"
        )
    factors = _factor_contract(root["factors"])
    factor_names = (factors[0]["name"], factors[1]["name"])
    observed = _cell_contract(
        root["observed_cells"], field="observed_cells", factor_names=factor_names
    )
    if not observed:
        raise DesignSimulationError("observed_cells must not be empty")
    proposed = _cell_contract(
        root["proposed_cells"], field="proposed_cells", factor_names=factor_names
    )

    models = root["models"]
    if not isinstance(models, list) or not models:
        raise DesignSimulationError("models must be a non-empty list")
    normalized_models: list[str] = []
    for index, raw in enumerate(models):
        model = _nonempty_text(raw, f"models[{index}]")
        if model not in _ALLOWED_MODELS:
            raise DesignSimulationError(
                f"unsupported model {model!r}; allowed={list(_ALLOWED_MODELS)}"
            )
        if model in normalized_models:
            raise DesignSimulationError(f"duplicate model: {model}")
        normalized_models.append(model)

    boundary = _exact_object(
        root["scientific_boundary"],
        required={
            "response_values_allowed",
            "coefficient_estimation_allowed",
            "effect_size_estimation_allowed",
            "predictive_modeling_allowed",
            "causal_inference_allowed",
            "optimization_allowed",
            "engineering_decision_allowed",
        },
        allowed={
            "response_values_allowed",
            "coefficient_estimation_allowed",
            "effect_size_estimation_allowed",
            "predictive_modeling_allowed",
            "causal_inference_allowed",
            "optimization_allowed",
            "engineering_decision_allowed",
        },
        field="scientific_boundary",
    )
    for key, flag in boundary.items():
        if flag is not False:
            raise DesignSimulationError(
                f"structural design simulation requires {key}=false"
            )

    observed_coords = {
        tuple(cell["factor_values"][name] for name in factor_names) for cell in observed
    }
    proposed_coords = {
        tuple(cell["factor_values"][name] for name in factor_names) for cell in proposed
    }
    overlap = observed_coords & proposed_coords

    normalized: dict[str, Any] = {
        "schema_version": DESIGN_SIMULATION_SCHEMA_VERSION,
        "simulation_id": _nonempty_text(root["simulation_id"], "simulation_id"),
        "research_question": _nonempty_text(
            root["research_question"], "research_question"
        ),
        "factors": factors,
        "observed_cells": observed,
        "proposed_cells": proposed,
        "models": normalized_models,
        "scientific_boundary": dict(boundary),
        "proposal_overlap_with_observed_cells": [
            {factor_names[0]: values[0], factor_names[1]: values[1]}
            for values in sorted(overlap)
        ],
    }
    if "metadata" in root:
        if not isinstance(root["metadata"], dict):
            raise DesignSimulationError("metadata must be an object")
        normalized["metadata"] = root["metadata"]
    return normalized


def _unique_cell_rows(
    cells: list[Mapping[str, Any]], factor_names: tuple[str, str]
) -> np.ndarray:
    """Return one row per unique process cell; replicate multiplicity cannot change rank."""
    rows = [
        [
            float(cell["factor_values"][factor_names[0]]),
            float(cell["factor_values"][factor_names[1]]),
        ]
        for cell in cells
    ]
    return np.asarray(rows, dtype=float)


def _total_replicates(cells: list[Mapping[str, Any]]) -> int:
    return sum(int(cell["replicates"]) for cell in cells)


def _standardized_factors(rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if rows.ndim != 2 or rows.shape[1] != 2 or rows.shape[0] == 0:
        raise DesignSimulationError("design cell rows must have shape n x 2")
    standardized: list[np.ndarray] = []
    for column_index in range(2):
        column = rows[:, column_index]
        center = float(np.mean(column))
        scale = float(np.std(column))
        if scale == 0.0:
            standardized.append(column - center)
        else:
            standardized.append((column - center) / scale)
    return standardized[0], standardized[1]


def _design_matrix(rows: np.ndarray, model: str) -> np.ndarray:
    x1, x2 = _standardized_factors(rows)
    intercept = np.ones(rows.shape[0], dtype=float)
    if model == "intercept":
        return np.column_stack([intercept])
    if model == "main_effects":
        return np.column_stack([intercept, x1, x2])
    if model == "interaction":
        return np.column_stack([intercept, x1, x2, x1 * x2])
    if model == "quadratic":
        return np.column_stack([intercept, x1, x2, x1 * x2, x1 * x1, x2 * x2])
    raise DesignSimulationError(f"unsupported model: {model}")


def _model_summary(
    rows: np.ndarray,
    model: str,
    *,
    total_replicates: int,
) -> dict[str, Any]:
    matrix = _design_matrix(rows, model)
    rank = int(np.linalg.matrix_rank(matrix))
    parameters = _PARAMETER_COUNTS[model]
    return {
        "model": model,
        "n_rows": total_replicates,
        "parameter_count": parameters,
        "matrix_rank": rank,
        "full_column_rank": rank == parameters,
        "residual_degrees_of_freedom": total_replicates - rank,
    }


def _grid_summary(
    cells: list[Mapping[str, Any]], factor_names: tuple[str, str]
) -> dict[str, Any]:
    coordinates = {
        tuple(float(cell["factor_values"][name]) for name in factor_names)
        for cell in cells
    }
    levels_1 = sorted({values[0] for values in coordinates})
    levels_2 = sorted({values[1] for values in coordinates})
    complete = {(v1, v2) for v1 in levels_1 for v2 in levels_2}
    missing = sorted(complete - coordinates)
    return {
        "factor_levels": {
            factor_names[0]: levels_1,
            factor_names[1]: levels_2,
        },
        "unique_cell_count": len(coordinates),
        "possible_observed_level_cell_count": len(complete),
        "observed_level_grid_complete": not missing,
        "missing_observed_level_cells": [
            {factor_names[0]: values[0], factor_names[1]: values[1]}
            for values in missing
        ],
        "total_replicates": _total_replicates(cells),
    }


def simulate_design_structure(config: object) -> dict[str, Any]:
    """Compare observed versus proposed+observed structural estimability."""
    validated = validate_design_simulation_config(config)
    factor_names = (
        validated["factors"][0]["name"],
        validated["factors"][1]["name"],
    )
    observed_cells = validated["observed_cells"]
    proposed_cells = validated["proposed_cells"]

    # A proposed cell that duplicates an observed coordinate is a replication-only addition.
    # Merge by coordinate so duplicate coordinates remain one structural design cell while
    # replicate multiplicity contributes only to residual degrees of freedom.
    merged: dict[tuple[float, float], dict[str, Any]] = {}
    for source, cells in (("observed", observed_cells), ("proposed", proposed_cells)):
        for cell in cells:
            coordinate = tuple(
                float(cell["factor_values"][name]) for name in factor_names
            )
            if coordinate not in merged:
                merged[coordinate] = {
                    "cell_id": cell["cell_id"],
                    "factor_values": dict(cell["factor_values"]),
                    "replicates": int(cell["replicates"]),
                    "sources": [source],
                }
            else:
                merged[coordinate]["replicates"] += int(cell["replicates"])
                merged[coordinate]["sources"].append(source)
    after_merged = list(merged.values())

    before_rows = _unique_cell_rows(observed_cells, factor_names)
    after_rows = _unique_cell_rows(after_merged, factor_names)
    before_total_replicates = _total_replicates(observed_cells)
    after_total_replicates = _total_replicates(after_merged)
    before_models = {
        model: _model_summary(
            before_rows,
            model,
            total_replicates=before_total_replicates,
        )
        for model in validated["models"]
    }
    after_models = {
        model: _model_summary(
            after_rows,
            model,
            total_replicates=after_total_replicates,
        )
        for model in validated["models"]
    }
    comparisons: list[dict[str, Any]] = []
    for model in validated["models"]:
        before = before_models[model]
        after = after_models[model]
        comparisons.append(
            {
                "model": model,
                "rank_before": before["matrix_rank"],
                "rank_after": after["matrix_rank"],
                "rank_gain": after["matrix_rank"] - before["matrix_rank"],
                "residual_df_before": before["residual_degrees_of_freedom"],
                "residual_df_after": after["residual_degrees_of_freedom"],
                "residual_df_gain": (
                    after["residual_degrees_of_freedom"]
                    - before["residual_degrees_of_freedom"]
                ),
                "full_column_rank_before": before["full_column_rank"],
                "full_column_rank_after": after["full_column_rank"],
            }
        )

    before_coords = {
        tuple(float(cell["factor_values"][name]) for name in factor_names)
        for cell in observed_cells
    }
    proposed_coords = {
        tuple(float(cell["factor_values"][name]) for name in factor_names)
        for cell in proposed_cells
    }
    new_coords = proposed_coords - before_coords
    overlap_coords = proposed_coords & before_coords

    return {
        "schema_version": DESIGN_SIMULATION_SCHEMA_VERSION,
        "design_simulation_policy_version": DESIGN_SIMULATION_POLICY_VERSION,
        "simulation_id": validated["simulation_id"],
        "research_question": validated["research_question"],
        "factors": validated["factors"],
        "before": {
            "grid": _grid_summary(observed_cells, factor_names),
            "models": [before_models[model] for model in validated["models"]],
        },
        "after_proposal": {
            "grid": _grid_summary(after_merged, factor_names),
            "models": [after_models[model] for model in validated["models"]],
        },
        "comparison": {
            "new_unique_cell_count": len(new_coords),
            "replication_only_cell_count": len(overlap_coords),
            "new_replicate_count": _total_replicates(proposed_cells),
            "model_changes": comparisons,
        },
        "expected_information_gain": {
            "status": "not_quantified",
            "value": None,
            "reason": (
                "Rank gain and residual degrees of freedom describe design structure; "
                "they are not a probabilistic expected-information-gain estimate."
            ),
        },
        "scientific_boundary": {
            **validated["scientific_boundary"],
            "response_values_used": False,
            "synthetic_response_generated": False,
            "coefficients_estimated": False,
            "effect_sizes_estimated": False,
            "predictions_generated": False,
            "causal_effects_inferred": False,
            "optimization_performed": False,
            "engineering_decision_made": False,
        },
    }


def simulate_design_structure_file(path: str | Path) -> dict[str, Any]:
    """Load one strict JSON design and bind the exact specification bytes."""
    resolved = Path(path).expanduser().resolve(strict=True)
    config, snapshot_sha256 = _load_json_snapshot(resolved)
    result = simulate_design_structure(config)
    return {
        **result,
        "simulation_spec_binding": {
            "path": str(resolved),
            "sha256": snapshot_sha256,
        },
    }


__all__ = [
    "DESIGN_SIMULATION_POLICY_VERSION",
    "DESIGN_SIMULATION_SCHEMA_VERSION",
    "DesignSimulationError",
    "simulate_design_structure",
    "simulate_design_structure_file",
    "validate_design_simulation_config",
]
