import pytest

from src.platform_core.entity_serialization import deserialize_entity_record, serialize_entity, validate_record
from src.platform_core.scientific_entities import ScientificEntity


def _entity() -> ScientificEntity:
    return ScientificEntity(
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


def test_entity_serialization_checksum_is_deterministic_and_round_trips():
    first = serialize_entity(_entity())
    second = serialize_entity(_entity())

    assert first["checksum_sha256"] == second["checksum_sha256"]
    assert validate_record(first)["valid"] is True
    assert deserialize_entity_record(first).to_dict() == _entity().to_dict()


def test_newer_or_tampered_record_rejected():
    record = serialize_entity(_entity())
    record["schema_version"] = "9.9"
    assert validate_record(record)["valid"] is False

    tampered = serialize_entity(_entity())
    tampered["record"] = dict(tampered["record"])
    tampered["record"]["domain"] = "changed"
    assert "checksum_mismatch" in validate_record(tampered)["errors"]


def test_record_does_not_store_live_python_object():
    record = serialize_entity(_entity())
    assert "record" in record
    with pytest.raises(ValueError):
        ScientificEntity(
            entity_id="bad",
            entity_type="MaterialCompositionEntity",
            schema_id="scientific_entity_schema_v2",
            schema_version="2.2.2",
            domain="materials",
            attributes={"handle": object()},
        )
