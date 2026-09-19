# Generic Evidence Provider Contract

## Purpose

`ProviderState` is a planning-only contract for normalizing verified domain readiness and
unresolved evidence requirements. It is deliberately separate from `EvidencePacket`.

An EvidencePacket may carry validated scientific evidence. A ProviderState carries metadata
about what a provider has verified, what remains blocked, and what class of evidence/action is
required next.

## Authority boundary

Every ProviderState fixes:

- `planning_metadata_only=true`;
- `empirical_evidence_created=false`;
- `scientific_status_promoted=false`;
- `downstream_use_authorized=false`;
- `execution_authorized=false`.

Provider normalization therefore cannot convert readiness metadata, blockers, or planning gaps
into measurements, scientific truth, or action authority.

## Required fields

Each ProviderState includes:

- provider identity, contract/schema version, and adapter identity;
- domain, modality, and subject scope;
- exact SHA-256 source bindings;
- readiness status and optional maturity/blocker state;
- zero or more unresolved requirements with stable generic action classes;
- explicit authority boundary;
- canonical ProviderState SHA-256.

Generic requirement classes are:

- `blocked_external`
- `authorization_required`
- `review_required`
- `evidence_acquisition`
- `analysis`
- `simulation`
- `engineering_validation`

These are planning semantics, not executor authorization.

## Characterization adapter

The characterization adapter does not trust a caller-authored gap. It:

1. replays the existing independent L0-L8 characterization verifier;
2. derives the first blocker through the existing characterization planning policy;
3. preserves producer source SHA-256 bindings;
4. emits only the resulting unresolved requirement.

A forged or rehashed ProviderState is rejected by
`verify_characterization_provider_state()`, which recomputes the state from the original
characterization assessment.

## Planning-state adapter

`adapt_authenticated_planning_gaps()` consumes an unresolved planning-state object only when
the complete canonical object matches an externally supplied SHA-256 trust root.

Unknown action classes are normalized to `review_required`, never to automatic execution.

`verify_authenticated_planning_provider_state()` recomputes the ProviderState from the
externally bound planning object.

## Aggregation

`aggregate_provider_requirements()` combines multiple validated ProviderStates while preserving
each state SHA-256 as ancestry. Provider identities must be unique.

The aggregate is deterministic and planning-only. A persisted aggregate can be replayed against
the source ProviderStates with `verify_provider_requirement_aggregate()`.

## Scientific boundary

Provider readiness is not empirical evidence. A source count is not independence. A blocker is
not a negative scientific finding. A planning requirement is not proof that a candidate exists.
A provider adapter may normalize already verified domain state, but it may not reinterpret or
upgrade that state.
