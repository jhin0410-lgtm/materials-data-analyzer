import json

from src.platform_core.materials_project_adapters import (
    MaterialsProjectStructureAdapter,
    crystal_basic_geometry_summary,
    validate_crystal_structure_entity,
)


def _entity_from_fixture():
    fixture = json.loads(open("configs/examples/materials_project_structure_entity_conversion.json", encoding="utf-8").read())
    return MaterialsProjectStructureAdapter().to_crystal_structure_entity(
        material_id=fixture["material_id"],
        structure=fixture["structure"],
        summary_row=fixture["summary"],
    )


def test_valid_structure_integrity_and_geometry_summary():
    entity = _entity_from_fixture()
    result = validate_crystal_structure_entity(entity)
    geometry = crystal_basic_geometry_summary(entity)

    assert result["status"] == "valid"
    assert geometry["site_count"] == 2
    assert geometry["predictive_feature_artifact"] is False
    assert geometry["cell_volume_angstrom3"] > 0


def test_invalid_lattice_rejected():
    fixture = json.loads(open("configs/examples/materials_project_structure_entity_conversion.json", encoding="utf-8").read())
    fixture["structure"]["lattice"]["matrix"][2] = [0.0, 0.0, 0.0]
    entity = MaterialsProjectStructureAdapter().to_crystal_structure_entity(
        material_id=fixture["material_id"],
        structure=fixture["structure"],
        summary_row=fixture["summary"],
    )
    result = validate_crystal_structure_entity(entity)

    assert result["status"] == "invalid"
    assert "non_positive_lattice_volume" in result["findings"]
