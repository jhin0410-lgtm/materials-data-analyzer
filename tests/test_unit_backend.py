import pytest

from src.platform_core.unit_backend import BuiltinUnitBackend, PintUnitBackend, pint_available, unit_backend_decision


def test_builtin_unit_backend_converts_linear_and_offset_units():
    backend = BuiltinUnitBackend()

    assert backend.convert(1.0, "nm", "angstrom") == pytest.approx(10.0)
    assert backend.normalize(25.0, "degC") == pytest.approx((298.15, "K"))
    assert backend.compatible("degree", "rad") is True


def test_unit_backend_decision_keeps_pint_optional():
    decision = unit_backend_decision()

    assert decision["decision"] == "optional_pint_backend"
    assert decision["default_backend"] == "builtin_unit_registry"
    assert decision["dependency_added"] is False


def test_optional_pint_backend_parity_if_installed():
    if not pint_available():
        pytest.skip("Pint not installed in this environment")
    backend = PintUnitBackend()
    assert backend.convert(1.0, "nanometer", "angstrom") == pytest.approx(10.0)
