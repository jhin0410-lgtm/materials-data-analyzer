# RFC 0004: Mechanism and Operator Taxonomy

Status: `accepted_for_v2_3`

## Context

v2.2 introduced selected scientific operators for bounded checks and
structure-artifact generation.

## Problem

Future physics work needs to distinguish relation metadata, representation
transforms, consistency checks, and state propagation.

## Decision

Use three primary operator roles:

- `Evaluator`
- `Transformer`
- `Propagator`

Relation categories include algebraic, constitutive, conservation,
equilibrium, kinetic, differential, integral, boundary, initial condition,
observation, statistical, transformation, transition, and graph construction.

## Alternatives Considered

- Treat every operator as a generic callable: rejected for security and claim
  control.
- Implement propagators immediately: rejected because mechanism readiness is
  not yet established.

## Consequences

Existing structure and XRD operations remain Evaluator or Transformer style.
`Propagator` remains concept-only in v2.3.1.

## Compatibility

The selected scientific operator registry remains metadata-only and
allowlisted.

## Security

No arbitrary equation execution, dynamic import, shell command, or network
operation is introduced.

## Scientific Limitations

Operator metadata is not evidence that a mechanism applies to a dataset.

## Migration Implications

Future operator records may add PGIR role metadata without renaming existing
operator IDs.

## Validation Plan

Validate capability stages and prohibit promotion of `Propagator` beyond
`concept_defined`.

## Open Questions

- Which first mechanism family should receive a bounded Evaluator?

## v2.3.2 Follow-up

The Battery pilot registers Transformer-style representation adapters and a
requirements-audit operator. It does not promote any battery mechanism to an
executed Evaluator or Propagator.
