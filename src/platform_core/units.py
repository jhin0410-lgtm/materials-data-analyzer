"""Small unit and dimension registry for scientific metadata checks.

The registry intentionally supports only linear conversions and a single
temperature offset pair. It is not a symbolic algebra system and does not parse
free-form unit expressions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite


SUPPORTED_DIMENSIONS = (
    "dimensionless",
    "mass",
    "length",
    "time",
    "temperature",
    "electric_current",
    "amount_of_substance",
    "energy",
    "energy_per_atom",
    "pressure",
    "voltage",
    "current",
    "resistance",
    "capacity",
    "frequency",
    "angle",
    "volume",
    "volume_per_site",
    "volume_per_atom",
    "density",
    "diffusivity",
    "count",
    "category",
)


@dataclass(frozen=True)
class UnitDefinition:
    unit_id: str
    dimension: str
    scale_to_base: float
    offset_to_base: float = 0.0
    base_unit: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if self.dimension not in SUPPORTED_DIMENSIONS:
            raise ValueError(f"unsupported dimension: {self.dimension}")
        if not self.unit_id:
            raise ValueError("unit_id is required")
        if not isfinite(self.scale_to_base) or self.scale_to_base == 0:
            raise ValueError("scale_to_base must be finite and non-zero")
        if not isfinite(self.offset_to_base):
            raise ValueError("offset_to_base must be finite")

    def to_base(self, value: float) -> float:
        return (float(value) * self.scale_to_base) + self.offset_to_base

    def from_base(self, value: float) -> float:
        return (float(value) - self.offset_to_base) / self.scale_to_base

    def to_dict(self) -> dict[str, object]:
        return {
            "unit_id": self.unit_id,
            "dimension": self.dimension,
            "scale_to_base": self.scale_to_base,
            "offset_to_base": self.offset_to_base,
            "base_unit": self.base_unit,
            "description": self.description,
        }


@dataclass
class UnitRegistry:
    _units: dict[str, UnitDefinition] = field(default_factory=dict)

    def register(self, unit: UnitDefinition) -> None:
        if unit.unit_id in self._units:
            raise ValueError(f"duplicate unit_id: {unit.unit_id}")
        self._units[unit.unit_id] = unit

    def get(self, unit_id: str) -> UnitDefinition:
        try:
            return self._units[unit_id]
        except KeyError as exc:
            raise KeyError(f"unknown unit_id: {unit_id}") from exc

    def list_units(self, dimension: str | None = None) -> list[UnitDefinition]:
        units = self._units.values()
        if dimension is not None:
            units = [unit for unit in units if unit.dimension == dimension]
        return [self._units[key] for key in sorted(unit.unit_id for unit in units)]

    def snapshot(self, dimension: str | None = None) -> list[dict[str, object]]:
        return [unit.to_dict() for unit in self.list_units(dimension)]

    def compatible(self, from_unit: str, to_unit: str) -> bool:
        return self.get(from_unit).dimension == self.get(to_unit).dimension

    def convert_value(self, value: float, from_unit: str, to_unit: str) -> float:
        source = self.get(from_unit)
        target = self.get(to_unit)
        if source.dimension != target.dimension:
            raise ValueError(f"incompatible units: {from_unit} -> {to_unit}")
        if not isfinite(float(value)):
            raise ValueError("value must be finite")
        return target.from_base(source.to_base(float(value)))


def build_default_unit_registry() -> UnitRegistry:
    registry = UnitRegistry()

    def add(unit_id: str, dimension: str, scale: float, offset: float = 0.0, base: str = "", description: str = "") -> None:
        registry.register(UnitDefinition(unit_id, dimension, scale, offset, base, description))

    add("kg", "mass", 1.0, base="kg")
    add("g", "mass", 1e-3, base="kg")

    add("m", "length", 1.0, base="m")
    add("cm", "length", 1e-2, base="m")
    add("mm", "length", 1e-3, base="m")
    add("um", "length", 1e-6, base="m")
    add("nm", "length", 1e-9, base="m")
    add("angstrom", "length", 1e-10, base="m")

    add("s", "time", 1.0, base="s")
    add("min", "time", 60.0, base="s")
    add("h", "time", 3600.0, base="s")
    add("day", "time", 86400.0, base="s")

    add("K", "temperature", 1.0, base="K")
    add("degC", "temperature", 1.0, 273.15, base="K")

    add("Pa", "pressure", 1.0, base="Pa")
    add("kPa", "pressure", 1e3, base="Pa")
    add("MPa", "pressure", 1e6, base="Pa")
    add("GPa", "pressure", 1e9, base="Pa")

    add("J", "energy", 1.0, base="J")
    add("eV", "energy", 1.602176634e-19, base="J")
    add("eV/atom", "energy_per_atom", 1.0, base="eV/atom")

    add("V", "voltage", 1.0, base="V")
    add("A", "current", 1.0, base="A")
    add("ohm", "resistance", 1.0, base="ohm")
    add("Ah", "capacity", 1.0, base="Ah")
    add("mAh", "capacity", 1e-3, base="Ah")
    add("Hz", "frequency", 1.0, base="Hz")
    add("rad", "angle", 1.0, base="rad")
    add("degree", "angle", 0.017453292519943295, base="rad")
    add("angstrom^3", "volume", 1.0, base="angstrom^3")
    add("angstrom^3/site", "volume_per_site", 1.0, base="angstrom^3/site")
    add("angstrom^3/atom", "volume_per_atom", 1.0, base="angstrom^3/atom")
    add("g/cm^3", "density", 1.0, base="g/cm^3")
    add("m^2/s", "diffusivity", 1.0, base="m^2/s")
    add("fraction", "dimensionless", 1.0, base="fraction")
    add("unitless", "dimensionless", 1.0, base="unitless")
    add("count", "count", 1.0, base="count")
    add("category", "category", 1.0, base="category")
    add("percent", "dimensionless", 0.01, base="fraction")

    return registry
