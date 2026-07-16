"""JSON-safe scientific entity records for platform metadata.

The classes in this module are runtime helpers for versioned records. They are
not persisted as live Python objects and they intentionally reject callables,
file handles, module references, and oversized inline payloads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping


ENTITY_SCHEMA_VERSION = "2.2.2"
MAX_METADATA_BYTES = 64_000
SUPPORTED_ENTITY_TYPES = (
    "MaterialCompositionEntity",
    "CrystalStructureEntity",
    "MeasurementSeriesEntity",
    "StateEntity",
    "TrajectoryEntity",
    "GraphEntity",
)
VALIDATION_STATUSES = ("valid", "warning", "invalid")


def _safe_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    if any(part in value for part in ("..", "/", "\\")):
        raise ValueError(f"{field_name} must be an identifier, not a path")
    return value.strip()


def _json_safe(value: Any, *, location: str = "value") -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item, location=f"{location}.{key}") for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple):
        return [_json_safe(item, location=f"{location}[]") for item in value]
    if isinstance(value, list):
        return [_json_safe(item, location=f"{location}[]") for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"{location} contains unsupported JSON value type: {type(value).__name__}")


def _assert_small_json(payload: Mapping[str, Any]) -> None:
    size = len(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    if size > MAX_METADATA_BYTES:
        raise ValueError(f"entity metadata exceeds {MAX_METADATA_BYTES} bytes; use an artifact reference")


@dataclass(frozen=True)
class EntityIdentity:
    entity_id: str
    entity_type: str
    domain: str

    def __post_init__(self) -> None:
        _safe_identifier(self.entity_id, "entity_id")
        if self.entity_type not in SUPPORTED_ENTITY_TYPES:
            raise ValueError(f"unsupported entity_type: {self.entity_type}")
        _safe_identifier(self.domain, "domain")

    def to_dict(self) -> dict[str, str]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "domain": self.domain,
        }


@dataclass(frozen=True)
class EntityReference:
    entity_id: str
    entity_type: str
    checksum_sha256: str | None = None

    def __post_init__(self) -> None:
        _safe_identifier(self.entity_id, "entity_id")
        if self.entity_type not in SUPPORTED_ENTITY_TYPES:
            raise ValueError(f"unsupported entity_type: {self.entity_type}")

    def to_dict(self) -> dict[str, str | None]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "checksum_sha256": self.checksum_sha256,
        }


@dataclass(frozen=True)
class EntitySchemaReference:
    schema_id: str
    schema_version: str

    def __post_init__(self) -> None:
        _safe_identifier(self.schema_id, "schema_id")
        _safe_identifier(self.schema_version, "schema_version")

    def to_dict(self) -> dict[str, str]:
        return {"schema_id": self.schema_id, "schema_version": self.schema_version}


@dataclass(frozen=True)
class EntityValidationResult:
    valid: bool
    validation_status: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.validation_status not in VALIDATION_STATUSES:
            raise ValueError(f"unsupported validation_status: {self.validation_status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "validation_status": self.validation_status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ScientificEntity:
    entity_id: str
    entity_type: str
    schema_id: str
    schema_version: str
    domain: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    quantity_fields: Mapping[str, Any] = field(default_factory=dict)
    provenance_refs: tuple[str, ...] = ()
    parent_entity_refs: tuple[EntityReference, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    created_by: str = "platform_core"
    validation_status: str = "valid"

    def __post_init__(self) -> None:
        EntityIdentity(self.entity_id, self.entity_type, self.domain)
        EntitySchemaReference(self.schema_id, self.schema_version)
        if self.validation_status not in VALIDATION_STATUSES:
            raise ValueError(f"unsupported validation_status: {self.validation_status}")
        attributes = _json_safe(self.attributes, location="attributes")
        quantity_fields = _json_safe(self.quantity_fields, location="quantity_fields")
        payload = {
            "attributes": attributes,
            "quantity_fields": quantity_fields,
            "provenance_refs": list(self.provenance_refs),
            "artifact_refs": list(self.artifact_refs),
        }
        _assert_small_json(payload)
        for ref in self.artifact_refs:
            if ref.startswith("/") or ":/" in ref or ":\\" in ref or ".." in ref.split("/"):
                raise ValueError(f"artifact reference must be relative and non-traversing: {ref}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "domain": self.domain,
            "attributes": _json_safe(self.attributes, location="attributes"),
            "quantity_fields": _json_safe(self.quantity_fields, location="quantity_fields"),
            "provenance_refs": list(self.provenance_refs),
            "parent_entity_refs": [ref.to_dict() for ref in self.parent_entity_refs],
            "artifact_refs": list(self.artifact_refs),
            "created_by": self.created_by,
            "validation_status": self.validation_status,
        }


@dataclass(frozen=True)
class EntityRecord:
    entity_id: str
    entity_type: str
    schema_id: str
    schema_version: str
    record: Mapping[str, Any]
    checksum_sha256: str
    artifact_refs: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    compact_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "record": _json_safe(self.record, location="record"),
            "checksum_sha256": self.checksum_sha256,
            "artifact_refs": list(self.artifact_refs),
            "provenance_refs": list(self.provenance_refs),
            "compact_metadata": _json_safe(self.compact_metadata, location="compact_metadata"),
        }


def entity_type_schemas() -> dict[str, dict[str, Any]]:
    """Return lightweight schema metadata for CLI inspection."""

    return {
        "MaterialCompositionEntity": {
            "required_attributes": ["elements", "stoichiometric_amounts", "atomic_fractions", "formula"],
            "purpose": "Composition identity and normalized fractions; no structure claim.",
        },
        "CrystalStructureEntity": {
            "required_attributes": ["lattice", "sites", "periodic_boundary_conditions"],
            "purpose": "Structure metadata contract; parsing/acquisition is out of scope.",
        },
        "MeasurementSeriesEntity": {
            "required_attributes": ["independent_variable", "dependent_variable", "axis_metadata"],
            "purpose": "Small measurement-series metadata with optional artifact-backed arrays.",
        },
        "StateEntity": {
            "required_attributes": ["state_variables", "conditions"],
            "purpose": "Snapshot of state variables and boundary-condition references.",
        },
        "TrajectoryEntity": {
            "required_attributes": ["ordered_state_refs", "time_axis"],
            "purpose": "Ordered state references; payload arrays remain artifact-backed.",
        },
        "GraphEntity": {
            "required_attributes": ["nodes", "edges", "graph_construction_metadata"],
            "purpose": "Graph metadata contract for future structure graphs; no GNN execution.",
        },
    }


def validate_entity_payload(payload: Mapping[str, Any]) -> EntityValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        entity = ScientificEntity(
            entity_id=str(payload["entity_id"]),
            entity_type=str(payload["entity_type"]),
            schema_id=str(payload["schema_id"]),
            schema_version=str(payload["schema_version"]),
            domain=str(payload["domain"]),
            attributes=payload.get("attributes", {}),
            quantity_fields=payload.get("quantity_fields", {}),
            provenance_refs=tuple(str(item) for item in payload.get("provenance_refs", ())),
            parent_entity_refs=tuple(
                EntityReference(
                    entity_id=str(item["entity_id"]),
                    entity_type=str(item["entity_type"]),
                    checksum_sha256=item.get("checksum_sha256"),
                )
                for item in payload.get("parent_entity_refs", ())
            ),
            artifact_refs=tuple(str(item) for item in payload.get("artifact_refs", ())),
            created_by=str(payload.get("created_by", "platform_core")),
            validation_status=str(payload.get("validation_status", "valid")),
        )
    except KeyError as exc:
        errors.append(f"missing:{exc.args[0]}")
        entity = None
    except ValueError as exc:
        errors.append(str(exc))
        entity = None
    if entity is not None:
        schema = entity_type_schemas().get(entity.entity_type, {})
        required = set(schema.get("required_attributes", ()))
        missing = sorted(required - set(entity.attributes))
        errors.extend(f"missing_attribute:{item}" for item in missing)
        if entity.entity_type in {"TrajectoryEntity", "GraphEntity"} and not entity.artifact_refs:
            warnings.append("large payloads should use artifact_refs when arrays or tensors are present")
    status = "valid" if not errors and not warnings else "warning" if not errors else "invalid"
    return EntityValidationResult(valid=not errors, validation_status=status, errors=tuple(errors), warnings=tuple(warnings))
