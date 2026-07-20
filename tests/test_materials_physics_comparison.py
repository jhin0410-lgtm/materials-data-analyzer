"""Synthetic tests for Materials v2.2 predictive-value comparison."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from src.analyzers import materials_physics_features as mpf
from src.analyzers.grouped_regression_validation import ModelConfig
from src.platform_core.artifacts import build_default_artifact_registry


def _write_synthetic_comparison_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    rows = []
    source_rows = []
    for i in range(36):
        formula = "FeSi" if i % 3 == 0 else "Fe2Si" if i % 3 == 1 else "LiFePO4"
        formula_group = f"F{i // 3}"
        chemsys = f"S{i // 9}"
        target = float((i % 6) * 0.02 + (i // 9) * 0.03)
        rows.append(
            {
                "material_id": f"mp-{i:03d}",
                "formula_pretty": formula,
                "reduced_formula_group": formula_group,
                "chemical_system_group": chemsys,
                "baseline_a": float(i % 5),
                "baseline_b": float((i // 2) % 7),
                "energy_above_hull": target,
                "theoretical": bool(i % 2),
            }
        )
        source_rows.append(
            {
                "material_id": f"mp-{i:03d}",
                "formula_pretty": formula,
                "energy_above_hull": target,
                "theoretical": bool(i % 2),
            }
        )
    analysis = pd.DataFrame(rows)
    source = pd.DataFrame(source_rows)
    feature_result = mpf.build_feature_matrix(
        source,
        mpf.MaterialsFeatureBuildRequest(input_path=tmp_path / "source.csv"),
    )
    feature_matrix_path = tmp_path / "features.csv"
    analysis_path = tmp_path / "analysis_ready.csv"
    inventory_path = tmp_path / "inventory.csv"
    ambiguity_path = tmp_path / "ambiguity.csv"
    spec_path = tmp_path / "validation_spec.json"
    feature_result.feature_matrix.to_csv(feature_matrix_path, index=False)
    analysis.to_csv(analysis_path, index=False)
    pd.DataFrame(
        [
            {"column_name": "baseline_a", "primary_feature": True},
            {"column_name": "baseline_b", "primary_feature": True},
        ]
    ).to_csv(inventory_path, index=False)
    (
        analysis.groupby("reduced_formula_group", as_index=False)
        .agg(row_count=("material_id", "count"))
        .assign(ambiguity_flag=False)
        .to_csv(ambiguity_path, index=False)
    )
    features = ["baseline_a", "baseline_b"]
    feature_hash = hashlib.sha256(json.dumps(features, sort_keys=True).encode("utf-8")).hexdigest()
    spec = {
        "schema_version": "1.0",
        "identifier_column": "material_id",
        "target_column": "energy_above_hull",
        "feature_columns": features,
        "feature_columns_sha256": feature_hash,
        "forbidden_features": [
            "material_id",
            "formula_pretty",
            "energy_above_hull",
            "reduced_formula_group",
            "chemical_system_group",
        ],
        "evaluation_only_columns": ["theoretical"],
        "n_splits": 2,
        "test_size": 0.25,
        "random_state": 42,
    }
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    return feature_matrix_path, analysis_path, inventory_path, ambiguity_path, spec_path


def test_predictive_comparison_uses_matched_rows_and_writes_summaries(tmp_path: Path, monkeypatch) -> None:
    feature_matrix_path, analysis_path, inventory_path, ambiguity_path, spec_path = _write_synthetic_comparison_inputs(tmp_path)
    evidence_path = tmp_path / "feature_use_evidence.json"
    evidence_path.write_bytes(
        Path("data/processed/materials_physics_v2_2_feature_use_evidence.json").read_bytes()
    )
    monkeypatch.setattr(
        mpf,
        "default_model_configs",
        lambda random_state=42: [
            ModelConfig("dummy_median", "dummy_median", "raw", random_state=random_state),
            ModelConfig("ridge_raw", "ridge", "raw", random_state=random_state),
        ],
    )
    request = mpf.MaterialsPredictiveComparisonRequest(
        feature_matrix_path=feature_matrix_path,
        analysis_ready_path=analysis_path,
        descriptor_inventory_path=inventory_path,
        ambiguity_summary_path=ambiguity_path,
        validation_spec_path=spec_path,
        output_dir=tmp_path / "outputs",
        tracked_metric_summary_path=tmp_path / "comparison_summary.csv",
        tracked_decision_path=tmp_path / "decision.json",
        tracked_evidence_path=evidence_path,
        tracked_report_summary_path=tmp_path / "report.md",
    )

    manifest = mpf.run_predictive_comparison(request)

    assert manifest["rows"]["matched_rows"] == 36
    assert manifest["claim_boundary"]["physics_informed_feature_used"] is True
    assert request.tracked_metric_summary_path.exists()
    assert request.tracked_decision_path.exists()
    assert request.tracked_evidence_path.exists()
    summary = pd.read_csv(request.tracked_metric_summary_path)
    assert {"matched_baseline", "physics_only", "combined_baseline_physics"}.issubset(
        set(summary["feature_set_id"])
    )
    decision = json.loads(request.tracked_decision_path.read_text(encoding="utf-8"))
    assert decision["representative_model_selected"] is False
    assert decision["predictive_value_status"] in {
        "predictive_value_supported",
        "predictive_value_limited",
        "random_only_improvement",
        "no_material_improvement",
        "performance_degraded",
        "inconclusive_low_sample",
        "blocked_feature_coverage",
    }
    split_assignments = pd.read_csv(manifest["local_outputs"]["local_split_assignments"])
    assert {"train", "test"}.issubset(set(split_assignments["assignment"]))


def test_feature_artifact_validation_rejects_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad_features.csv"
    pd.DataFrame([{"material_id": "mp-1"}]).to_csv(path, index=False)

    result = mpf.validate_feature_artifact(path)

    assert result["valid"] is False
    assert "feature_build_status" in result["missing_columns"]


def test_materials_v2_2_schemas_parse_and_artifacts_are_registered() -> None:
    feature_schema = json.loads(
        Path("data/platform/materials_physics_feature_definition_schema_v2.json").read_text(
            encoding="utf-8"
        )
    )
    comparison_schema = json.loads(
        Path("data/platform/materials_predictive_comparison_schema_v2.json").read_text(
            encoding="utf-8"
        )
    )
    artifact_registry = build_default_artifact_registry()

    assert feature_schema["schema_version"] == "2.2.1"
    assert "physics_constrained_model" in feature_schema["claim_boundary"]["prohibited"]
    assert comparison_schema["split_strategy_policy"]["random"] == "optimistic_reference_only"
    assert (
        artifact_registry.get("materials_physics_v2_2_predictive_value_decision").tracked_policy
        == "generated_compact"
    )
    assert artifact_registry.get("materials_physics_v2_2_predictions").local_only is True
