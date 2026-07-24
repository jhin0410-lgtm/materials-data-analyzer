# External Source Provenance Levels

Status: `v2.4.1_active`

Provenance is represented as explicit statuses with evidence references and
limitations. It is never collapsed into one confidence or trust score.

## Status Taxonomy

- `authoritative_source_verified`
- `authoritative_metadata_verified`
- `official_distribution_verified`
- `snapshot_identity_verified`
- `immediate_upstream_verified`
- `local_copy_checksum_verified`
- `derived_lineage_verified`
- `snapshot_identity_unresolved`
- `official_original_not_locally_verified`
- `license_or_terms_unresolved`
- `documentation_incomplete`
- `mirror_only`
- `provenance_conflict`

Every status entry requires at least one evidence reference and one limitation.
Conflicting statuses remain visible rather than being averaged away.

## Materials Project Boundary

The source is authoritative and the local v2.2.4 lineage from 838 existing IDs
through structure entities is verified. The acquisition manifest records the
historical retrieval time and bounded query. It does not record a named
Materials Project database version, so `snapshot_identity_unresolved` remains.
The API service identity is not treated as the target dataset snapshot.

## Battery Boundary

The immediate Kaggle upstream, archive bytes, metadata bytes, and derived
34-cell lineage are verified. The official NASA original snapshot/version is
not locally verified, retrieval time is unavailable, and terms are unresolved.
These gaps remain explicit; the Kaggle checksum is not described as an
official NASA checksum.

## Compatibility Replay

The v2.5.1 replay carries these statuses and limitations through explicit
versioned adapters. It does not promote `snapshot_identity_unresolved` or
`license_or_terms_unresolved`, and it introduces no numeric trust score. A
successful replay means only that a supported historical compact artifact can
be interpreted deterministically without being rewritten.

## Retrieval Reproducibility

The v2.5.2 audit keeps retrieval reproducibility separate from compatibility.
Exact bytes, canonical logical content, and retrieval metadata are evaluated
as different evidence classes. A real-world reproducibility claim requires
two independent same-domain, same-role retrieval events. The current
Materials and Battery records each provide only one bounded evidence point, so
both conclude `insufficient_evidence`; they are not compared with one another
or with themselves.

## Claim Boundary

Provenance status does not establish measurement accuracy, calibration,
scientific correctness, mechanism validity, predictive value, or deployment
readiness. Those require separate evidence and trust gates.
