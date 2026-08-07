from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.materials_project_acquisition_closeout_binding import (
    MaterialsProjectCloseoutBindingError,
    STRATEGIES,
    validate_strategy_comparison_binding,
)


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _prepare_suite(tmp_path: Path) -> Path:
    suite = tmp_path / "suite"
    final_mae = {
        "fixed_catalog": 0.0873,
        "random": 0.0864,
        "diversity": 0.0893,
        "uncertainty": 0.0929,
    }
    rows: list[dict[str, object]] = []
    for strategy in STRATEGIES:
        primary = {
            "model_variant": "ridge_raw",
            "seed_only_mae": 0.1117,
            "final_sequence_mae": final_mae[strategy],
            "delta_mae_final_minus_seed": final_mae[strategy] - 0.1117,
            "relative_mae_improvement_fraction": (0.1117 - final_mae[strategy]) / 0.1117,
            "improved": True,
            "seed_only_r2": -0.37,
            "final_sequence_r2": 0.01,
            "seed_only_spearman": 0.28,
            "final_sequence_spearman": 0.20,
        }
        _write_json(
            suite / "evaluations" / strategy / "evaluation_manifest.json",
            {
                "benchmark_id": "fixture-benchmark",
                "evaluation_status": "completed",
                "strategy": strategy,
                "cost_used": 100,
                "acquired_rows": 100,
                "primary_model_result": primary,
            },
        )
        rows.append(
            {
                "strategy": strategy,
                "cost_used": 100,
                "acquired_rows": 100,
                "primary_model": "ridge_raw",
                "seed_only_mae": primary["seed_only_mae"],
                "final_sequence_mae": primary["final_sequence_mae"],
                "delta_mae_final_minus_seed": primary["delta_mae_final_minus_seed"],
                "relative_mae_improvement_fraction": primary[
                    "relative_mae_improvement_fraction"
                ],
                "improved": primary["improved"],
                "final_sequence_r2": primary["final_sequence_r2"],
                "final_sequence_spearman": primary["final_sequence_spearman"],
            }
        )
    _write_json(
        suite / "strategy_comparison.json",
        {
            "benchmark_id": "fixture-benchmark",
            "primary_model": "ridge_raw",
            "lowest_locked_mae_strategy": "random",
            "strategies": rows,
        },
    )
    return suite


def test_comparison_is_bound_to_evaluation_manifests(tmp_path: Path) -> None:
    suite = _prepare_suite(tmp_path)
    result = validate_strategy_comparison_binding(suite)
    assert result["valid"] is True
    assert result["lowest_locked_mae_strategy"] == "random"
    assert result["comparison_bound_to_evaluation_manifests"] is True


def test_comparison_metric_tampering_is_rejected(tmp_path: Path) -> None:
    suite = _prepare_suite(tmp_path)
    path = suite / "strategy_comparison.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload["strategies"]:
        if row["strategy"] == "uncertainty":
            row["final_sequence_mae"] = 0.0001
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(MaterialsProjectCloseoutBindingError, match="final_sequence_mae drifted"):
        validate_strategy_comparison_binding(suite)
