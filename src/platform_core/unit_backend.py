"""Unit backend abstraction over the existing builtin unit registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .units import UnitDefinition, UnitRegistry, build_default_unit_registry


@dataclass(frozen=True)
class UnitParseResult:
    unit_id: str
    dimension: str
    canonical_unit: str
    backend: str
    backend_version: str

    def to_dict(self) -> dict[str, str]:
        return {
            "unit_id": self.unit_id,
            "dimension": self.dimension,
            "canonical_unit": self.canonical_unit,
            "backend": self.backend,
            "backend_version": self.backend_version,
        }


class UnitBackend(Protocol):
    backend_id: str
    backend_version: str

    def parse_unit(self, unit: str) -> UnitParseResult: ...

    def dimensionality(self, unit: str) -> str: ...

    def compatible(self, from_unit: str, to_unit: str) -> bool: ...

    def convert(self, value: float, from_unit: str, to_unit: str) -> float: ...

    def normalize(self, value: float, unit: str) -> tuple[float, str]: ...

    def serialize_unit(self, unit: str) -> dict[str, str]: ...


class BuiltinUnitBackend:
    backend_id = "builtin_unit_registry"
    backend_version = "2.2.2"

    def __init__(self, registry: UnitRegistry | None = None) -> None:
        self.registry = registry or build_default_unit_registry()

    def _definition(self, unit: str) -> UnitDefinition:
        return self.registry.get(unit)

    def parse_unit(self, unit: str) -> UnitParseResult:
        definition = self._definition(unit)
        return UnitParseResult(
            unit_id=definition.unit_id,
            dimension=definition.dimension,
            canonical_unit=definition.base_unit or definition.unit_id,
            backend=self.backend_id,
            backend_version=self.backend_version,
        )

    def dimensionality(self, unit: str) -> str:
        return self._definition(unit).dimension

    def compatible(self, from_unit: str, to_unit: str) -> bool:
        return self.registry.compatible(from_unit, to_unit)

    def convert(self, value: float, from_unit: str, to_unit: str) -> float:
        return self.registry.convert_value(value, from_unit, to_unit)

    def normalize(self, value: float, unit: str) -> tuple[float, str]:
        parsed = self.parse_unit(unit)
        return self.convert(value, unit, parsed.canonical_unit), parsed.canonical_unit

    def serialize_unit(self, unit: str) -> dict[str, str]:
        return self.parse_unit(unit).to_dict()


class PintUnitBackend:
    """Optional Pint adapter.

    Pint is not a required dependency. This class is only usable when Pint is
    installed in the local environment, and no arbitrary unit definition file is
    loaded.
    """

    backend_id = "optional_pint_backend"

    def __init__(self) -> None:
        try:
            import pint  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Pint is not installed; use BuiltinUnitBackend") from exc

        self._pint = pint
        self._ureg = pint.UnitRegistry()
        self.backend_version = getattr(pint, "__version__", "unknown")

    def parse_unit(self, unit: str) -> UnitParseResult:
        parsed = self._ureg.Unit(unit)
        dimensionality = str(parsed.dimensionality)
        return UnitParseResult(unit, dimensionality, str(parsed.to_base_units()), self.backend_id, self.backend_version)

    def dimensionality(self, unit: str) -> str:
        return self.parse_unit(unit).dimension

    def compatible(self, from_unit: str, to_unit: str) -> bool:
        return self._ureg.Unit(from_unit).dimensionality == self._ureg.Unit(to_unit).dimensionality

    def convert(self, value: float, from_unit: str, to_unit: str) -> float:
        return float((value * self._ureg.Unit(from_unit)).to(to_unit).magnitude)

    def normalize(self, value: float, unit: str) -> tuple[float, str]:
        quantity = value * self._ureg.Unit(unit)
        base = quantity.to_base_units()
        return float(base.magnitude), str(base.units)

    def serialize_unit(self, unit: str) -> dict[str, str]:
        return self.parse_unit(unit).to_dict()


def pint_available() -> bool:
    try:
        import pint  # noqa: F401  # type: ignore[import-not-found]
    except ImportError:
        return False
    return True


def unit_backend_decision() -> dict[str, object]:
    return {
        "decision": "optional_pint_backend",
        "default_backend": "builtin_unit_registry",
        "pint_available": pint_available(),
        "dependency_added": False,
        "rationale": [
            "existing unit behavior remains backed by src.platform_core.units",
            "compound symbolic unit parsing is not yet required by current case studies",
            "Pint can be used as a controlled optional adapter when installed",
        ],
    }
