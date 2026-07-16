import json

from src.platform_core.materials_project_adapters import (
    MaterialsProjectStructureAdapter,
    MaterialsProjectSummaryAdapter,
    MaterialsProjectTargetAdapter,
    structure_entity_record,
)


def _fixture():
    return json.loads(open("configs/examples/materials_project_structure_entity_conversion.json", encoding="utf-8").read())


def test_summary_target_and_structure_adapters_round_trip_json_safe():
    fixture = _fixture()
    summary = fixture["summary"]
    composition = MaterialsProjectSummaryAdapter().to_composition_entity(summary)
    structure = MaterialsProjectStructureAdapter().to_crystal_structure_entity(
        material_id=fixture["material_id"],
        structure=fixture["structure"],
        summary_row=summary,
    )
    quantity = MaterialsProjectTargetAdapter().to_quantity(summary)
    record = structure_entity_record(structure)

    assert composition.entity_type == "MaterialCompositionEntity"
    assert structure.entity_type == "CrystalStructureEntity"
    assert record["entity_type"] == "CrystalStructureEntity"
    assert record["checksum_sha256"]
    assert quantity.value is not None
    assert quantity.value.original_unit == "eV/atom"
    assert quantity.value.uncertainty.kind == "unavailable"
    json.dumps(record, sort_keys=True)


def test_adapter_does_not_persist_runtime_object_repr():
    fixture = _fixture()
    structure = MaterialsProjectStructureAdapter().to_crystal_structure_entity(
        material_id=fixture["material_id"],
        structure=fixture["structure"],
        summary_row=fixture["summary"],
    )
    payload = json.dumps(structure.to_dict(), sort_keys=True)

    assert "pymatgen" not in payload.lower()
    assert "object at 0x" not in payload
    assert "__class__" not in payload
