# RFC 0005: Domain Boundaries

Status: `accepted_for_v2_3`

## Context

The platform spans materials, batteries, smart factory data, reliability, and
XRD examples.

## Problem

Shared representation contracts can accidentally erase domain semantics or
turn domain-specific evidence into universal claims.

## Decision

Keep the PGIR core domain-neutral, but require explicit domain, measurement,
prediction, mechanism, scale, temporal, spatial, intervention, and validation
contexts for scientific claims.

## Alternatives Considered

- A universal domain-free ontology: rejected because domain semantics are
  necessary for applicability.
- Domain-specific stacks only: rejected because it prevents reusable governance
  and registry tooling.

## Consequences

Materials `composition_only_pre_structure` and
`known_structure_post_relaxation` remain separate prediction contexts. Battery
trajectory, reliability asset history, and process quality logs will require
their own context mappings before mechanism claims.

## Compatibility

Existing case-study trust boundaries remain authoritative.

## Security

Context records cannot contain credentials, local absolute paths, or executable
payloads.

## Scientific Limitations

Cross-domain reuse is not a universal mechanism claim until independently
validated.

## Migration Implications

Future adapters may add context references without changing historical results.

## Validation Plan

Use PGIR mapping, capability-stage, and report integration tests.

## Open Questions

- What is the minimum context needed for battery Observation to State mapping?

## v2.3.2 Follow-up

The first mapping is intentionally bounded: Battery Observation may transform
only to an operational State summary, not to complete electrochemical State,
internal concentration Field, or mechanism-ready parameter records.
