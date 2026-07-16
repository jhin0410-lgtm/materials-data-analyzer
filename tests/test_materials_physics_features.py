"""Tests for Materials v2.2 physics-aware feature builders."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from src.analyzers import materials_physics_features as mpf


def test_formula_parser_handles_formula_mapping_and_malformed_values() -> None:
    formula, status = mpf.parse_composition_value("Fe2Si")
    assert status == "parsed"
    assert formula is not None
    fractions = mpf.normalized_atomic_fractions(formula)
    assert math.isclose(fractions["Fe"], 2 / 3)
    assert math.isclose(fractions["Si"], 1 / 3)

    mapping, mapping_status = mpf.parse_composition_value({"Fe": 1, "Si": 1})
    assert mapping_status == "parsed"
    assert mapping is not None
    assert math.isclose(mpf.normalized_atomic_fractions(mapping)["Fe"], 0.5)

    malformed, malformed_status = mpf.parse_composition_value("@@@")
    assert malformed is None
    assert malformed_status.startswith("parse_error")


def test_feature_values_follow_documented_formulas() -> None:
    composition, _ = mpf.parse_composition_value("FeSi")
    assert composition is not None
    fractions = mpf.normalized_atomic_fractions(composition)
    values, issues, coverage, unsupported = mpf.compute_feature_values(fractions)
    by_column = {item.column_name: item.value for item in values}

    assert issues == []
    assert coverage == 1.0
    assert unsupported == 0
    assert math.isclose(by_column["number_of_elements"], 2)
    assert math.isclose(
        by_column["configurational_mixing_entropy_j_per_mol_k"],
        mpf.GAS_CONSTANT_J_PER_MOL_K * math.log(2),
    )
    assert math.isclose(by_column["valence_electron_concentration"], 6.0)
    assert by_column["atomic_radius_mismatch"] >= 0
    assert by_column["electronegativity_mismatch"] >= 0


def test_feature_matrix_rejects_parse_failures_without_dropping_rows(tmp_path: Path) -> None:
    source = pd.DataFrame(
        [
            {"material_id": "mp-1", "formula_pretty": "FeSi", "energy_above_hull": 0.0},
            {"material_id": "mp-2", "formula_pretty": "LiFePO4", "energy_above_hull": 0.1},
            {"material_id": "mp-3", "formula_pretty": "@@@", "energy_above_hull": 0.2},
        ]
    )
    request = mpf.MaterialsFeatureBuildRequest(input_path=tmp_path / "source.csv")
    result = mpf.build_feature_matrix(source, request)

    assert len(result.feature_matrix) == 3
    assert result.summary["generated_rows"] == 2
    assert result.summary["unavailable_rows"] == 1
    failed = result.feature_matrix[result.feature_matrix["material_id"].eq("mp-3")].iloc[0]
    assert failed["composition_parse_status"] == "failed"
    assert failed["feature_build_status"] == "unavailable"


def test_feature_build_writes_local_and_compact_outputs(tmp_path: Path) -> None:
    source = pd.DataFrame(
        [
            {
                "material_id": "mp-1",
                "formula_pretty": "FeSi",
                "composition_reduced": json.dumps({"Fe": 1, "Si": 1}),
                "energy_above_hull": 0.0,
            }
        ]
    )
    input_path = tmp_path / "source.csv"
    source.to_csv(input_path, index=False)
    request = mpf.MaterialsFeatureBuildRequest(
        input_path=input_path,
        output_dir=tmp_path / "outputs",
        tracked_definition_path=tmp_path / "feature_definitions.csv",
        tracked_property_source_path=tmp_path / "property_source.json",
        tracked_coverage_path=tmp_path / "coverage.csv",
        tracked_evidence_path=tmp_path / "evidence.json",
    )

    manifest = mpf.run_feature_build(request)

    assert Path(manifest["local_outputs"]["feature_matrix"]).exists()
    assert request.tracked_definition_path.exists()
    assert request.tracked_property_source_path.exists()
    assert request.tracked_coverage_path.exists()
    evidence = json.loads(request.tracked_evidence_path.read_text(encoding="utf-8"))
    assert evidence["physics_informed_feature_available"] is True
    assert evidence["physics_informed_feature_used"] is False
    validation = mpf.validate_feature_artifact(manifest["local_outputs"]["feature_matrix"])
    assert validation["valid"] is True


def test_property_source_metadata_is_deterministic_and_sanitized() -> None:
    first = mpf.build_property_source_metadata(["Fe", "Si"]).to_dict()
    second = mpf.build_property_source_metadata(["Si", "Fe"]).to_dict()

    assert first["checksum_sha256"] == second["checksum_sha256"]
    assert first["supported_elements"] == ["Fe", "Si"]
    payload = json.dumps(first)
    assert ("C:" + "/") not in payload
    assert ("sec" + "ret") not in payload.lower()


def test_missing_property_policy_does_not_renormalize(monkeypatch) -> None:
    original_property = mpf.element_property_value

    def fake_property(element_symbol: str, property_name: str) -> float | None:
        if element_symbol == "Fe" and property_name == "atomic_radius":
            return None
        return original_property(element_symbol, property_name)

    monkeypatch.setattr(mpf, "element_property_value", fake_property)
    composition, _ = mpf.parse_composition_value("FeSi")
    assert composition is not None

    values, issues, coverage, unsupported = mpf.compute_feature_values(
        mpf.normalized_atomic_fractions(composition)
    )

    assert unsupported == 1
    assert coverage < 1.0
    assert any("unsupported_element_property" in issue for issue in issues)
    assert all(item.status == "unavailable" for item in values)
