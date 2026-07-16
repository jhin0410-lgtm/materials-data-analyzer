from src.platform_core.schema_evolution import build_default_migration_registry


def test_material_composition_schema_migration_is_deterministic_and_lossless():
    registry = build_default_migration_registry()
    payload = {
        "entity_id": "composition_demo",
        "entity_type": "MaterialCompositionEntity",
        "schema_id": "scientific_entity_schema_v2",
        "schema_version": "1",
        "domain": "materials",
        "attributes": {"formula": "FeSi", "elements": ["Fe", "Si"], "amounts": {"Fe": 1, "Si": 1}, "atomic_fractions": {"Fe": 0.5, "Si": 0.5}},
    }

    first = registry.migrate(payload, schema_id="MaterialCompositionEntity", from_version="1", to_version="2")
    second = registry.migrate(payload, schema_id="MaterialCompositionEntity", from_version="1", to_version="2")

    assert first.status == "migrated"
    assert first.payload == second.payload
    assert "stoichiometric_amounts" in first.payload["attributes"]
    assert "amounts" not in first.payload["attributes"]


def test_future_or_unknown_schema_migration_is_rejected():
    registry = build_default_migration_registry()
    result = registry.migrate({}, schema_id="MaterialCompositionEntity", from_version="9", to_version="10")

    assert result.status == "unsupported"
