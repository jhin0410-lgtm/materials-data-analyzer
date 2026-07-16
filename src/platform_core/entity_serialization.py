"""Deterministic JSON serialization for scientific entity records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .scientific_entities import (
    ENTITY_SCHEMA_VERSION,
    SUPPORTED_ENTITY_TYPES,
    EntityReference,
    EntityRecord,
    ScientificEntity,
    validate_entity_payload,
)


SUPPORTED_SCHEMA_VERSIONS = {"2.2.2"}


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def checksum_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def to_record(entity: ScientificEntity) -> EntityRecord:
    payload = entity.to_dict()
    validation = validate_entity_payload(payload)
    if not validation.valid:
        raise ValueError("; ".join(validation.errors))
    checksum = checksum_payload(payload)
    return EntityRecord(
        entity_id=entity.entity_id,
        entity_type=entity.entity_type,
        schema_id=entity.schema_id,
        schema_version=entity.schema_version,
        record=payload,
        checksum_sha256=checksum,
        artifact_refs=entity.artifact_refs,
        provenance_refs=entity.provenance_refs,
        compact_metadata={
            "domain": entity.domain,
            "validation_status": entity.validation_status,
            "record_kind": "json_safe_entity_record",
        },
    )


def validate_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    required = {"entity_id", "entity_type", "schema_id", "schema_version", "record", "checksum_sha256"}
    missing = sorted(required - set(payload))
    errors.extend(f"missing:{field}" for field in missing)
    entity_type = payload.get("entity_type")
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        errors.append(f"unsupported_entity_type:{entity_type}")
    schema_version = str(payload.get("schema_version", ""))
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"unsupported_schema_version:{schema_version}")
    record = payload.get("record")
    if isinstance(record, Mapping):
        actual = checksum_payload(record)
        if payload.get("checksum_sha256") != actual:
            errors.append("checksum_mismatch")
        validation = validate_entity_payload(record)
        errors.extend(validation.errors)
    else:
        errors.append("record_must_be_object")
    return {"valid": not errors, "errors": errors}


def from_record(payload: Mapping[str, Any]) -> ScientificEntity:
    validation = validate_record(payload)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))
    record = payload["record"]
    assert isinstance(record, Mapping)
    return ScientificEntity(
        entity_id=str(record["entity_id"]),
        entity_type=str(record["entity_type"]),
        schema_id=str(record["schema_id"]),
        schema_version=str(record["schema_version"]),
        domain=str(record["domain"]),
        attributes=record.get("attributes", {}),
        quantity_fields=record.get("quantity_fields", {}),
        provenance_refs=tuple(str(item) for item in record.get("provenance_refs", ())),
        parent_entity_refs=tuple(
            EntityReference(
                entity_id=str(item["entity_id"]),
                entity_type=str(item["entity_type"]),
                checksum_sha256=item.get("checksum_sha256"),
            )
            for item in record.get("parent_entity_refs", ())
        ),
        artifact_refs=tuple(str(item) for item in record.get("artifact_refs", ())),
        created_by=str(record.get("created_by", "platform_core")),
        validation_status=str(record.get("validation_status", "valid")),
    )


def serialize_entity(entity: ScientificEntity) -> dict[str, Any]:
    return to_record(entity).to_dict()


def deserialize_entity_record(payload: Mapping[str, Any]) -> ScientificEntity:
    return from_record(payload)


def reject_newer_schema(schema_version: str) -> None:
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported or newer entity schema version: {schema_version}; supported={ENTITY_SCHEMA_VERSION}")
