"""Tests for Materials Project descriptive screening workflow."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from connectors.materials_project_connector import calculate_file_sha256


def _materials_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "material_id": ["mp-1", "mp-2", "mp-3"],
            "formula": ["FeSiO3", "LiFeSiO4", "TiFeSi"],
            "band_gap_ev": [0.6, 1.2, 0.0],
            "formation_energy_ev_atom": [-2.0, -2.5, -0.6],
            "energy_above_hull_ev_atom": [0.05, 0.0, 0.2],
            "density_g_cm3": [3.9, 2.7, 5.5],
            "volume_a3": [220.0, 200.0, 237.0],
            "quality_status": ["valid", "valid", "warning"],
            "quality_issue_count": [0, 0, 1],
            "quality_issues": ["", "", "scope warning"],
        }
    )


def _screening_spec() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "dataset_name": "materials_project_test",
        "screening_mode": "descriptive_observed_property_screening",
        "identifier_column": "material_id",
        "display_columns": ["formula"],
        "filters": [
            {"column": "quality_status", "operator": "in", "values": ["valid"]}
        ],
        "objectives": [
            {
                "property": "energy_above_hull_ev_atom",
                "mode": "minimize",
                "weight": 1.0,
                "target": None,
                "lower_bound": None,
                "upper_bound": None,
                "unit": "eV/atom",
                "rationale": "descriptive stability-proxy screen",
            }
        ],
        "missing_value_policy": "exclude_from_ranking",
        "tie_policy": "min_rank",
        "top_n": 2,
        "provenance_status": "reconstructed",
        "limitations": ["synthetic test"],
        "notes": ["no credentials"],
    }


def test_materials_project_screening_cli_creates_results_and_summary(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("MP_API_KEY", raising=False)
    input_path = tmp_path / "materials_project_normalized.csv"
    spec_path = tmp_path / "screening_spec.json"
    results_output = tmp_path / "screening_results.csv"
    summary_output = tmp_path / "screening_summary.csv"
    _materials_df().to_csv(input_path, index=False)
    spec_path.write_text(json.dumps(_screening_spec(), indent=2), encoding="utf-8")
    input_hash = calculate_file_sha256(input_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_materials_project_screening.py",
            "--input",
            str(input_path),
            "--screening-spec",
            str(spec_path),
            "--results-output",
            str(results_output),
            "--summary-output",
            str(summary_output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    results = pd.read_csv(results_output)
    summary = pd.read_csv(summary_output)

    assert len(results) == 3
    assert len(summary) == 2
    assert summary.iloc[0]["material_id"] == "mp-2"
    assert results[results["material_id"].eq("mp-3")].iloc[0]["screening_status"] == "filter_failed"
    assert calculate_file_sha256(input_path) == input_hash
    assert "ranked candidate count: 2" in result.stdout
    assert "descriptive screening" in result.stdout


def test_materials_project_screening_outputs_preserve_properties(tmp_path) -> None:
    input_path = tmp_path / "materials_project_normalized.csv"
    spec_path = tmp_path / "screening_spec.json"
    results_output = tmp_path / "screening_results.csv"
    summary_output = tmp_path / "screening_summary.csv"
    _materials_df().to_csv(input_path, index=False)
    spec_path.write_text(json.dumps(_screening_spec(), indent=2), encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            "scripts/run_materials_project_screening.py",
            "--input",
            str(input_path),
            "--screening-spec",
            str(spec_path),
            "--results-output",
            str(results_output),
            "--summary-output",
            str(summary_output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    results = pd.read_csv(results_output)

    assert "energy_above_hull_ev_atom" in results.columns
    assert "energy_above_hull_ev_atom_objective_score" in results.columns
    assert "overall_rank" in results.columns
    assert not results.astype(str).stack().str.contains(r"^[A-Za-z]:\\|^/|^\\\\", regex=True).any()
    assert not results.astype(str).stack().str.contains(
        r"api[_-]?key|token|secret|credential|password|sk-",
        case=False,
        regex=True,
    ).any()
