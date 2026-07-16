import pytest

from src.platform_core.scientific_entities import ScientificEntity, entity_type_schemas, validate_entity_payload


def test_material_composition_entity_contract_validates_required_attributes():
    entity = ScientificEntity(
        entity_id="composition_fe_si",
        entity_type="MaterialCompositionEntity",
        schema_id="scientific_entity_schema_v2",
        schema_version="2.2.2",
        domain="materials",
        attributes={
            "formula": "FeSi",
            "elements": ["Fe", "Si"],
            "stoichiometric_amounts": {"Fe": 1, "Si": 1},
            "atomic_fractions": {"Fe": 0.5, "Si": 0.5},
        },
    )

    result = validate_entity_payload(entity.to_dict())

    assert result.valid is True
    assert entity_type_schemas()["MaterialCompositionEntity"]["purpose"].startswith("Composition")


def test_unknown_entity_type_and_non_json_attribute_rejected():
    with pytest.raises(ValueError, match="unsupported entity_type"):
        ScientificEntity(
            entity_id="bad",
            entity_type="UnknownEntity",
            schema_id="scientific_entity_schema_v2",
            schema_version="2.2.2",
            domain="materials",
        )
    with pytest.raises(ValueError, match="unsupported JSON"):
        ScientificEntity(
            entity_id="bad_callable",
            entity_type="MaterialCompositionEntity",
            schema_id="scientific_entity_schema_v2",
            schema_version="2.2.2",
            domain="materials",
            attributes={"formula": lambda: "Fe"},
        )
