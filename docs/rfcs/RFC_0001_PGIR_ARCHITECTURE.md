# RFC 0001: PGIR Architecture

Status: `accepted_for_v2_3`

## Context

The platform now has scientific entities, quantities, uncertainty records,
relations, selected operators, graph artifacts, and trust-boundary outputs.
These pieces need a common governance model before future physics-aware work.

## Problem

Without a canonical representation layer, future features could silently treat
observations as states, graph artifacts as predictive evidence, or metadata as
mechanism execution.

## Decision

Adopt PGIR as a representation-governance architecture with domain-neutral
concepts and domain-explicit boundaries. PGIR is additive and read-only in
v2.3.1.

## Alternatives Considered

- Rename existing runtime classes to PGIR names: rejected because it would
  break stable APIs and persisted schema identity.
- Build a solver-first physics layer: rejected because readiness and claim
  boundaries are not yet sufficient.

## Consequences

Existing v1/v2 APIs remain valid. PGIR concepts map to current implementation
records through compact registries and documentation.

## Compatibility

Persisted schema IDs remain stable. Optional PGIR metadata can be added later
only when migration and checksum policies permit.

## Security

No dynamic import, shell execution, network access, live object persistence, or
unsafe binary object serialization is allowed.

## Scientific Limitations

PGIR architecture is not physical correctness, predictive improvement, or
production readiness.

## Migration Implications

No migration is performed in v2.3.1.

## Validation Plan

Use registry parse checks, mapping validation, schema ownership checks,
capability-stage validation, CLI smoke, and v2.2 preservation tests.

## Open Questions

- Which battery trajectory representation should be the first PGIR adapter?
- Which mechanism family should be evaluated first after data sufficiency is
  demonstrated?
