"""Deterministic schema migration helpers for JSON-safe records."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


MigrationCallable = Callable[[Mapping[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class SchemaIdentifier:
    schema_id: str
    version: str

    def key(self) -> tuple[str, str]:
        return (self.schema_id, self.version)

    def to_dict(self) -> dict[str, str]:
        return {"schema_id": self.schema_id, "version": self.version}


@dataclass(frozen=True)
class SchemaVersion:
    schema_id: str
    version: str
    status: str = "supported"

    def to_identifier(self) -> SchemaIdentifier:
        return SchemaIdentifier(self.schema_id, self.version)


@dataclass(frozen=True)
class MigrationStep:
    source: SchemaIdentifier
    target: SchemaIdentifier
    migration_id: str
    description: str
    migrate: MigrationCallable

    def __post_init__(self) -> None:
        if self.migrate.__module__ != __name__:
            raise ValueError("schema migrations must be code-registered in schema_evolution")


@dataclass(frozen=True)
class MigrationResult:
    status: str
    source: SchemaIdentifier
    target: SchemaIdentifier
    applied_steps: tuple[str, ...]
    payload: Mapping[str, Any]
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "applied_steps": list(self.applied_steps),
            "payload": dict(self.payload),
            "errors": list(self.errors),
        }


@dataclass
class MigrationRegistry:
    _steps: dict[tuple[tuple[str, str], tuple[str, str]], MigrationStep] = field(default_factory=dict)

    def register(self, step: MigrationStep) -> None:
        key = (step.source.key(), step.target.key())
        if key in self._steps:
            raise ValueError(f"duplicate migration step: {step.migration_id}")
        self._steps[key] = step

    def migrate(self, payload: Mapping[str, Any], *, schema_id: str, from_version: str, to_version: str) -> MigrationResult:
        source = SchemaIdentifier(schema_id, from_version)
        target = SchemaIdentifier(schema_id, to_version)
        if from_version == to_version:
            return MigrationResult("already_current", source, target, (), dict(payload))
        current = source
        current_payload: dict[str, Any] = dict(payload)
        applied: list[str] = []
        seen: set[tuple[str, str]] = set()
        protected_fields = {"entity_id", "entity_type", "schema_id", "quantity_id"}
        while current.version != target.version:
            if current.key() in seen:
                return MigrationResult("failed", source, target, tuple(applied), current_payload, ("migration_cycle",))
            seen.add(current.key())
            candidates = [step for (src, _), step in self._steps.items() if src == current.key() and step.target.schema_id == schema_id]
            if not candidates:
                return MigrationResult("unsupported", source, target, tuple(applied), current_payload, (f"no_step_from:{current.version}",))
            step = sorted(candidates, key=lambda item: item.target.version)[0]
            before_keys = set(current_payload)
            current_payload = step.migrate(current_payload)
            if not set(current_payload).issuperset(before_keys & protected_fields):
                return MigrationResult("failed", source, target, tuple(applied), current_payload, ("required_field_loss",))
            applied.append(step.migration_id)
            current = step.target
            if current.version > target.version:
                return MigrationResult("unsupported", source, target, tuple(applied), current_payload, (f"overshot:{current.version}",))
        return MigrationResult("migrated", source, target, tuple(applied), current_payload)

    def snapshot(self) -> list[dict[str, Any]]:
        rows = []
        for step in sorted(self._steps.values(), key=lambda item: item.migration_id):
            rows.append(
                {
                    "migration_id": step.migration_id,
                    "source": step.source.to_dict(),
                    "target": step.target.to_dict(),
                    "description": step.description,
                }
            )
        return rows


def _migrate_material_composition_v1_to_v2(payload: Mapping[str, Any]) -> dict[str, Any]:
    migrated = dict(payload)
    migrated["schema_version"] = "2"
    attributes = dict(migrated.get("attributes", {}))
    if "amounts" in attributes and "stoichiometric_amounts" not in attributes:
        attributes["stoichiometric_amounts"] = attributes.pop("amounts")
    attributes.setdefault("normalization_status", "declared_or_derived")
    migrated["attributes"] = attributes
    return migrated


def _migrate_scientific_quantity_v1_to_v2(payload: Mapping[str, Any]) -> dict[str, Any]:
    migrated = dict(payload)
    migrated["schema_version"] = "2"
    if "unit" in migrated and "original_unit" not in migrated:
        migrated["original_unit"] = migrated["unit"]
    migrated.setdefault("validity_status", "valid")
    migrated.setdefault("conversion_history", [])
    return migrated


def build_default_migration_registry() -> MigrationRegistry:
    registry = MigrationRegistry()
    registry.register(
        MigrationStep(
            source=SchemaIdentifier("MaterialCompositionEntity", "1"),
            target=SchemaIdentifier("MaterialCompositionEntity", "2"),
            migration_id="material_composition_entity_v1_to_v2",
            description="Rename amounts to stoichiometric_amounts and add normalization status.",
            migrate=_migrate_material_composition_v1_to_v2,
        )
    )
    registry.register(
        MigrationStep(
            source=SchemaIdentifier("ScientificQuantity", "1"),
            target=SchemaIdentifier("ScientificQuantity", "2"),
            migration_id="scientific_quantity_v1_to_v2",
            description="Preserve original_unit and add validity/conversion metadata.",
            migrate=_migrate_scientific_quantity_v1_to_v2,
        )
    )
    return registry
