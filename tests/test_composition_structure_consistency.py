import json

from src.platform_core.materials_project_adapters import (
    MaterialsProjectStructureAdapter,
    MaterialsProjectSummaryAdapter,
    composition_structure_consistency,
)


def test_reduced_composition_match():
    fixture = json.loads(open("configs/examples/materials_project_structure_entity_conversion.json", encoding="utf-8").read())
    composition = MaterialsProjectSummaryAdapter().to_composition_entity(fixture["summary"])
    structure = MaterialsProjectStructureAdapter().to_crystal_structure_entity(
        material_id=fixture["material_id"],
        structure=fixture["structure"],
        summary_row=fixture["summary"],
    )

    result = composition_structure_consistency(composition, structure)

    assert result["status"] == "reduced_match"
    assert result["interpretation"] == "consistency_check_not_phase_or_causality_claim"


def test_composition_mismatch_is_finding_not_causality_claim():
    fixture = json.loads(open("configs/examples/materials_project_structure_entity_conversion.json", encoding="utf-8").read())
    fixture["summary"]["composition_reduced"] = {"Fe": 2.0, "Si": 1.0}
    composition = MaterialsProjectSummaryAdapter().to_composition_entity(fixture["summary"])
    structure = MaterialsProjectStructureAdapter().to_crystal_structure_entity(
        material_id=fixture["material_id"],
        structure=fixture["structure"],
        summary_row=fixture["summary"],
    )

    result = composition_structure_consistency(composition, structure)

    assert result["status"] == "mismatch"
    assert "causality" in result["interpretation"]
