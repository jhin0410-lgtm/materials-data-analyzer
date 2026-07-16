# Scientific Entity Architecture Audit

Status: `v2.2.2 foundation`

## Current Representation

The platform still uses dictionaries, pandas DataFrames, JSON files, compact CSV
artifacts, and SQLite registry rows. Those formats remain valid. v2.2.2 adds a
JSON-safe scientific entity layer above them rather than replacing them.

## Representation Classes

| Class | Current examples | v2.2.2 decision |
| --- | --- | --- |
| Runtime object | Python dataclasses, pandas DataFrames, evaluator results | Allowed only in memory |
| Serialized record | JSON manifests, scientific execution results, compact metadata | Versioned JSON-safe records |
| Persisted registry row | run registry and scientific execution SQLite tables | Metadata, checksum, schema refs, artifact refs only |
| Tabular artifact | processed compact CSVs, model summaries | Kept as tabular artifacts |
| Domain-specific artifact | Materials feature matrices, Backblaze local datasets | Kept behind artifact references when large |
| Local-only artifact | raw archives, outputs, row-level predictions | Not tracked and not loaded by CI tests |

## Dict and DataFrame Usage

DataFrames remain the correct format for analysis-ready tables, feature matrices,
metric summaries, and compact CSV outputs. Dicts remain the correct exchange
format for CLI JSON, manifests, registry snapshots, and scientific execution
payloads. Entity records are introduced for identity, provenance, relation, and
quantity semantics where a flat table is too weak.

## Persistence Boundary

The registry must not store live Python objects. It stores versioned serialized
records, checksums, compact metadata, provenance references, and artifact
references. Large arrays, trajectories, structures, graph tensors, and row-level
outputs remain artifact-backed.

## Unsafe Persistence Audit

The v2.2.2 foundation does not introduce binary object serialization, dynamic
class imports, user-supplied callable execution, or arbitrary equation
execution. Migration functions and operators are code-registered.

## Compatibility

Existing v1.x, v2.1, and v2.2.1 DataFrame/JSON workflows remain canonical for
their case-study outputs. Compatibility adapters connect selected rows and small
metadata frames to entity records only when the grain is explicit.
