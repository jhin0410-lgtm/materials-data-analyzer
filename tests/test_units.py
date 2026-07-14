import math

import pytest

from src.platform_core.units import UnitDefinition, UnitRegistry, build_default_unit_registry


def test_unit_registry_converts_supported_linear_and_offset_units():
    registry = build_default_unit_registry()

    assert registry.convert_value(25, "degC", "K") == pytest.approx(298.15)
    assert registry.convert_value(1, "nm", "angstrom") == pytest.approx(10)
    assert registry.convert_value(50, "percent", "fraction") == pytest.approx(0.5)


def test_unit_registry_rejects_incompatible_or_unknown_units():
    registry = build_default_unit_registry()

    with pytest.raises(ValueError):
        registry.convert_value(1, "nm", "K")
    with pytest.raises(KeyError):
        registry.convert_value(1, "nm", "parsec")


def test_unit_registry_duplicate_and_invalid_dimension_rejected():
    registry = UnitRegistry()
    registry.register(UnitDefinition("x", "length", 1.0))

    with pytest.raises(ValueError):
        registry.register(UnitDefinition("x", "length", 1.0))
    with pytest.raises(ValueError):
        UnitDefinition("bad", "unsupported", 1.0)


def test_unit_registry_snapshot_deterministic():
    registry = build_default_unit_registry()

    ids = [unit["unit_id"] for unit in registry.snapshot()]
    assert ids == sorted(ids)
    assert all(math.isfinite(unit["scale_to_base"]) for unit in registry.snapshot())
