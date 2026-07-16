from src.platform_core.scientific_operator_registry import (
    ScientificOperatorMetadata,
    ScientificOperatorRegistry,
    build_default_scientific_operator_registry,
)


def test_default_operator_registry_has_selected_operators_only():
    registry = build_default_scientific_operator_registry()
    snapshot = registry.snapshot()
    operator_ids = {item["operator_id"] for item in snapshot}

    assert registry.validate()["valid"] is True
    assert len(snapshot) == 9
    assert "mp_structure_to_crystal_entity_v1" in operator_ids
    assert "crystal_structure_to_descriptor_summary_v1" in operator_ids
    assert "crystal_structure_to_radius_graph_v1" in operator_ids
    assert "structure_snapshot_alignment_check_v1" in operator_ids
    assert all(item["network_policy"] == "no_network" for item in snapshot)
    assert all("callable" not in item for item in snapshot)


def test_operator_registry_rejects_duplicate_and_unknown():
    registry = ScientificOperatorRegistry()
    operator = ScientificOperatorMetadata(
        operator_id="example_operator",
        operator_version="1",
        input_entity_types=("A",),
        output_types=("B",),
        required_fields=("x",),
        side_effect_policy="none",
        network_policy="no_network",
        uncertainty_policy="unavailable_if_source_not_provided",
        provenance_policy="record",
        deterministic=True,
        bounded_input_policy="small",
    )
    registry.register(operator)
    try:
        registry.register(operator)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("expected duplicate rejection")
    try:
        registry.get("missing")
    except KeyError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("expected unknown operator rejection")
