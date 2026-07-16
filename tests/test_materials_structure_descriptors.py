import json

import pytest

from src.analyzers.materials_structure_features import (
    build_radius_graph,
    build_structure_descriptor_table,
    descriptor_coverage_summary,
    descriptor_row,
    load_structure_entities,
    structure_descriptor_definitions,
)
from src.platform_core.materials_project_adapters import MaterialsProjectStructureAdapter


def _entity():
    fixture = json.loads(open("configs/examples/materials_project_structure_entity_conversion.json", encoding="utf-8").read())
    return MaterialsProjectStructureAdapter().to_crystal_structure_entity(
        material_id=fixture["material_id"],
        structure=fixture["structure"],
        summary_row=fixture["summary"],
    )


def test_descriptor_definitions_mark_candidates_and_forbid_target_access():
    definitions = structure_descriptor_definitions()

    assert len(definitions) == 12
    assert all(item["target_access_policy"] == "forbidden" for item in definitions)
    assert "structure_volume_per_atom" in {item["descriptor_id"] for item in definitions}


def test_structure_descriptors_are_deterministic_and_target_free(tmp_path):
    entity = _entity()
    path = tmp_path / "entities.jsonl"
    path.write_text(json.dumps(entity.to_dict()) + "\n", encoding="utf-8")
    entities = load_structure_entities(path)

    first = build_structure_descriptor_table(entities)
    second = build_structure_descriptor_table(entities)

    assert first.to_dict("records") == second.to_dict("records")
    assert first.loc[0, "structure_volume_per_atom"] > 0
    assert bool(first.loc[0, "target_accessed"]) is False
    coverage = descriptor_coverage_summary(first)
    assert any(row["descriptor_id"] == "nearest_neighbor_distance_mean" and row["status"] == "available" for row in coverage)


def test_descriptor_rejects_target_like_structure_attributes():
    entity = _entity()
    polluted = type(entity)(
        entity_id=entity.entity_id,
        entity_type=entity.entity_type,
        schema_id=entity.schema_id,
        schema_version=entity.schema_version,
        domain=entity.domain,
        attributes={**entity.attributes, "energy_above_hull": 0.0},
        quantity_fields=entity.quantity_fields,
    )

    with pytest.raises(ValueError, match="target-like"):
        descriptor_row(polluted)


def test_periodic_neighbor_distance_matches_hand_calculation():
    entity = _entity()
    graph = build_radius_graph(entity)
    nearest = min(edge["distance_angstrom"] for edge in graph["edges"])

    assert nearest == pytest.approx((3 ** 0.5) * 1.4)
