import json

import pytest

from src.analyzers.materials_structure_features import RadiusGraphConfig, build_radius_graph
from src.platform_core.materials_project_adapters import MaterialsProjectStructureAdapter


def _entity():
    fixture = json.loads(open("configs/examples/materials_project_structure_entity_conversion.json", encoding="utf-8").read())
    return MaterialsProjectStructureAdapter().to_crystal_structure_entity(
        material_id=fixture["material_id"],
        structure=fixture["structure"],
        summary_row=fixture["summary"],
    )


def test_radius_graph_is_deterministic_and_not_gnn_input():
    entity = _entity()

    first = build_radius_graph(entity)
    second = build_radius_graph(entity)

    assert first["checksum_sha256"] == second["checksum_sha256"]
    assert first["graph_construction_metadata"]["target_values_included"] is False
    assert first["graph_construction_metadata"]["gnn_input_ready"] is False
    assert first["nodes"][0]["species"] == "Fe"
    assert first["edges"] == sorted(first["edges"], key=lambda edge: (edge["source"], edge["distance_angstrom"], edge["target"], edge["periodic_image"]))


def test_radius_graph_enforces_max_edge_guard():
    entity = _entity()

    with pytest.raises(ValueError, match="max_edges"):
        build_radius_graph(entity, RadiusGraphConfig(cutoff_angstrom=4.0, max_edges=1))
