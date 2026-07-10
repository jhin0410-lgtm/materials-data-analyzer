"""Tests for Materials Project query contract artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from connectors.materials_project_connector import (
    build_property_inventory,
    calculate_file_sha256,
    create_provenance_manifest,
    validate_query_spec,
)


def _valid_query_spec() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "dataset_name": "materials_project_test",
        "source_system": "Materials Project",
        "case_study_scope": "Synthetic Fe/Si-containing test fixture.",
        "query_mode": "summary_search_element_containment_probe",
        "required_elements": ["Fe", "Si"],
        "excluded_elements": [],
        "chemical_system_policy": "element_containment_not_binary_only",
        "requested_fields": [
            "material_id",
            "formula_pretty",
            "band_gap",
            "formation_energy_per_atom",
            "energy_above_hull",
            "density",
            "volume",
        ],
        "optional_filters": {},
        "result_limit": 50,
        "expected_identifier_column": "material_id",
        "provenance_status": "reconstructed",
        "notes": ["synthetic fixture"],
    }


def _test_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "material_id": ["mp-1", "mp-2", "mp-2"],
            "formula": ["FeSiO3", "LiFeSiO4", "LiFeSiO4"],
            "band_gap_ev": [0.0, 1.2, 1.4],
            "formation_energy_ev_atom": [-1.0, -2.0, -2.1],
            "energy_above_hull_ev_atom": [0.0, 0.03, 0.04],
            "density_g_cm3": [5.1, 2.7, 2.8],
            "volume_a3": [100.0, 200.0, 210.0],
        }
    )


def test_validate_query_spec_accepts_valid_contract() -> None:
    validate_query_spec(_valid_query_spec())


def test_validate_query_spec_rejects_missing_required_field() -> None:
    spec = _valid_query_spec()
    spec.pop("source_system")

    with pytest.raises(ValueError, match="missing required"):
        validate_query_spec(spec)


def test_validate_query_spec_rejects_duplicate_requested_fields() -> None:
    spec = _valid_query_spec()
    spec["requested_fields"] = ["material_id", "material_id"]

    with pytest.raises(ValueError, match="duplicate"):
        validate_query_spec(spec)


def test_validate_query_spec_rejects_invalid_result_limit() -> None:
    spec = _valid_query_spec()
    spec["result_limit"] = 0

    with pytest.raises(ValueError, match="positive integer"):
        validate_query_spec(spec)


def test_validate_query_spec_rejects_credential_like_keys_and_absolute_paths() -> None:
    credential_spec = _valid_query_spec()
    credential_spec["api_key"] = "do-not-store"
    with pytest.raises(ValueError, match="credential"):
        validate_query_spec(credential_spec)

    path_spec = _valid_query_spec()
    path_spec["notes"] = ["C:\\private\\materials_project.csv"]
    with pytest.raises(ValueError, match="absolute paths"):
        validate_query_spec(path_spec)


def test_manifest_preserves_unknown_retrieval_metadata_and_counts(tmp_path) -> None:
    csv_path = tmp_path / "materials.csv"
    df = _test_df()
    df.to_csv(csv_path, index=False)
    spec = _valid_query_spec()

    manifest = create_provenance_manifest(
        df=df,
        artifact_path=csv_path,
        query_spec=spec,
        query_spec_path="data/case_studies/materials_project/query_spec.json",
        generated_manifest_timestamp="2026-07-10T00:00:00+00:00",
    )

    assert manifest["row_count"] == 3
    assert manifest["column_count"] == 7
    assert manifest["artifact_sha256"] == calculate_file_sha256(csv_path)
    assert manifest["unique_identifier_count"] == 2
    assert manifest["duplicate_identifier_count"] == 1
    assert manifest["credential_included"] is False
    assert manifest["retrieval_timestamp"] is None
    assert manifest["api_version"] is None
    assert manifest["missing_requested_columns"] == []
    assert manifest["extra_columns"] == []


def test_property_inventory_summarizes_columns_and_leakage_roles() -> None:
    inventory = build_property_inventory(_test_df())

    assert len(inventory) == 7
    band_gap = inventory[inventory["column_name"].eq("band_gap_ev")].iloc[0]
    material_id = inventory[inventory["column_name"].eq("material_id")].iloc[0]
    hull = inventory[inventory["column_name"].eq("energy_above_hull_ev_atom")].iloc[0]

    assert band_gap["semantic_role"] == "electronic_property"
    assert band_gap["numeric_median"] == 1.2
    assert bool(band_gap["target_candidate"]) is True
    assert bool(material_id["identifier_column"]) is True
    assert bool(material_id["feature_candidate"]) is False
    assert hull["leakage_risk"] == "leakage candidate"
    assert len(str(inventory.loc[0, "example_values"]).split("; ")) <= 3


def test_query_contract_cli_creates_outputs_without_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MP_API_KEY", raising=False)
    csv_path = tmp_path / "materials.csv"
    spec_path = tmp_path / "query_spec.json"
    manifest_path = tmp_path / "manifest.json"
    inventory_path = tmp_path / "inventory.csv"
    input_hash = None

    _test_df().to_csv(csv_path, index=False)
    input_hash = calculate_file_sha256(csv_path)
    spec_path.write_text(
        json.dumps(_valid_query_spec(), indent=2),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_materials_project_query_contract.py",
            "--input",
            str(csv_path),
            "--query-spec",
            str(spec_path),
            "--manifest-output",
            str(manifest_path),
            "--property-inventory-output",
            str(inventory_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inventory = pd.read_csv(inventory_path)

    assert manifest["row_count"] == 3
    assert manifest["local_artifact_path"].endswith("materials.csv")
    assert manifest["credential_included"] is False
    assert manifest["absolute_path_included"] is False
    assert manifest["consistency_checks"]["requested_columns_match"] is True
    assert len(inventory) == 7
    assert calculate_file_sha256(csv_path) == input_hash
    assert "row count: 3" in result.stdout
    assert "credential included: False" in result.stdout
