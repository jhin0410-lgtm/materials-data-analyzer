"""Tests for Materials Project schema normalization and quality summaries."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from connectors.materials_project_connector import calculate_file_sha256
from loaders.materials_project_loader import (
    build_quality_summary,
    load_schema_contract,
    normalize_materials_project_dataframe,
    validate_local_table_schema,
    validate_schema_contract,
)


def _schema_contract() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "dataset_name": "materials_project_test",
        "provenance_status": "reconstructed",
        "identifier_column": "material_id",
        "required_columns": [
            "material_id",
            "formula",
            "band_gap_ev",
            "formation_energy_ev_atom",
            "energy_above_hull_ev_atom",
            "density_g_cm3",
            "volume_a3",
        ],
        "optional_columns": [],
        "column_mappings": [
            {
                "source_column": "material_id",
                "canonical_column": "material_id",
                "semantic_role": "identifier",
                "expected_dtype": "string",
                "unit": "unknown",
                "required": True,
                "nullable": False,
                "identifier": True,
                "target_candidate": False,
                "feature_candidate": False,
                "leakage_risk": "identifier only",
                "interpretation_note": "identifier only",
            },
            {
                "source_column": "formula",
                "canonical_column": "formula",
                "semantic_role": "composition",
                "expected_dtype": "string",
                "unit": "unknown",
                "required": True,
                "nullable": False,
                "identifier": False,
                "target_candidate": False,
                "feature_candidate": False,
                "leakage_risk": "conditional",
                "interpretation_note": "composition label",
            },
            {
                "source_column": "band_gap_ev",
                "canonical_column": "band_gap_ev",
                "semantic_role": "electronic_property",
                "expected_dtype": "float",
                "unit": "eV",
                "required": True,
                "nullable": False,
                "identifier": False,
                "target_candidate": True,
                "feature_candidate": True,
                "leakage_risk": "conditional",
                "interpretation_note": "target candidate",
            },
            {
                "source_column": "formation_energy_ev_atom",
                "canonical_column": "formation_energy_ev_atom",
                "semantic_role": "thermodynamic_property",
                "expected_dtype": "float",
                "unit": "eV/atom",
                "required": True,
                "nullable": False,
                "identifier": False,
                "target_candidate": True,
                "feature_candidate": True,
                "leakage_risk": "leakage candidate",
                "interpretation_note": "thermodynamic property",
            },
            {
                "source_column": "energy_above_hull_ev_atom",
                "canonical_column": "energy_above_hull_ev_atom",
                "semantic_role": "thermodynamic_property",
                "expected_dtype": "float",
                "unit": "eV/atom",
                "required": True,
                "nullable": False,
                "identifier": False,
                "target_candidate": True,
                "feature_candidate": True,
                "leakage_risk": "leakage candidate",
                "interpretation_note": "stability proxy",
            },
            {
                "source_column": "density_g_cm3",
                "canonical_column": "density_g_cm3",
                "semantic_role": "structure",
                "expected_dtype": "float",
                "unit": "g/cm3",
                "required": True,
                "nullable": False,
                "identifier": False,
                "target_candidate": True,
                "feature_candidate": True,
                "leakage_risk": "conditional",
                "interpretation_note": "structure descriptor",
            },
            {
                "source_column": "volume_a3",
                "canonical_column": "volume_a3",
                "semantic_role": "structure",
                "expected_dtype": "float",
                "unit": "A^3",
                "required": True,
                "nullable": False,
                "identifier": False,
                "target_candidate": True,
                "feature_candidate": True,
                "leakage_risk": "conditional",
                "interpretation_note": "volume descriptor",
            },
        ],
        "data_types": {
            "material_id": "string",
            "formula": "string",
            "band_gap_ev": "float",
            "formation_energy_ev_atom": "float",
            "energy_above_hull_ev_atom": "float",
            "density_g_cm3": "float",
            "volume_a3": "float",
        },
        "units": {
            "material_id": "unknown",
            "formula": "unknown",
            "band_gap_ev": "eV",
            "formation_energy_ev_atom": "eV/atom",
            "energy_above_hull_ev_atom": "eV/atom",
            "density_g_cm3": "g/cm3",
            "volume_a3": "A^3",
        },
        "nullable_policy": {
            "material_id": False,
            "formula": False,
            "band_gap_ev": False,
            "formation_energy_ev_atom": False,
            "energy_above_hull_ev_atom": False,
            "density_g_cm3": False,
            "volume_a3": False,
        },
        "uniqueness_policy": {"material_id": "unique_required"},
        "quality_rules": {
            "required_elements": ["Fe", "Si"],
            "formula_scope_policy": "element_containment_not_binary_only",
        },
        "notes": ["synthetic fixture"],
    }


def _source_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "material_id": [" mp-1 ", "mp-2", "mp-3"],
            "formula": ["FeSiO3", "LiFeSiO4", "TiFeSi"],
            "band_gap_ev": ["0.0", "1.2", "2.5"],
            "formation_energy_ev_atom": [-1.0, -2.0, -0.5],
            "energy_above_hull_ev_atom": [0.0, 0.03, 0.01],
            "density_g_cm3": [5.1, 2.7, 4.2],
            "volume_a3": [100.0, 200.0, 150.0],
        }
    )


def _write_contract(tmp_path: Path, contract: dict[str, object] | None = None) -> Path:
    path = tmp_path / "schema_contract.json"
    path.write_text(
        json.dumps(contract or _schema_contract(), indent=2),
        encoding="utf-8",
    )
    return path


def test_validate_schema_contract_accepts_valid_contract() -> None:
    validate_schema_contract(_schema_contract())


def test_validate_schema_contract_rejects_missing_required_column() -> None:
    df = _source_df().drop(columns=["formula"])

    with pytest.raises(ValueError, match="missing required column"):
        validate_local_table_schema(df, _schema_contract())


def test_validate_schema_contract_rejects_duplicate_canonical_column() -> None:
    contract = _schema_contract()
    mappings = contract["column_mappings"]
    mappings[1]["canonical_column"] = "material_id"

    with pytest.raises(ValueError, match="duplicate canonical"):
        validate_schema_contract(contract)


def test_validate_schema_contract_rejects_invalid_semantic_role() -> None:
    contract = _schema_contract()
    contract["column_mappings"][2]["semantic_role"] = "made_up_role"

    with pytest.raises(ValueError, match="Unsupported semantic_role"):
        validate_schema_contract(contract)


def test_normalization_is_deterministic_and_preserves_row_count() -> None:
    normalized, audit = normalize_materials_project_dataframe(
        _source_df(),
        _schema_contract(),
    )

    assert len(normalized) == 3
    assert normalized.loc[0, "material_id"] == "mp-1"
    assert normalized["band_gap_ev"].tolist() == [0.0, 1.2, 2.5]
    assert normalized.columns.tolist()[-3:] == [
        "quality_status",
        "quality_issue_count",
        "quality_issues",
    ]
    assert audit["conversion_failures_by_column"]["band_gap_ev"] == 0


def test_numeric_conversion_failure_and_missing_identifier_are_flagged() -> None:
    df = _source_df()
    df.loc[0, "band_gap_ev"] = "not-a-number"
    df.loc[1, "material_id"] = ""

    normalized, audit = normalize_materials_project_dataframe(df, _schema_contract())

    assert audit["conversion_failures_by_column"]["band_gap_ev"] == 1
    assert "nonnumeric_property_value:band_gap_ev" in normalized.loc[0, "quality_issues"]
    assert normalized.loc[1, "quality_status"] == "invalid"
    assert "missing_identifier" in normalized.loc[1, "quality_issues"]


def test_duplicate_identifier_and_fe_si_scope_are_quality_warnings() -> None:
    df = _source_df()
    df.loc[1, "material_id"] = "mp-1"
    df.loc[1, "formula"] = "SiO2"
    df.loc[2, "formula"] = "FeSi"

    normalized, audit = normalize_materials_project_dataframe(df, _schema_contract())
    summary = build_quality_summary(normalized, _schema_contract(), audit)

    assert "duplicate_identifier" in normalized.loc[0, "quality_issues"]
    assert "required_element_missing_fe" in normalized.loc[1, "quality_issues"]
    assert "binary_scope_mismatch" in normalized.loc[2, "quality_issues"]
    assert int(summary.loc[summary["metric"].eq("binary_fe_si_rows"), "count"].iloc[0]) == 1
    assert int(summary.loc[summary["metric"].eq("multinary_fe_si_containing_rows"), "count"].iloc[0]) == 1


def test_unknown_numeric_unit_is_warning_not_schema_failure() -> None:
    contract = _schema_contract()
    contract["column_mappings"][2]["unit"] = "unknown"
    contract["units"]["band_gap_ev"] = "unknown"

    normalized, _ = normalize_materials_project_dataframe(_source_df(), contract)

    assert "unknown_unit:band_gap_ev" in normalized.loc[0, "quality_issues"]
    assert normalized.loc[0, "quality_status"] == "warning"


def test_schema_contract_rejects_credential_like_key_and_absolute_path() -> None:
    credential_contract = _schema_contract()
    credential_contract["api_key"] = "do-not-store"
    with pytest.raises(ValueError, match="credential"):
        validate_schema_contract(credential_contract)

    path_contract = _schema_contract()
    path_contract["notes"] = ["C:\\private\\materials_project.csv"]
    with pytest.raises(ValueError, match="absolute paths"):
        validate_schema_contract(path_contract)


def test_normalization_cli_creates_outputs_without_api_or_input_changes(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("MP_API_KEY", raising=False)
    input_path = tmp_path / "materials.csv"
    contract_path = _write_contract(tmp_path)
    normalized_output = tmp_path / "normalized.csv"
    quality_output = tmp_path / "quality.csv"
    _source_df().to_csv(input_path, index=False)
    input_hash = calculate_file_sha256(input_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_materials_project_normalized.py",
            "--input",
            str(input_path),
            "--schema-contract",
            str(contract_path),
            "--normalized-output",
            str(normalized_output),
            "--quality-summary-output",
            str(quality_output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    normalized = pd.read_csv(normalized_output)
    quality = pd.read_csv(quality_output)

    assert len(normalized) == 3
    assert "quality_status" in normalized.columns
    assert "total_rows" in quality["metric"].tolist()
    assert calculate_file_sha256(input_path) == input_hash
    assert "output row count: 3" in result.stdout
    assert "credential included: False" in result.stdout
