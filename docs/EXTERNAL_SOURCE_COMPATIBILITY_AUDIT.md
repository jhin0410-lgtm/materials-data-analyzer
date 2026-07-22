# External Source Compatibility Audit

Status: `v2.5.1_feature_stage_complete`

The v2.5.1 audit executes two explicit v2.4 compatibility mappings over
tracked compact evidence. It demonstrates deterministic software
compatibility without migrating source files, acquiring data, reading
credentials, or changing scientific conclusions. The public platform version
remains `2.4.0` during this feature stage.

## Supported Inputs

| Adapter | Tracked input | Version | Result |
| --- | --- | --- | --- |
| `materials_structure_summary_external_lineage_v1` | `materials_project_v2_2_4_structure_enrichment_summary.json` | `2.2.4` | `compatible_with_restrictions` |
| `battery_source_lineage_to_external_source_v1` | `battery_v2_3_5_source_lineage_summary.json` | `2.3.5` | `partial` |

Dispatch is an exact artifact-kind and version allowlist. Unknown artifact
kinds, unsupported or future versions, ambiguous matches, unknown fields,
absolute paths, path traversal, and secret-like values fail explicitly. The
registry does not import user-supplied callables or use reflection, `eval`,
`exec`, pickle, network access, or shell execution.

## Replay Evidence

Each adapter records two distinct checksums:

- the SHA-256 of the exact input bytes;
- the SHA-256 of canonical logical JSON.

The Materials raw-byte checksum is
`3eb562668272daefb3893f725717856da1706b5c71771d51cd5f2fd74583ee92`;
the Battery raw-byte checksum is
`c392bf6a1a6ded87714e6038331ca7b7fb38bf54eabe36a1724cf5c2d36f284c`.
Repeated runs reproduce the same adapter and summary checksums. The input
files remain byte-for-byte unchanged.

The Materials result retains the unresolved named dataset snapshot, source
database version, API client version, and license/terms fields. Its
`LocalDerivedArtifact` target remains explicitly conceptual because v1 has no
dedicated typed record for it.

The Battery result remains partial. The local Kaggle immediate-upstream
archive identity and checksums are preserved, while the official NASA
snapshot, original retrieval timestamp, license/terms, measurement
uncertainty, and calibration metadata remain unresolved and are not filled
with defaults.

## CLI

Preview validates the config, allowlisted adapter plan, tracked inputs, and
versions without writing:

```powershell
python -m src.cli preview-external-source-compatibility configs/examples/external_source_compatibility_audit.json
```

Execution requires an explicit flag:

```powershell
python -m src.cli run-external-source-compatibility-audit configs/examples/external_source_compatibility_audit.json --execute
```

The compact summary can be validated independently:

```powershell
python -m src.cli validate-external-source-compatibility data/processed/external_source_compatibility_audit_summary_v1.json
```

These commands need only the two tracked summaries, so preview, audit, and
tests work in a clean checkout without raw Battery data or local Materials API
artifacts.

## Artifact Policy

The tracked file
`data/processed/external_source_compatibility_audit_summary_v1.json` contains
only compact deterministic evidence. Detailed per-adapter results are written
under ignored `outputs/v2_5_external_source_compatibility/`. No raw data, row-
level identifiers, API responses, credentials, or local absolute paths are
tracked.

## Claim Boundary

The software verdict is `supported` for deterministic interpretation of the
two explicitly tested historical artifacts. Provenance portability remains
`diagnostic`: compatibility preserves available evidence and unresolved gaps,
but does not independently verify source authenticity, data correctness,
scientific comparability, mechanism validity, predictive models, independent
validation, or production readiness. No numeric trust score is used.
