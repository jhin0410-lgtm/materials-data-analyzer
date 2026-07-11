"""Tests for Materials Project v1.3.5 trust-boundary orchestration."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from scripts.run_materials_project_v1_3_trust_analysis import (
    assign_target_strata,
    build_model_eligibility,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_synthetic_trust_inputs(tmp_path: Path) -> dict[str, Path]:
    analysis = pd.DataFrame(
        {
            "material_id": [f"mp-{idx:03d}" for idx in range(8)],
            "formula_pretty": [f"F{idx // 2}" for idx in range(8)],
            "reduced_formula_group": [f"F{idx // 2}" for idx in range(8)],
            "chemical_system_group": ["A-B", "A-B", "A-C", "A-C", "B-C", "B-C", "C-D", "C-D"],
            "feature_a": [0.0, 0.1, 1.0, 1.1, 2.0, 2.1, 9.0, 9.2],
            "feature_b": [0.0, 0.1, 1.0, 1.1, 2.0, 2.1, 9.0, 9.2],
            "energy_above_hull": [0.0, 0.01, 0.02, 0.04, 0.10, 0.12, 1.0, 1.2],
            "theoretical": [False, False, True, True, False, True, False, True],
        }
    )
    predictions = pd.DataFrame(
        [
            {
                "split_strategy": "random",
                "split_index": 0,
                "model_variant": model,
                "material_id": material_id,
                "reduced_formula_group": formula,
                "chemical_system_group": chemsys,
                "theoretical": theoretical,
                "actual_target": target,
                "raw_prediction": pred,
                "constrained_prediction": max(pred, 0.0),
                "absolute_error": abs(target - max(pred, 0.0)),
                "negative_prediction": pred < 0,
                "descriptor_seen_in_train": False,
                "formula_seen_in_train": False,
                "chemical_system_seen_in_train": False,
                "ambiguity_group_status": "ambiguous_formula_group",
            }
            for model, pred_offset in [("dummy_median", 0.05), ("ridge_log1p", 0.02)]
            for material_id, formula, chemsys, theoretical, target, pred in [
                ("mp-006", "F3", "C-D", False, 1.0, 1.0 + pred_offset),
                ("mp-007", "F3", "C-D", True, 1.2, 1.2 + pred_offset),
            ]
        ]
    )
    metrics = pd.DataFrame(
        [
            {
                "split_strategy": "random",
                "split_index": 0,
                "model_variant": "dummy_median",
                "status": "valid",
                "mae": 0.40,
                "median_absolute_error": 0.40,
                "r2": -0.2,
                "spearman": 0.0,
            },
            {
                "split_strategy": "random",
                "split_index": 0,
                "model_variant": "ridge_log1p",
                "status": "valid",
                "mae": 0.02,
                "median_absolute_error": 0.02,
                "r2": 0.1,
                "spearman": 1.0,
            },
        ]
    )
    comparison = pd.DataFrame(
        [
            {"strategy": strategy, "model_variant": model, "metric": metric, "median": value}
            for strategy in ["random", "reduced_formula_group", "chemical_system_group"]
            for model, metric, value in [
                ("dummy_median", "r2", -0.1),
                ("dummy_median", "spearman", 0.0),
                ("ridge_log1p", "r2", 0.01 if strategy != "random" else 0.1),
                ("ridge_log1p", "spearman", 0.2),
            ]
        ]
    )
    screening = pd.DataFrame(
        [
            {
                "strategy": strategy,
                "model_variant": model,
                "metric": "precision_at_10pct",
                "median": value,
            }
            for strategy in ["random", "reduced_formula_group", "chemical_system_group"]
            for model, value in [("dummy_median", 0.5), ("ridge_log1p", 0.6)]
        ]
    )
    split = pd.DataFrame(
        [
            {
                "split_strategy": "random",
                "split_index": 0,
                "split_status": "valid",
                "descriptor_vector_overlap_count": 0,
            }
        ]
    )
    inventory = pd.DataFrame(
        [
            {"column_name": "feature_a", "primary_feature": True},
            {"column_name": "feature_b", "primary_feature": True},
            {"column_name": "material_id", "primary_feature": False},
        ]
    )
    ambiguity = pd.DataFrame(
        [
            {"reduced_formula_group": "F0", "row_count": 2, "ambiguity_flag": True},
            {"reduced_formula_group": "F1", "row_count": 2, "ambiguity_flag": True},
            {"reduced_formula_group": "F2", "row_count": 2, "ambiguity_flag": True},
            {"reduced_formula_group": "F3", "row_count": 2, "ambiguity_flag": True},
        ]
    )
    validation_spec = {
        "identifier_column": "material_id",
        "target_column": "energy_above_hull",
        "feature_columns": ["feature_a", "feature_b"],
    }
    trust_spec = {"applicability_domain_method": {"k_neighbors": 2}}

    paths = {
        "analysis": tmp_path / "analysis.csv",
        "predictions": tmp_path / "predictions.csv",
        "metrics": tmp_path / "metrics.csv",
        "comparison": tmp_path / "comparison.csv",
        "screening": tmp_path / "screening.csv",
        "split": tmp_path / "split.csv",
        "inventory": tmp_path / "inventory.csv",
        "ambiguity": tmp_path / "ambiguity.csv",
        "validation_spec": tmp_path / "validation_spec.json",
        "trust_spec": tmp_path / "trust_spec.json",
        "trust_output": tmp_path / "trust_diagnostics.csv",
        "applicability": tmp_path / "applicability_summary.csv",
        "error": tmp_path / "error_structure_summary.csv",
        "claim": tmp_path / "claim_boundary.csv",
        "conclusion": tmp_path / "trust_conclusion.csv",
    }
    for name, df in [
        ("analysis", analysis),
        ("predictions", predictions),
        ("metrics", metrics),
        ("comparison", comparison),
        ("screening", screening),
        ("split", split),
        ("inventory", inventory),
        ("ambiguity", ambiguity),
    ]:
        df.to_csv(paths[name], index=False)
    paths["validation_spec"].write_text(json.dumps(validation_spec), encoding="utf-8")
    paths["trust_spec"].write_text(json.dumps(trust_spec), encoding="utf-8")
    return paths


def test_trust_cli_writes_outputs_and_preserves_sources(tmp_path: Path) -> None:
    paths = _write_synthetic_trust_inputs(tmp_path)
    before_analysis = paths["analysis"].read_bytes()
    before_predictions = paths["predictions"].read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_materials_project_v1_3_trust_analysis.py",
            "--analysis-input",
            str(paths["analysis"]),
            "--predictions-input",
            str(paths["predictions"]),
            "--metrics-input",
            str(paths["metrics"]),
            "--comparison-input",
            str(paths["comparison"]),
            "--screening-input",
            str(paths["screening"]),
            "--split-diagnostics-input",
            str(paths["split"]),
            "--descriptor-inventory",
            str(paths["inventory"]),
            "--ambiguity-summary",
            str(paths["ambiguity"]),
            "--validation-spec",
            str(paths["validation_spec"]),
            "--trust-spec",
            str(paths["trust_spec"]),
            "--trust-output",
            str(paths["trust_output"]),
            "--applicability-output",
            str(paths["applicability"]),
            "--error-structure-output",
            str(paths["error"]),
            "--claim-boundary-output",
            str(paths["claim"]),
            "--trust-conclusion-output",
            str(paths["conclusion"]),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    summary = json.loads(result.stdout)

    assert paths["analysis"].read_bytes() == before_analysis
    assert paths["predictions"].read_bytes() == before_predictions
    assert summary["analysis_sha_unchanged"] is True
    assert summary["predictions_sha_unchanged"] is True
    for key in ["trust_output", "applicability", "error", "claim", "conclusion"]:
        assert paths[key].exists()
    trust = pd.read_csv(paths["trust_output"])
    claim = pd.read_csv(paths["claim"])
    conclusion = pd.read_csv(paths["conclusion"])
    assert {"nearest_train_distance", "applicability_status", "target_stratum"}.issubset(
        trust.columns
    )
    assert "reliable discovery of novel stable materials" in set(claim["claim"])
    assert conclusion.loc[conclusion["field"].eq("shap_decision"), "value"].iloc[0] == "deferred"


def test_model_eligibility_gate_is_conservative() -> None:
    metrics = pd.DataFrame(
        [
            {
                "split_strategy": "random",
                "split_index": split,
                "model_variant": model,
                "status": "valid",
                "mae": mae,
                "median_absolute_error": mae,
                "r2": r2,
                "spearman": spearman,
            }
            for split in range(3)
            for model, mae, r2, spearman in [
                ("dummy_median", 0.1, -0.1, 0.0),
                ("ridge_raw", 0.2, -2.0, 0.1),
            ]
        ]
    )
    comparison = pd.DataFrame(
        [
            {"strategy": strategy, "model_variant": "ridge_raw", "metric": metric, "median": value}
            for strategy in ["reduced_formula_group", "chemical_system_group"]
            for metric, value in [("r2", -0.5), ("spearman", 0.1)]
        ]
    )
    screening = pd.DataFrame(
        [
            {
                "strategy": "random",
                "model_variant": model,
                "metric": "precision_at_10pct",
                "median": value,
            }
            for model, value in [("dummy_median", 0.5), ("ridge_raw", 0.4)]
        ]
    )

    eligibility = build_model_eligibility(metrics, comparison, screening)

    assert eligibility.loc[eligibility["model_variant"].eq("ridge_raw"), "eligibility_status"].iloc[
        0
    ] in {"diagnostic_only", "not_eligible"}


def test_target_strata_include_exact_zero_and_extreme_tail() -> None:
    strata = assign_target_strata(pd.Series([0.0, 0.001, 0.1, 10.0]))

    assert "exact_zero" in set(strata)
    assert "extreme_tail" in set(strata)
