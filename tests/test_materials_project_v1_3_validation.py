"""Tests for Materials Project v1.3.4 validation orchestration."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


FEATURE_COLUMNS = ["feature_a", "feature_b"]


def _write_synthetic_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    rows = []
    for i in range(36):
        formula = f"F{i // 3}"
        chemsys = f"S{i // 9}"
        rows.append(
            {
                "material_id": f"mp-{i:03d}",
                "formula_pretty": formula,
                "reduced_formula_group": formula,
                "chemical_system_group": chemsys,
                "feature_a": float(i % 6),
                "feature_b": float((i // 2) % 5),
                "energy_above_hull": float((i % 6) * 0.05 + (i // 9) * 0.03),
                "theoretical": bool(i % 2),
            }
        )
    analysis = pd.DataFrame(rows)
    inventory = pd.DataFrame(
        [
            {"column_name": "feature_a", "primary_feature": True},
            {"column_name": "feature_b", "primary_feature": True},
            {"column_name": "material_id", "primary_feature": False},
            {"column_name": "energy_above_hull", "primary_feature": False},
        ]
    )
    ambiguity = (
        analysis.groupby("reduced_formula_group", as_index=False)
        .agg(row_count=("material_id", "count"))
        .assign(ambiguity_flag=lambda df: df["row_count"].gt(1))
    )
    feature_hash = hashlib.sha256(
        json.dumps(FEATURE_COLUMNS, sort_keys=True).encode("utf-8")
    ).hexdigest()
    spec = {
        "schema_version": "1.0",
        "dataset_version": "test",
        "validation_version": "test",
        "execution_status": "specified",
        "identifier_column": "material_id",
        "target_column": "energy_above_hull",
        "primary_feature_source": "synthetic",
        "feature_columns": FEATURE_COLUMNS,
        "feature_columns_sha256": feature_hash,
        "forbidden_features": [
            "material_id",
            "formula_pretty",
            "energy_above_hull",
            "reduced_formula_group",
            "chemical_system_group",
        ],
        "evaluation_only_columns": ["theoretical"],
        "split_strategies": [],
        "n_splits": 2,
        "test_size": 0.25,
        "random_state": 42,
        "model_variants": [],
        "target_treatments": [],
        "nonnegative_prediction_policy": {},
        "regression_metrics": [],
        "ranking_metrics": [],
        "subgroup_metrics": [],
        "overlap_diagnostics": [],
        "output_paths": {},
        "stop_conditions": [],
        "interpretation_limits": [],
    }
    analysis_path = tmp_path / "analysis_ready.csv"
    inventory_path = tmp_path / "inventory.csv"
    ambiguity_path = tmp_path / "ambiguity.csv"
    spec_path = tmp_path / "validation_spec.json"
    analysis.to_csv(analysis_path, index=False)
    inventory.to_csv(inventory_path, index=False)
    ambiguity.to_csv(ambiguity_path, index=False)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    return analysis_path, inventory_path, ambiguity_path, spec_path


def test_materials_project_validation_cli_writes_outputs_and_preserves_source(tmp_path: Path) -> None:
    analysis_path, inventory_path, ambiguity_path, spec_path = _write_synthetic_inputs(tmp_path)
    before = analysis_path.read_bytes()
    outputs = {
        "predictions": tmp_path / "predictions.csv",
        "metrics": tmp_path / "metrics.csv",
        "comparison": tmp_path / "comparison.csv",
        "split": tmp_path / "split.csv",
        "screening": tmp_path / "screening.csv",
    }

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_materials_project_v1_3_validation.py",
            "--input",
            str(analysis_path),
            "--inventory",
            str(inventory_path),
            "--ambiguity-summary",
            str(ambiguity_path),
            "--spec",
            str(spec_path),
            "--predictions-output",
            str(outputs["predictions"]),
            "--metrics-output",
            str(outputs["metrics"]),
            "--comparison-output",
            str(outputs["comparison"]),
            "--split-diagnostics-output",
            str(outputs["split"]),
            "--screening-output",
            str(outputs["screening"]),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    summary = json.loads(result.stdout)

    assert analysis_path.read_bytes() == before
    assert summary["feature_count"] == 2
    assert summary["source_sha_unchanged"] is True
    for path in outputs.values():
        assert path.exists()
    metrics = pd.read_csv(outputs["metrics"])
    predictions = pd.read_csv(outputs["predictions"])
    split = pd.read_csv(outputs["split"])
    screening = pd.read_csv(outputs["screening"])
    assert set(metrics["model_variant"]) == {
        "dummy_median",
        "ridge_raw",
        "ridge_log1p",
        "histogram_gradient_boosting_raw",
        "histogram_gradient_boosting_log1p",
    }
    assert {"random", "reduced_formula_group", "chemical_system_group"}.issubset(
        set(metrics["split_strategy"])
    )
    assert "negative_prediction_count" in metrics.columns
    assert "precision_at_10pct" in screening["metric"].values
    assert "descriptor_seen_in_train" in predictions.columns
    assert split["split_status"].eq("valid").all()


def test_validation_cli_rejects_spec_feature_mismatch(tmp_path: Path) -> None:
    analysis_path, inventory_path, ambiguity_path, spec_path = _write_synthetic_inputs(tmp_path)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["feature_columns"] = ["feature_a"]
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_materials_project_v1_3_validation.py",
            "--input",
            str(analysis_path),
            "--inventory",
            str(inventory_path),
            "--ambiguity-summary",
            str(ambiguity_path),
            "--spec",
            str(spec_path),
            "--predictions-output",
            str(tmp_path / "predictions.csv"),
            "--metrics-output",
            str(tmp_path / "metrics.csv"),
            "--comparison-output",
            str(tmp_path / "comparison.csv"),
            "--split-diagnostics-output",
            str(tmp_path / "split.csv"),
            "--screening-output",
            str(tmp_path / "screening.csv"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "feature_columns do not match" in result.stderr

