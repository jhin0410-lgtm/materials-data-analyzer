# External Source Metadata Contract

Status: `v2.4.1_contract_ready_with_provenance_gaps`

The v2.4 contract is a versioned provenance-governance layer. It is not a
generic network client and does not certify source quality.

## Concept Model

| Concept | Meaning |
| --- | --- |
| `ExternalSourceSystem` | Publisher service, catalog, repository, mirror, or archive source |
| `ExternalDataset` | Logical collection independent of a particular release |
| `DatasetSnapshot` | Versioned or explicitly unresolved dataset state |
| `DistributionArtifact` | Concrete archive, file, or API response batch |
| `RetrievalEvent` | When and how a distribution was retrieved |
| `MirrorOrImmediateUpstream` | Intermediary source distinct from an official original |
| `LocalDerivedArtifact` | Parser, adapter, Transformer, or Evaluator output |
| `SourceDocumentationRecord` | API docs, protocol paper, dictionary, or calibration record |

Typed records live in
[`src/platform_core/external_source_contracts.py`](../src/platform_core/external_source_contracts.py).
Runtime records and persisted envelopes are separate. Persisted envelopes
include schema ID, schema version, record type, JSON-safe record, and canonical
JSON checksum.

## Version And Compatibility Policy

- Schema version is independent of product version.
- v1 rejects unsupported future schema versions.
- Unknown fields are rejected; silent field dropping is prohibited.
- Existing Materials and Battery artifacts are referenced through adapters and
  are not rewritten.
- Future changes require an explicit compatibility adapter or migration.

The bounded v2.5.1 follow-on implements the two tracked-summary adapters as an
exact artifact/version allowlist. It records raw-byte and canonical logical
JSON checksums separately and rejects unknown or future versions. See the
[External Source Compatibility Audit](EXTERNAL_SOURCE_COMPATIBILITY_AUDIT.md).

The six schema contracts and three compact registries live under
`data/platform/`. Their ownership is registered in the PGIR schema-ownership
registry.

## Authentication Policy

Allowed authentication requirements are `none`, `optional_api_key`,
`required_api_key`, `record_dependent`, and `local_only`. Only approved
environment-variable names may be persisted. Credential values, authorization
headers, signed-URL secrets, sessions, and arbitrary runtime objects are
rejected.

## Checksum Policy

`raw_bytes_sha256` hashes exact distribution bytes. `canonical_json_sha256`
hashes sorted logical JSON and is stable across formatting or line endings.
The two checksum classes answer different questions and cannot substitute for
one another.

## Current Records

- Materials Project: authoritative API with actual bounded historical
  retrieval evidence, unresolved named snapshot identity, and unresolved
  access/license terms in existing repository evidence.
- NASA-derived Battery: verified immediate Kaggle upstream archive with
  verified local byte checksums and unresolved official NASA snapshot.
- NIST OAR, NVD, and NREL: future declarations only, with zero retrieval,
  snapshot, or successful-integration evidence.

## Execution Boundary

The v2.4.1 contract build performs no network call, acquisition, descriptor or
graph generation, model run, solver execution, source mutation, or credential
read. Local audit output is ignored under
`outputs/v2_4_external_source_pgir_reuse/`.

The v2.5.1 compatibility replay has the same no-network and no-credential
boundary. It reads only the two tracked compact summaries; detailed replay
records remain local-only under
`outputs/v2_5_external_source_compatibility/`.
