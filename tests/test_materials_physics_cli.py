"""CLI tests for Materials v2.2 feature commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_materials_feature_builder_cli_list_and_inspect() -> None:
    listed = _run_cli("--json", "list-materials-feature-builders")
    inspected = _run_cli(
        "--json",
        "inspect-materials-feature-builder",
        "materials.configurational_mixing_entropy",
    )

    assert listed.returncode == 0
    assert any(
        row["feature_id"] == "materials.atomic_radius_mismatch"
        for row in json.loads(listed.stdout)
    )
    assert inspected.returncode == 0
    payload = json.loads(inspected.stdout)
    assert payload["unit"] == "J/mol/K"


def test_materials_feature_build_cli_with_synthetic_config(tmp_path: Path) -> None:
    source = pd.DataFrame(
        [
            {
                "material_id": "mp-1",
                "formula_pretty": "FeSi",
                "energy_above_hull": 0.0,
            }
        ]
    )
    source_path = tmp_path / "source.csv"
    source.to_csv(source_path, index=False)
    config = {
        "input_path": str(source_path),
        "output_dir": str(tmp_path / "outputs"),
        "tracked_definition_path": str(tmp_path / "definitions.csv"),
        "tracked_property_source_path": str(tmp_path / "property_source.json"),
        "tracked_coverage_path": str(tmp_path / "coverage.csv"),
        "tracked_evidence_path": str(tmp_path / "evidence.json"),
    }
    config_path = tmp_path / "feature_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = _run_cli("--json", "build-materials-physics-features", str(config_path))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["generated_rows"] == 1
    feature_matrix = payload["local_outputs"]["feature_matrix"]
    validate = _run_cli("--json", "validate-materials-feature-artifact", feature_matrix)
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["valid"] is True


def test_materials_show_comparison_reports_missing_path() -> None:
    result = _run_cli("--json", "show-materials-feature-comparison", "missing-result")

    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "not_found"
