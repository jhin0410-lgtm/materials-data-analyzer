# External Source Current Architecture Audit

Status: `v2.4.1_audited`

This audit records the source-handling architecture that existed at the
v2.3.0 release boundary. It introduces no acquisition, download, or migration.

## Existing Source Types

| Workflow | Existing source form | Current evidence | Principal gap |
| --- | --- | --- | --- |
| Materials Project | Authoritative API, bounded existing-ID retrieval | 838 requested and returned documents, query plan, 17 chunk manifests | Named database snapshot/version unavailable |
| NASA-derived Battery | Immediate Kaggle upstream archive | Local ZIP and `metadata.csv` byte checksums, exact 34-cell lineage | Official NASA original snapshot, retrieval time, and license unresolved |
| NIST OAR | Future catalog declaration | Routing metadata only | No dataset, snapshot, retrieval, or integration evidence |
| NVD | Future security source declaration | Routing metadata only | Not a Battery or materials-property source |
| NREL | Future energy-system source declaration | Routing metadata only | Not a cell protocol or measurement-uncertainty substitute |

## Authentication Handling

Materials Project code already uses local credential gating. v2.4.1 records
only `MP_API_KEY`, `NVD_API_KEY`, and `NREL_API_KEY` as environment-variable
names. No value, authorization header, signed URL, session, hostname, or user
path is persisted. The Battery archive is audited as an existing local file;
its historical retrieval authentication is unavailable.

## Identity And Version Handling

Earlier code represented source, query, local archive, and derived outputs in
separate manifests, but did not provide one shared contract distinguishing:

- source system;
- logical dataset;
- dataset snapshot;
- distribution artifact;
- retrieval event;
- immediate upstream or mirror;
- local derived artifact; and
- source documentation.

v2.4.1 adds that separation through compatibility adapters. Existing payloads
remain authoritative and unchanged. A landing page does not establish a
snapshot version, an API service version is not a dataset release, and a
retrieval timestamp is not a publication date.

## Query And Retrieval Evidence

The Materials workflow preserves the v2.2.4 `enrich_existing_ids` plan:
838 existing IDs, 12 allowlisted fields, maximum 838 records, chunks of 50,
17 completed chunks, zero missing IDs, and zero duplicate returned IDs. That
historical acquisition is referenced read-only; v2.4.1 makes no API call.

The Battery workflow has a verified local ZIP but no recorded retrieval event
time. v2.4.1 therefore records an incomplete historical retrieval event rather
than inventing a timestamp.

## Checksums

- Raw archives and binaries use byte checksums.
- Logical JSON/text records use canonical content checksums when applicable.
- A mirror checksum proves the local mirror bytes only; it is not an official
  original checksum.
- Raw-byte and canonical-content checksums are not interchangeable.

## License, Citation, And Documentation

Materials Project publisher and documentation references are explicit, while
its named database snapshot and access/license terms remain unresolved. The Battery immediate upstream
is identified by Kaggle slug and checksums; official NASA snapshot and local
redistribution terms remain unresolved, so raw data stays local-only.

## Existing Contract Mapping

| Existing record | New concept | Mapping | Migration |
| --- | --- | --- | --- |
| `MaterialsProjectAcquisitionManifest` | `RetrievalEvent` | `compatible_adapter` | None |
| v2.2.4 structure enrichment summary | `LocalDerivedArtifact` | `compatible_adapter` | None |
| v2.3.5 Battery lineage summary | `DistributionArtifact` | `partial` | None |

The partial Battery mapping preserves missing retrieval time, official snapshot
identity, and license as gaps. No tracked v2.2/v2.3 checksum is changed.

## Current Limitations

- Source governance does not certify scientific data quality.
- An official publisher does not imply independent validation of each record.
- Materials current API records and the original modeling target belong to
  different snapshot concepts even though the audited target drift was zero.
- Battery official NASA provenance remains unresolved beyond the verified
  immediate Kaggle package.
- Future NIST OAR, NVD, and NREL entries are declarations, not integrations.
