# Retrieval Reproducibility Audit

Status: `v2.5.2_retrieval_reproducibility_feature_stage_complete`

The v2.5.2 audit asks whether repository evidence is sufficient to compare two
independent retrieval events. It performs no retrieval itself. The public
platform release remains `v2.4.0`; v2.5.2 is an additive feature stage.

## Reproducibility Classes

| Class | Evidence required |
| --- | --- |
| Exact byte reproducibility | Two independent events, comparable source and artifact roles, complete retrieval metadata, and equal raw-byte SHA-256 values |
| Logical content reproducibility | The same evidence boundary, unequal or unavailable raw bytes, and equal canonical logical JSON |
| Content changed | Eligible paired events with different canonical logical content |
| Metadata mismatch | Eligible paired events whose declared source, snapshot, client, query, schema, or transformation conditions differ |
| Not comparable | Different domains, incompatible artifact roles or versions, or another ineligible pair |
| Insufficient evidence | A required event, identity, checksum, or metadata field is absent |

Canonical JSON normalizes JSON key order and formatting. It can therefore
identify equal logical JSON across indentation or LF/CRLF differences. It
cannot establish equal source snapshots, retrieval conditions, or exact
distribution bytes.

## Evidence Contract

Each local evidence record preserves:

- case study, artifact role, artifact version, and relative artifact reference;
- source-system, dataset, distribution, snapshot, and retrieval-event
  references when present;
- exact artifact-byte and canonical logical checksums as distinct values;
- retrieval timestamp, client, method, query, entity scope, response count,
  input schema, and transformation boundary when present;
- field-level evidence sources, unresolved metadata, and limitations.

Comparison records include eligibility, source and role checks, raw and
logical content checks, metadata findings, a registered assessment status, an
explicit claim boundary, and a deterministic checksum. The contract rejects
unknown fields, unsupported versions, unregistered statuses, checksum
tampering, absolute paths, path traversal, secret-like values, arbitrary
module or callable declarations, cross-domain pairs, and same-file
self-comparison.

## Supported Inputs And Current Result

The clean-checkout audit reads only:

- `materials_project_v2_2_4_structure_enrichment_summary.json`;
- `battery_v2_3_5_source_lineage_summary.json`;
- `external_source_compatibility_audit_summary_v1.json`.

These are three context artifacts, not three retrieval events. Materials and
Battery are different domains and are never paired with one another.

| Case study | Compatibility context | Retrieval result | Primary missing evidence |
| --- | --- | --- | --- |
| Materials Project | `compatible_with_restrictions` | `insufficient_evidence` | Independent second event, named snapshot, retrieval timestamp, exact requested-ID evidence, and API client version |
| Battery | `partial` | `insufficient_evidence` | Independent second event, official NASA snapshot, retrieval timestamp and client/method details, license/terms, uncertainty, and calibration metadata |

The Battery archive checksum identifies the verified local Kaggle package. It
does not identify an official NASA snapshot. The Materials tracked summary
identifies one bounded historical aggregate, not a second retrieval event.
Neither case study currently supports exact-byte, logical-content, or metadata
reproducibility as a real-world scientific claim.

## CLI

Preview reads and validates the bounded evidence plan without writing:

```powershell
python -m src.cli preview-retrieval-reproducibility-audit configs/examples/retrieval_reproducibility_audit.json
```

Run requires explicit authorization but still performs no network or model
execution:

```powershell
python -m src.cli run-retrieval-reproducibility-audit configs/examples/retrieval_reproducibility_audit.json --execute
```

Validate the compact summary or a local evidence/comparison record:

```powershell
python -m src.cli validate-retrieval-reproducibility-audit data/processed/retrieval_reproducibility_audit_summary_v1.json
```

## Artifact Policy

The tracked
`data/processed/retrieval_reproducibility_audit_summary_v1.json` stores
canonical logical identities and deterministic aggregate readiness only.
Checkout-dependent raw hashes and detailed evidence/comparison records remain
under ignored `outputs/v2_5_retrieval_reproducibility/`.

Optional local pairs may be declared with safe repository-relative paths.
They are not required by tests or clean checkouts, and their paths and results
do not change the portable tracked readiness summary.

## Claim Boundary

Software validation is `supported`: registered synthetic pairs exercise exact,
logical, changed-content, metadata-mismatch, ineligible, and insufficient
outcomes deterministically. Scientific validation remains
`insufficient_paired_retrieval_evidence`.

Compatibility, canonical identity, matching record counts, or one local
checksum does not establish source truth, scientific validity, domain
comparability, mechanism validity, independent validation, or production
validation. The conclusion can change only with independently retrieved,
same-role artifacts and complete source, snapshot, client, query, timestamp,
schema, transformation, and checksum evidence.
