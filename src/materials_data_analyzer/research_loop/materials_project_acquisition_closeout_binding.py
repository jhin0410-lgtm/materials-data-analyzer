"""Integrity binding for Materials Project acquisition suite comparison output."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


STRATEGIES = ("fixed_catalog", "random", "diversity", "uncertainty")


class MaterialsProjectCloseoutBindingError(ValueError):
    """Raised when strategy comparison no longer matches frozen evaluations."""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MaterialsProjectCloseoutBindingError(f"JSON root must be an object: {path}")
    return value


def _same_float(left: Any, right: Any) -> bool:
    a = float(left)
    b = float(right)
    if math.isnan(a) and math.isnan(b):
        return True
    return math.isclose(a, b, rel_tol=0.0, abs_tol=1e-15)


def validate_strategy_comparison_binding(suite_root: str | Path) -> dict[str, Any]:
    """Require strategy_comparison.json to exactly reflect frozen evaluation manifests."""
    root = Path(suite_root).expanduser().resolve(strict=True)
    comparison = _load(root / "strategy_comparison.json")
    rows = comparison.get("strategies")
    if not isinstance(rows, list):
        raise MaterialsProjectCloseoutBindingError("comparison strategies must be a list")
    by_strategy = {
        str(row.get("strategy")): row
        for row in rows
        if isinstance(row, dict)
    }
    if set(by_strategy) != set(STRATEGIES) or len(rows) != len(STRATEGIES):
        raise MaterialsProjectCloseoutBindingError("comparison strategy inventory drifted")

    expected_primary: set[str] = set()
    expected_benchmark: set[str] = set()
    expected_best: list[tuple[float, int, str]] = []
    float_fields = (
        "seed_only_mae",
        "final_sequence_mae",
        "delta_mae_final_minus_seed",
        "relative_mae_improvement_fraction",
        "final_sequence_r2",
        "final_sequence_spearman",
    )
    for strategy in STRATEGIES:
        manifest = _load(root / "evaluations" / strategy / "evaluation_manifest.json")
        if manifest.get("evaluation_status") != "completed" or manifest.get("strategy") != strategy:
            raise MaterialsProjectCloseoutBindingError(
                f"evaluation manifest is not completed for {strategy}"
            )
        primary = manifest.get("primary_model_result")
        if not isinstance(primary, dict):
            raise MaterialsProjectCloseoutBindingError(
                f"primary model result missing for {strategy}"
            )
        row = by_strategy[strategy]
        expected_primary.add(str(primary.get("model_variant")))
        expected_benchmark.add(str(manifest.get("benchmark_id")))
        if int(row.get("cost_used")) != int(manifest.get("cost_used")):
            raise MaterialsProjectCloseoutBindingError(f"comparison cost drifted for {strategy}")
        if int(row.get("acquired_rows")) != int(manifest.get("acquired_rows")):
            raise MaterialsProjectCloseoutBindingError(
                f"comparison acquired_rows drifted for {strategy}"
            )
        if str(row.get("primary_model")) != str(primary.get("model_variant")):
            raise MaterialsProjectCloseoutBindingError(
                f"comparison primary model drifted for {strategy}"
            )
        if bool(row.get("improved")) is not bool(primary.get("improved")):
            raise MaterialsProjectCloseoutBindingError(
                f"comparison improved flag drifted for {strategy}"
            )
        for field in float_fields:
            primary_field = field
            if not _same_float(row.get(field), primary.get(primary_field)):
                raise MaterialsProjectCloseoutBindingError(
                    f"comparison {field} drifted for {strategy}"
                )
        expected_best.append(
            (float(primary["final_sequence_mae"]), int(manifest["cost_used"]), strategy)
        )

    if len(expected_primary) != 1 or comparison.get("primary_model") != next(iter(expected_primary)):
        raise MaterialsProjectCloseoutBindingError("comparison primary model inventory drifted")
    if len(expected_benchmark) != 1 or comparison.get("benchmark_id") != next(iter(expected_benchmark)):
        raise MaterialsProjectCloseoutBindingError("comparison benchmark id drifted")
    expected_best_strategy = min(expected_best)[2]
    if comparison.get("lowest_locked_mae_strategy") != expected_best_strategy:
        raise MaterialsProjectCloseoutBindingError("comparison best-strategy label drifted")
    return {
        "valid": True,
        "benchmark_id": next(iter(expected_benchmark)),
        "primary_model": next(iter(expected_primary)),
        "strategy_count": len(STRATEGIES),
        "lowest_locked_mae_strategy": expected_best_strategy,
        "comparison_bound_to_evaluation_manifests": True,
    }
