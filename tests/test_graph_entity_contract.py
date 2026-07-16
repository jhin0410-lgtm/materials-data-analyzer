from src.platform_core.scientific_entities import validate_entity_payload


def test_graph_entity_contract_allows_periodic_metadata_without_gnn_claim():
    payload = {
        "entity_id": "graph_demo",
        "entity_type": "GraphEntity",
        "schema_id": "scientific_entity_schema_v2",
        "schema_version": "2.2.2",
        "domain": "materials_graph_synthetic",
        "attributes": {
            "nodes": [{"node_id": "n0", "species": "X"}],
            "edges": [],
            "periodic_edge_metadata": {"included": True, "image_offsets": []},
            "source_entity_ref": "structure_demo",
            "graph_construction_metadata": {"tensor_generation": False, "gnn_execution": False},
        },
    }

    result = validate_entity_payload(payload)

    assert result.valid is True
