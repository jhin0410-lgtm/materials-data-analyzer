# RFC 0003: Schema Ownership and Evolution

Status: `accepted_for_v2_3`

## Context

The platform has versioned schemas for entities, quantities, uncertainty,
relations, operators, reports, and scientific execution records.

## Problem

Physics-aware extensions can weaken reproducibility if schema ownership,
versioning, compatibility, and deprecation rules are not explicit.

## Decision

Each schema has one owning module, a stable schema ID, and a schema version
separate from product version. Backward-compatible optional fields are
preferred; breaking changes require migration. Silent field dropping is
prohibited.

## Alternatives Considered

- Let every module evolve schemas independently: rejected because provenance
  and migration paths would fragment.
- Tie schema version to release tags: rejected because schema and product
  lifecycles differ.

## Consequences

Future PGIR fields must preserve unit, uncertainty, and provenance semantics.
Large payloads remain artifact-backed.

## Compatibility

Existing schema IDs remain stable. Runtime implementation class names are not
persisted identity.

## Security

Schemas cannot authorize dynamic imports, live object persistence, or local
absolute paths.

## Scientific Limitations

Schema validity does not guarantee scientific validity.

## Migration Implications

Future migrations must preserve logical checksums or explicitly record changed
semantics.

## Validation Plan

Use `pgir_schema_ownership_registry_v1.json` and CLI schema-governance
validation.

## Open Questions

- Which schema should first accept optional `pgir_role` metadata?

## v2.3.2 Follow-up

Battery PGIR schemas are registered as additive v1 schemas for cycle
Observation, operational State, Trajectory summary, and mechanism-readiness
metadata. Existing v2.2 and v1.x schemas are not rewritten.
