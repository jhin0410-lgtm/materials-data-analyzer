import json

from src.platform_core.materials_project_adapters import MaterialsProjectStructureAdapter, assess_crystal_graph_eligibility


def test_graph_eligibility_does_not_construct_graph():
    fixture = json.loads(open("configs/examples/materials_project_structure_entity_conversion.json", encoding="utf-8").read())
    entity = MaterialsProjectStructureAdapter().to_crystal_structure_entity(
        material_id=fixture["material_id"],
        structure=fixture["structure"],
        summary_row=fixture["summary"],
    )

    result = assess_crystal_graph_eligibility(entity)

    assert result["status"] == "graph_adapter_candidate"
    assert result["graph_constructed"] is False
    assert result["gnn_ready"] is False
    assert result["claim"] == "graph-construction contract eligibility only"
