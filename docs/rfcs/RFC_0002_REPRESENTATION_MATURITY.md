# RFC 0002: Representation Maturity

Status: `accepted_for_v2_3`

## Context

Engineering datasets enter the platform with different levels of semantics,
units, uncertainty, and physical context.

## Problem

A schema-valid artifact can still be physically incomplete. Treating all parsed
data as mechanism-ready would create leakage and overclaiming risk.

## Decision

Use explicit maturity levels:

- `L0 raw_observed`
- `L1 schema_valid`
- `L2 semantically_mapped`
- `L3 dimensionally_valid`
- `L4 physically_admissible`
- `L5 mechanism_compatible`
- `L6 scientifically_evaluated`
- `L7 independently_validated`
- `L8 production_validated`

Maturity is claim-specific and operator-specific, not a scalar quality score.

## Alternatives Considered

- A single readiness flag: rejected because it hides context.
- Automatic promotion after parsing: rejected because file format is not
  scientific evidence.

## Consequences

Lower-maturity data can remain useful for audits and descriptive summaries, but
operators must enforce supported maturity levels.

## Compatibility

Existing artifacts are not rewritten. Maturity metadata is optional unless a
future migration justifies making it explicit.

## Security

Maturity evaluation cannot run arbitrary user code or inspect local raw data.

## Scientific Limitations

Dimensional validity is not physical correctness.

## Migration Implications

Future migrations may add optional `representation_maturity` fields.

## Validation Plan

Tests verify the level order, no automatic promotion, and future-only
capability boundaries.

## Open Questions

- How much evidence is sufficient for `mechanism_compatible` in battery
  trajectory analysis?

## v2.3.2 Follow-up

Battery observations and operational state summaries remain below
`mechanism_compatible`; the conformance gate records the missing mechanism
requirements rather than promoting the representation.
