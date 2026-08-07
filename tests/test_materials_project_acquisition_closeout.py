from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from materials_data_analyzer.research_loop.materials_project_acquisition_closeout import (
    MaterialsProjectAcquisitionCloseoutError,
    STRATEGIES,
    audit_materials_project_acquisition_suite,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _prepare(tmp_path: Path) -> tuple[Path, Path, Path]:
    benchmark = tmp_path / "benchmark"
    suite = tmp_path / "suite"
    output = tmp_path / "closeout"
    config = tmp_path / "benchmark_config.json"
    benchmark.mkdir()
    (benchmark / "planner").mkdir()

    seed = pd.DataFrame(
        {
            "material_id": ["seed-1", "seed-2"],
            "chemical_system_group": ["Seed-A", "Seed-B"],
            "reduced_formula_group": ["S1", "S2"],
            "feature_a": [0.0, 1.0],
            "energy_above_hull": [0.01, 0.02],
        }
    )
    seed_path = benchmark / "planner" / "seed_evidence.csv"
    seed.to_csv(seed_path, index=False)
    _write_json(
        config,
        {
            "benchmark_id": "fixture-benchmark",
            "identifier_column": "material_id",
            "target_column": "energy_above_hull",
        },
    )
    _write_json(
        benchmark / "benchmark_manifest.json",
        {
            "benchmark_id": "fixture-benchmark",
            "outputs": {"seed_evidence": "planner/seed_evidence.csv"},
            "output_sha256": {"seed_evidence": _sha(seed_path)},
        },
    )

    final_mae = {
        "fixed_catalog": 0.0873,
        "random": 0.0864,
        "diversity": 0.0893,
        "uncertainty": 0.0929,
    }
    final_r2 = {
        "fixed_catalog": 0.024,
        "random": -0.032,
        "diversity": 0.029,
        "uncertainty": -0.005,
    }
    final_spearman = {
        "fixed_catalog": 0.21,
        "random": 0.17,
        "diversity": 0.29,
        "uncertainty": 0.20,
    }
    comparison_rows: list[dict[str, object]] = []
    for index, strategy in enumerate(STRATEGIES):
        sequence = suite / "sequences" / strategy
        evaluation = suite / "evaluations" / strategy
        sequence.mkdir(parents=True)
        evaluation.mkdir(parents=True)
        history = pd.DataFrame(
            {
                "step": [1, 2],
                "strategy": [strategy, strategy],
                "selected_group": [f"{strategy}-G1", f"{strategy}-G2"],
                "acquired_rows": [1, 1],
                "step_cost": [1, 1],
                "cumulative_cost": [1, 2],
                "remaining_budget": [1, 0],
                "selection_score": [float(index + 1), float(index + 2)],
                "selection_reason": ["fixture", "fixture"],
            }
        )
        training = pd.concat(
            [
                seed,
                pd.DataFrame(
                    {
                        "material_id": [f"{strategy}-1", f"{strategy}-2"],
                        "chemical_system_group": [f"{strategy}-G1", f"{strategy}-G2"],
                        "reduced_formula_group": [f"{strategy}-F1", f"{strategy}-F2"],
                        "feature_a": [2.0, 3.0],
                        "energy_above_hull": [0.03 + index * 0.01, 0.04 + index * 0.01],
                    }
                ),
            ],
            ignore_index=True,
        )
        history_path = sequence / "acquisition_history.csv"
        training_path = sequence / "training_evidence.csv"
        history.to_csv(history_path, index=False)
        training.to_csv(training_path, index=False)
        sequence_manifest = {
            "execution_status": "completed",
            "strategy": strategy,
            "counts": {"acquired_rows": 2, "cost_used": 2},
            "planner_boundary": {"locked_test_content_read": False},
            "outputs": {
                "training_evidence": "training_evidence.csv",
                "acquisition_history": "acquisition_history.csv",
            },
            "output_sha256": {
                "training_evidence": _sha(training_path),
                "acquisition_history": _sha(history_path),
            },
        }
        _write_json(sequence / "sequence_manifest.json", sequence_manifest)

        metrics = pd.DataFrame(
            [
                {
                    "training_scope": "final_sequence",
                    "model_variant": "dummy_median",
                    "mae": 0.10,
                    "r2": -0.10,
                    "spearman": float("nan"),
                },
                {
                    "training_scope": "final_sequence",
                    "model_variant": "ridge_raw",
                    "mae": final_mae[strategy],
                    "r2": final_r2[strategy],
                    "spearman": final_spearman[strategy],
                },
            ]
        )
        metrics_path = evaluation / "locked_metrics.csv"
        metrics.to_csv(metrics_path, index=False)
        evaluation_manifest = {
            "evaluation_status": "completed",
            "strategy": strategy,
            "sequence_manifest_sha256": _sha(sequence / "sequence_manifest.json"),
            "cost_used": 2,
            "locked_test_sha256": "a" * 64,
            "primary_model_result": {"model_variant": "ridge_raw"},
            "locked_boundary": {
                "sequence_completed_before_locked_read": True,
                "locked_metrics_not_available_to_sequence": True,
                "primary_model_predeclared": True,
            },
            "outputs": {"locked_metrics": "locked_metrics.csv"},
            "output_sha256": {"locked_metrics": _sha(metrics_path)},
        }
        _write_json(evaluation / "evaluation_manifest.json", evaluation_manifest)

        comparison_rows.append(
            {
                "strategy": strategy,
                "cost_used": 2,
                "acquired_rows": 2,
                "primary_model": "ridge_raw",
                "seed_only_mae": 0.1117,
                "final_sequence_mae": final_mae[strategy],
                "delta_mae_final_minus_seed": final_mae[strategy] - 0.1117,
                "relative_mae_improvement_fraction": (0.1117 - final_mae[strategy]) / 0.1117,
                "improved": True,
                "final_sequence_r2": final_r2[strategy],
                "final_sequence_spearman": final_spearman[strategy],
            }
        )
    _write_json(
        suite / "strategy_comparison.json",
        {
            "benchmark_id": "fixture-benchmark",
            "primary_model": "ridge_raw",
            "lowest_locked_mae_strategy": "random",
            "strategies": comparison_rows,
        },
    )
    return suite, benchmark, config


def test_closeout_preserves_negative_adaptive_result(tmp_path: Path) -> None:
    suite, benchmark, config = _prepare(tmp_path)
    output = tmp_path / "closeout"
    result = audit_materials_project_acquisition_suite(
        suite_root=suite,
        benchmark_dir=benchmark,
        benchmark_config_path=config,
        output_dir=output,
    )

    assert result["execution_status"] == "benchmark_v1_closed_out"
    assert result["observed_result"]["lowest_locked_mae_strategy"] == "random"
    assert result["observed_result"]["all_strategies_improved_primary_mae_vs_seed"] is True
    assert result["observed_result"]["uncertainty_outperformed_fixed_and_random_on_primary_mae"] is False
    assert result["scientific_closeout"]["additional_label_evidence_benefit"] == "Diagnostic"
    assert result["scientific_closeout"]["adaptive_uncertainty_policy_superiority"] == "Unsupported"
    assert result["policy_boundary"]["benchmark_v1_strategy_retuning_authorized"] is False
    assert (output / "benchmark_closeout.json").is_file()
    assert (output / "planner_strategy_diagnostics.csv").is_file()
    assert (output / "locked_model_diagnostics.csv").is_file()
    assert (output / "selected_group_overlap.csv").is_file()


def test_closeout_rejects_tampered_sequence_output(tmp_path: Path) -> None:
    suite, benchmark, config = _prepare(tmp_path)
    history = suite / "sequences" / "uncertainty" / "acquisition_history.csv"
    history.write_text(history.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(MaterialsProjectAcquisitionCloseoutError, match="checksum mismatch"):
        audit_materials_project_acquisition_suite(
            suite_root=suite,
            benchmark_dir=benchmark,
            benchmark_config_path=config,
            output_dir=tmp_path / "closeout",
        )


def test_closeout_rejects_output_inside_frozen_suite(tmp_path: Path) -> None:
    suite, benchmark, config = _prepare(tmp_path)
    with pytest.raises(MaterialsProjectAcquisitionCloseoutError, match="must not mutate"):
        audit_materials_project_acquisition_suite(
            suite_root=suite,
            benchmark_dir=benchmark,
            benchmark_config_path=config,
            output_dir=suite / "closeout",
        )
