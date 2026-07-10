"""Tests for Materials Project v1.3.3 composition descriptors."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from features import materials_composition as mc


def _synthetic_acquired() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "material_id": "mp-2",
                "formula_pretty": "FeSi",
                "chemsys": "Fe-Si",
                "elements": '["Fe","Si"]',
                "nelements": 2,
                "theoretical": False,
                "deprecated": False,
                "energy_above_hull": 0.0,
                "composition": '{"Fe":2.0,"Si":2.0}',
                "composition_reduced": '{"Fe":1.0,"Si":1.0}',
                "formation_energy_per_atom": -0.2,
                "density": 5.0,
                "volume": 20.0,
                "nsites": 4,
                "band_gap": 0.0,
                "is_metal": True,
                "symmetry": '{"number":221,"crystal_system":"Cubic"}',
                "is_stable": True,
                "origins": "[]",
                "last_updated": "2026-01-01T00:00:00Z",
                "database_IDs": "{}",
            },
            {
                "material_id": "mp-1",
                "formula_pretty": "FeSi",
                "chemsys": "Fe-Si",
                "elements": '["Fe","Si"]',
                "nelements": 2,
                "theoretical": True,
                "deprecated": False,
                "energy_above_hull": 0.2,
                "composition": '{"Fe":4.0,"Si":4.0}',
                "composition_reduced": '{"Fe":1.0,"Si":1.0}',
                "formation_energy_per_atom": -0.1,
                "density": 5.1,
                "volume": 21.0,
                "nsites": 8,
                "band_gap": 0.1,
                "is_metal": False,
                "symmetry": '{"number":198,"crystal_system":"Cubic"}',
                "is_stable": False,
                "origins": "[]",
                "last_updated": "2026-01-01T00:00:00Z",
                "database_IDs": "{}",
            },
            {
                "material_id": "mp-3",
                "formula_pretty": "Fe2SiO4",
                "chemsys": "Fe-O-Si",
                "elements": '["Fe","O","Si"]',
                "nelements": 3,
                "theoretical": False,
                "deprecated": False,
                "energy_above_hull": 0.5,
                "composition": '{"Fe":2.0,"Si":1.0,"O":4.0}',
                "composition_reduced": '{"Fe":2.0,"Si":1.0,"O":4.0}',
                "formation_energy_per_atom": -0.4,
                "density": 4.0,
                "volume": 30.0,
                "nsites": 7,
                "band_gap": 1.0,
                "is_metal": False,
                "symmetry": '{"number":62,"crystal_system":"Orthorhombic"}',
                "is_stable": False,
                "origins": "[]",
                "last_updated": "2026-01-01T00:00:00Z",
                "database_IDs": "{}",
            },
        ]
    )


def _manifest(row_count: int = 3, column_count: int = 21) -> dict[str, object]:
    return {"table_row_count": row_count, "column_count": column_count}


def test_structured_composition_parsing_and_deterministic_groups() -> None:
    parsed = mc.parse_composition_row(_synthetic_acquired().iloc[0])

    assert parsed.status == "parsed"
    assert parsed.source == "composition_reduced"
    assert parsed.composition is not None
    assert parsed.composition.reduced_formula == "FeSi"
    assert parsed.composition.chemical_system == "Fe-Si"


def test_formula_fallback_when_structured_composition_missing() -> None:
    row = _synthetic_acquired().iloc[0].copy()
    row["composition_reduced"] = np.nan
    row["composition"] = np.nan

    parsed = mc.parse_composition_row(row)

    assert parsed.status == "parsed"
    assert parsed.source == "formula_pretty"
    assert parsed.composition is not None
    assert parsed.composition.reduced_formula == "FeSi"


def test_stoichiometric_entropy_and_fraction_normalization() -> None:
    acquired = _synthetic_acquired()
    analysis, metadata = mc.build_analysis_ready_table(acquired, _manifest())
    row = analysis.loc[analysis["material_id"].eq("mp-1")].iloc[0]

    assert len(analysis) == len(acquired)
    assert row["fraction_sum"] == 1.0
    assert row["composition_fraction_entropy"] == np.log(2)
    assert row["composition_fraction_l2_norm"] == np.sqrt(0.5)
    assert metadata["parse_status_counts"] == {"parsed": 3}


def test_weighted_aggregations_pairwise_mismatch_and_block_fractions() -> None:
    analysis, metadata = mc.build_analysis_ready_table(_synthetic_acquired(), _manifest())
    row = analysis.loc[analysis["material_id"].eq("mp-1")].iloc[0]

    assert row["atomic_number_weighted_mean"] == 20.0
    assert row["atomic_number_minimum"] == 14.0
    assert row["atomic_number_maximum"] == 26.0
    assert row["atomic_number_range"] == 12.0
    assert row["atomic_number_weighted_std"] == 6.0
    assert row["pairwise_mismatch_atomic_number"] == 3.0
    assert row["d_block_fraction"] == 0.5
    assert row["p_block_fraction"] == 0.5
    assert row["transition_metal_fraction"] == 0.5
    assert row["metalloid_fraction"] == 0.5
    assert "atomic_number" in metadata["included_elemental_properties"]


def test_missing_elemental_property_is_excluded_without_zero_fill(monkeypatch) -> None:
    monkeypatch.setitem(
        mc.ELEMENTAL_PROPERTY_SPECS,
        "missing_demo_property",
        {
            "attribute": "not_a_real_pymatgen_property",
            "unit": "unknown",
            "definition": "Synthetic missing-property test.",
            "preferred_for_mismatch": True,
        },
    )

    analysis, metadata = mc.build_analysis_ready_table(_synthetic_acquired(), _manifest())

    assert "missing_demo_property" in metadata["excluded_elemental_properties"]
    assert "missing_demo_property_weighted_mean" not in analysis.columns
    assert "pairwise_mismatch_missing_demo_property" not in analysis.columns


def test_forbidden_features_and_target_are_not_primary_features() -> None:
    analysis, metadata = mc.build_analysis_ready_table(_synthetic_acquired(), _manifest())
    features = mc.primary_feature_columns(analysis)

    assert "energy_above_hull" not in features
    assert "material_id" not in features
    assert "formula_pretty" not in features
    assert "theoretical" not in features
    assert "formation_energy_per_atom" not in features
    assert metadata["forbidden_features_in_primary_features"] == []


def test_theoretical_is_evaluation_only_in_inventory() -> None:
    analysis, metadata = mc.build_analysis_ready_table(_synthetic_acquired(), _manifest())
    inventory = mc.build_descriptor_inventory(analysis, metadata)

    row = inventory.loc[inventory["column_name"].eq("theoretical")].iloc[0]
    assert bool(row["evaluation_only"]) is True
    assert bool(row["primary_feature"]) is False


def test_polymorph_rows_preserved_and_ambiguity_detected() -> None:
    analysis, _ = mc.build_analysis_ready_table(_synthetic_acquired(), _manifest())
    ambiguity, overall = mc.build_composition_ambiguity_summary(analysis)
    fe_si = ambiguity.loc[ambiguity["reduced_formula_group"].eq("FeSi")].iloc[0]

    assert len(analysis) == 3
    assert fe_si["row_count"] == 2
    assert fe_si["unique_descriptor_vector_count"] == 1
    assert bool(fe_si["ambiguity_flag"]) is True
    assert overall["ambiguous_formula_groups"] >= 1


def test_target_suitability_and_zero_heavy_audit() -> None:
    analysis, _ = mc.build_analysis_ready_table(_synthetic_acquired(), _manifest())
    target_summary = mc.build_target_suitability_summary(analysis)

    zero_rate = target_summary.loc[
        target_summary["scope"].eq("overall") & target_summary["metric"].eq("zero_rate"),
        "value",
    ].iloc[0]
    assert zero_rate > 0
    assert "direct_regression_suitability" in set(target_summary["metric"])


def test_descriptor_redundancy_and_split_readiness_outputs() -> None:
    analysis, metadata = mc.build_analysis_ready_table(_synthetic_acquired(), _manifest())
    inventory = mc.build_descriptor_inventory(analysis, metadata)
    redundancy = mc.build_descriptor_redundancy_summary(analysis, inventory)
    ambiguity, overall = mc.build_composition_ambiguity_summary(analysis)
    split = mc.build_split_readiness_summary(analysis, redundancy, overall)

    assert "primary_feature_count" in set(redundancy["metric"])
    assert "overall_modeling_readiness" in set(split["metric"])
    assert "formula_group_split_readiness" in set(split["metric"])
    assert "chemical_system_split_readiness" in set(split["metric"])


def test_structure_group_feasibility_is_audit_only() -> None:
    analysis, metadata = mc.build_analysis_ready_table(_synthetic_acquired(), _manifest())
    inventory = mc.build_descriptor_inventory(analysis, metadata)
    group_inventory = mc.build_group_inventory(analysis)
    features = mc.primary_feature_columns(analysis)

    assert "crystal_system_group" in analysis.columns
    assert "space_group_number_group" in analysis.columns
    assert "crystal_system_group" not in features
    assert "space_group_number_group" not in features
    assert "crystal_system_group" in set(group_inventory["group_type"])
    role = inventory.loc[inventory["column_name"].eq("crystal_system_group"), "column_role"].iloc[0]
    assert role == "evaluation_only"


def test_pipeline_writes_outputs_preserves_source_and_no_path_or_credential(tmp_path: Path) -> None:
    acquired_path = tmp_path / "acquired.csv"
    manifest_path = tmp_path / "manifest.json"
    _synthetic_acquired().to_csv(acquired_path, index=False)
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    before = mc.calculate_file_sha256(acquired_path)

    result = mc.run_descriptor_pipeline(
        acquired_path=acquired_path,
        manifest_path=manifest_path,
        analysis_ready_output=tmp_path / "analysis_ready.csv",
        inventory_output=tmp_path / "descriptor_inventory.csv",
        redundancy_output=tmp_path / "redundancy.csv",
        ambiguity_output=tmp_path / "ambiguity.csv",
        target_output=tmp_path / "target.csv",
        split_output=tmp_path / "split.csv",
        group_inventory_output=tmp_path / "groups.csv",
    )

    assert result["input_sha256_before"] == before
    assert result["input_sha256_after"] == before
    assert result["output_row_count"] == 3
    for path in result["output_sizes"]:
        assert Path(path).exists()
    assert all(
        count == 0
        for count in mc.contains_credential_or_absolute_path(result["output_sizes"]).values()
    )


def test_descriptor_spec_has_no_absolute_path_or_credentials() -> None:
    spec = mc.build_descriptor_spec()
    text = json.dumps(spec)

    assert "MP_API_KEY" not in text
    assert "C:\\" not in text
    assert spec["target_column"] == "energy_above_hull"
    assert "material_id" in spec["forbidden_features"]
