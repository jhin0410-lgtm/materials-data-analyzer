import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.analyzers.grouped_regression_validation import ModelConfig, SplitConfig
from src.analyzers.materials_physics_features import CONTROL_FEATURE_COLUMNS, PHYSICS_FEATURE_COLUMNS
from src.analyzers.materials_structure_prediction import (
    KnownStructurePredictionRequest,
    STRUCTURE_CATEGORICAL_FEATURES,
    STRUCTURE_NUMERIC_FEATURES,
    build_feature_sets,
    build_known_structure_cohort,
    forbidden_feature_audit,
    paired_metric_summary,
    preview_known_structure_comparison,
    validate_known_structure_cohort,
    validate_known_structure_result,
    _evaluate_one,
    _prediction_interval_audit,
)


def _write_synthetic_known_structure_inputs(tmp_path: Path) -> KnownStructurePredictionRequest:
    rows = []
    for index in range(8):
        rows.append(
            {
                "material_id": f"mp-test-{index}",
                "formula_pretty": "FeSiO2",
                "reduced_formula_group": f"rf-{index % 4}",
                "chemical_system_group": f"cs-{index % 3}",
                "energy_above_hull": 0.01 * index,
                "baseline_feature": float(index),
                "atomic_radius_weighted_mean": 1.0 + index,
            }
        )
    analysis = pd.DataFrame(rows)
    analysis_path = tmp_path / "analysis.csv"
    analysis.to_csv(analysis_path, index=False)

    physics_rows = []
    for index in range(8):
        row = {
            "material_id": f"mp-test-{index}",
            "feature_build_status": "generated",
        }
        for pos, column in enumerate([*PHYSICS_FEATURE_COLUMNS, *CONTROL_FEATURE_COLUMNS]):
            row[column] = float(index + pos)
        physics_rows.append(row)
    physics_path = tmp_path / "physics.csv"
    pd.DataFrame(physics_rows).to_csv(physics_path, index=False)

    structure_rows = []
    for index in range(8):
        row = {
            "material_id": f"mp-test-{index}",
            "target_accessed": False,
        }
        for pos, column in enumerate(STRUCTURE_NUMERIC_FEATURES):
            row[column] = float(index + pos + 1)
        for column in STRUCTURE_CATEGORICAL_FEATURES:
            row[column] = "cubic" if column == "crystal_system_category" else "221"
        structure_rows.append(row)
    structure_rows[-1]["target_accessed"] = True
    structure_path = tmp_path / "structure.csv"
    pd.DataFrame(structure_rows).to_csv(structure_path, index=False)

    alignment_path = tmp_path / "alignment.csv"
    pd.DataFrame(
        {
            "material_id": [f"mp-test-{index}" for index in range(8)],
            "comparison_status": ["target_exact_match"] * 4 + ["target_within_numeric_tolerance"] * 4,
        }
    ).to_csv(alignment_path, index=False)

    spec_path = tmp_path / "validation_spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "feature_columns": ["baseline_feature", "atomic_radius_weighted_mean"],
                "n_splits": 2,
                "test_size": 0.25,
                "random_state": 7,
            }
        ),
        encoding="utf-8",
    )
    summary_path = tmp_path / "v2_2_4_summary.json"
    summary_path.write_text(json.dumps({"decision_status": "structure_prediction_ready_with_restrictions"}), encoding="utf-8")
    return KnownStructurePredictionRequest(
        analysis_ready_path=analysis_path,
        validation_spec_path=spec_path,
        physics_feature_matrix_path=physics_path,
        structure_descriptor_path=structure_path,
        snapshot_alignment_path=alignment_path,
        v2_2_4_summary_path=summary_path,
        output_dir=tmp_path / "outputs",
    )


def test_known_structure_cohort_preserves_original_target_and_suffixes_physics(tmp_path):
    request = _write_synthetic_known_structure_inputs(tmp_path)
    preview = preview_known_structure_comparison(request)
    assert preview["status"] == "ready_for_local_comparison"
    assert preview["network_required"] is False

    cohort, summary = build_known_structure_cohort(request)

    assert len(cohort) == 7
    assert summary["target_source"] == "original_v1_3_energy_above_hull"
    assert summary["original_target_overwritten"] is False
    assert "atomic_radius_weighted_mean" in cohort.columns
    assert "atomic_radius_weighted_mean__physics" in cohort.columns
    assert "current_energy_above_hull" not in cohort.columns
    assert summary["forbidden_feature_audit"]["forbidden_feature_columns"] == []

    cohort_path = tmp_path / "known_structure_cohort.csv"
    cohort.to_csv(cohort_path, index=False)
    validation = validate_known_structure_cohort(cohort_path)
    assert validation["valid"] is True


def test_feature_sets_keep_graph_and_raw_lattice_out_of_features():
    feature_sets = build_feature_sets(
        baseline_features=["baseline_a"],
        physics_features=["physics_a"],
        structure_numeric=["structure_volume_per_atom", "nearest_neighbor_distance_mean"],
        structure_categorical=["crystal_system_category"],
    )

    assert "known_structure_full_combined_v1" in feature_sets
    all_features = {
        feature
        for spec in feature_sets.values()
        for feature in [*spec["numeric_features"], *spec["categorical_features"]]
    }
    assert "graph_checksum" not in all_features
    assert "raw_lattice_primary_feature" not in all_features

    audit = forbidden_feature_audit(["safe_feature", "energy_above_hull_current", "graph_checksum"])
    assert audit["forbidden_feature_columns"] == ["energy_above_hull_current", "graph_checksum"]


def test_paired_metric_summary_uses_positive_improvement_convention():
    metrics = pd.DataFrame(
        [
            {
                "split_strategy": "reduced_formula_group",
                "split_index": 0,
                "model_variant": "ridge_raw",
                "feature_set_id": "known_structure_composition_baseline_v1",
                "mae": 0.20,
                "rmse": 0.30,
                "r2": 0.1,
            },
            {
                "split_strategy": "reduced_formula_group",
                "split_index": 0,
                "model_variant": "ridge_raw",
                "feature_set_id": "known_structure_baseline_plus_structure_v1",
                "mae": 0.10,
                "rmse": 0.20,
                "r2": 0.2,
            },
        ]
    )

    paired = paired_metric_summary(metrics)
    row = paired[paired["comparison_id"].eq("A_vs_D")].iloc[0]
    assert row["mae_improvement_median"] > 0
    assert row["improvement_sign_convention"] == "positive_means_candidate_better"


def test_prediction_interval_uses_train_internal_calibration_only():
    df = pd.DataFrame(
        {
            "material_id": [f"mp-synth-{index}" for index in range(120)],
            "energy_above_hull": np.linspace(0.0, 0.4, 120),
            "x": np.linspace(0.0, 1.0, 120),
            "reduced_formula_group": [f"rf-{index % 8}" for index in range(120)],
            "chemical_system_group": [f"cs-{index % 5}" for index in range(120)],
        }
    )
    split = {"split_index": 0, "status": "valid", "train_index": np.arange(0, 90), "test_index": np.arange(90, 120)}
    split_config = SplitConfig("random", "shuffle", None, 1, 0.25, 42)
    model_config = ModelConfig("ridge_raw", "ridge", "raw", alpha=1.0, random_state=42)
    feature_set = {
        "feature_set_id": "known_structure_composition_baseline_v1",
        "label": "A",
        "numeric_features": ["x"],
        "categorical_features": [],
    }

    interval = _prediction_interval_audit(
        df,
        feature_set,
        split,
        split_config,
        model_config,
        confidence_level=0.9,
        random_state=42,
    )
    evaluation = _evaluate_one(
        df,
        feature_set,
        split,
        split_config,
        model_config,
        confidence_level=0.9,
        random_state=42,
    )

    assert interval["uncertainty_status"] == "valid"
    assert interval["calibration_row_count"] < len(split["train_index"])
    assert interval["test_row_count"] == len(split["test_index"])
    assert evaluation["metrics"]["status"] == "valid"


def test_known_structure_decision_validation_blocks_overclaims(tmp_path):
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(
        json.dumps(
            {
                "schema_version": "2.2.5",
                "target_source": "original_v1_3_energy_above_hull",
                "claim_boundary": {
                    "graph_model_used": False,
                    "gnn_model": False,
                    "DFT_replacement": False,
                    "hybrid_physics_ml": False,
                },
            }
        ),
        encoding="utf-8",
    )
    assert validate_known_structure_result(decision_path)["valid"] is True

    bad_path = tmp_path / "bad_decision.json"
    bad_path.write_text(
        json.dumps(
            {
                "schema_version": "2.2.5",
                "target_source": "current_energy_above_hull",
                "claim_boundary": {
                    "graph_model_used": True,
                    "gnn_model": False,
                    "DFT_replacement": False,
                    "hybrid_physics_ml": False,
                },
            }
        ),
        encoding="utf-8",
    )
    bad = validate_known_structure_result(bad_path)
    assert bad["valid"] is False
    assert "target_source" in bad["errors"]
    assert "graph_model_used" in bad["errors"]
