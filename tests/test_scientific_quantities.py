import pytest

from src.platform_core.quantities import QuantityArrayMetadata, build_quantity_value, quantity_from_payload, validate_quantity_payload


def test_quantity_preserves_original_and_canonical_units():
    quantity = build_quantity_value(value=1.5406, unit="angstrom")

    assert quantity.original_unit == "angstrom"
    assert quantity.canonical_unit == "m"
    assert quantity.dimension == "length"
    assert quantity.canonical_value == pytest.approx(1.5406e-10)


def test_large_array_requires_relative_artifact_reference():
    with pytest.raises(ValueError, match="relative"):
        QuantityArrayMetadata(
            artifact_ref="C:/tmp/array.npy",
            shape=(10,),
            dtype="float64",
            unit="m",
            checksum_sha256="abc",
        )


def test_quantity_payload_validation_and_legacy_parse():
    payload = {
        "schema_version": "2.2.2",
        "quantity_id": "q",
        "value": {"value": 25, "original_unit": "degC", "canonical_value": 298.15, "canonical_unit": "K", "dimension": "temperature"},
        "array_metadata": None,
    }

    assert validate_quantity_payload(payload)["valid"] is True
    parsed = quantity_from_payload(payload)
    assert parsed.value is not None
    assert parsed.value.canonical_value == pytest.approx(298.15)
