from src.platform_core.quantities import build_quantity_value
from src.platform_core.unit_backend import BuiltinUnitBackend


def test_structure_units_are_literal_supported_units():
    backend = BuiltinUnitBackend()

    assert backend.parse_unit("angstrom").dimension == "length"
    assert backend.parse_unit("angstrom^3").dimension == "volume"
    assert backend.parse_unit("angstrom^3/atom").dimension == "volume_per_atom"
    assert backend.parse_unit("g/cm^3").dimension == "density"
    assert backend.parse_unit("eV/atom").dimension == "energy_per_atom"
    assert backend.parse_unit("count").dimension == "count"
    assert backend.parse_unit("unitless").dimension == "dimensionless"
    assert backend.parse_unit("category").dimension == "category"
    assert build_quantity_value(value=1.2, unit="angstrom^3").original_unit == "angstrom^3"
