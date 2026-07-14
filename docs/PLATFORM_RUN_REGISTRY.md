# Platform Run Registry

Status: `development_stage` for v2.1.1.

The platform run registry is a local-only SQLite metadata index for run
manifests, report manifests, artifact instances, lineage, and reproducibility
checks. It extends the v2.0 manifest/report scaffold without executing
acquisition, model training, raw-data reads, or scientific recomputation.

## Purpose

The registry answers operational questions about platform metadata:

- Which manifests have been recorded locally?
- Which input and output artifact instances were declared by each run?
- What checksums, config hashes, code commits, statuses, warnings, and claim
  boundaries were recorded?
- Can a run be treated as reproducibility-verified from metadata?
- Are two runs metadata-equivalent, or did config, inputs, code, or outputs
  change?

It does not store raw rows, model binaries, credentials, host inventory,
environment secrets, usernames, or absolute local paths.

## Storage Backend

The backend is Python standard-library `sqlite3`.

Default path:

```text
outputs/platform_registry/platform_registry.sqlite3
```

`outputs/**` is ignored by Git, so the registry remains local-only. The CLI
rejects absolute registry paths, path traversal, and registry paths outside
`outputs/platform_registry/`.

## Schema

The logical schema is tracked in
[`../data/platform/platform_registry_schema_v2.json`](../data/platform/platform_registry_schema_v2.json).
The SQLite DDL lives in `src/platform_core/run_registry.py`.

Tables:

- `runs`: one run or report manifest record
- `artifacts`: input/output artifact instances declared by a run
- `lineage`: input-to-output artifact relationships within a run
- `warnings`: warnings and errors imported from the manifest
- `registry_metadata`: schema version and timestamps

The initial database schema version is `1`. Newer unsupported schema versions
are rejected. Migration support is intentionally minimal until the registry has
more production history.

## Manifest Ingestion

Supported inputs:

- v2 run manifests under `outputs/platform_runs/**/run_manifest.json`
- v2 report manifests under `outputs/platform_reports/**/report_manifest.json`

Ingestion validates the manifest, computes a canonical manifest SHA256, records
run metadata, creates artifact records, creates lineage edges, and imports
warnings/errors in a single transaction.

Duplicate policy:

- Same `run_id` with identical manifest content: idempotent success
- Same `run_id` with different manifest content: conflict rejection

The source manifest file is not modified.

## Artifact Instances

The static artifact registry defines expected artifacts. The persistent run
registry records observed artifact instances for a specific run.

Artifact records include:

- artifact ID
- run ID
- role: `input` or `output`
- relative path
- artifact type and format
- checksum when available
- local-only/tracked policy
- producer and provenance status

Raw artifacts cannot be marked as tracked compact outputs. Local-only artifacts
are not promoted into Git tracking by the registry.

## Reproducibility Status

The registry computes metadata-only reproducibility status:

- `reproducible_verified`
- `reproducible_partial`
- `unverifiable_missing_input`
- `unverifiable_checksum_mismatch`
- `unverifiable_code_commit`
- `unverifiable_config`
- `blocked_policy_violation`

The check uses manifest metadata, checksums, side-effect status, and claim
boundary references. It does not rerun adapters or recompute scientific
metrics.

## Run Comparison

Two runs can be compared by plugin, adapter, stage, config SHA, code commit,
input checksums, output checksums, status, and warning metadata.

Comparison statuses:

- `identical_metadata`
- `reproducible_equivalent`
- `configuration_changed`
- `inputs_changed`
- `code_changed`
- `outputs_changed`
- `incomparable`

Numeric metric comparison is intentionally out of scope for v2.1.1.

## CLI Usage

Initialize a local registry:

```powershell
python -m src.cli registry-init
```

Ingest an existing run manifest:

```powershell
python -m src.cli registry-ingest outputs/platform_runs/reliability-trust-verify-run/run_manifest.json
```

List and inspect runs:

```powershell
python -m src.cli registry-list-runs
python -m src.cli registry-show-run reliability-trust-verify-run
python -m src.cli registry-list-artifacts --run-id reliability-trust-verify-run
```

Check reproducibility and compare:

```powershell
python -m src.cli registry-reproducibility reliability-trust-verify-run
python -m src.cli registry-compare-runs run-a run-b
```

Validate and export:

```powershell
python -m src.cli registry-validate
python -m src.cli registry-export --overwrite
```

Existing commands can opt into registration:

```powershell
python -m src.cli dry-run configs/examples/reliability_trust_manifest_dry_run.json --write-manifest --register-run
python -m src.cli execute configs/examples/reliability_trust_verify_run.json --mode verify --register-run
python -m src.cli generate-report --config configs/examples/platform_report_all_case_studies.json --register-run
```

`--register-run` is off by default for backward compatibility.

## Security And Privacy

The registry uses parameterized SQLite queries and does not expose arbitrary
SQL in the CLI. It rejects absolute paths, path traversal, credential-like
manifest content, and registry paths outside `outputs/platform_registry/`.

The registry does not:

- execute subprocesses or shell commands
- call network APIs
- run acquisition
- train models
- read raw datasets
- store credentials, usernames, hostnames, or environment dumps
- overwrite canonical tracked artifacts

## Export

Registry exports are local-only under:

```text
outputs/platform_registry/exports/
```

The current export writes:

- `registry_snapshot.json`
- `runs.csv`

Exports are deterministic enough for local inspection but remain ignored
regenerable artifacts.

## Limitations

- This is not a server or multi-user database.
- There is no SQLite dependency beyond the Python standard library.
- Report-manifest ingestion is metadata-oriented; it does not validate report
  claims beyond the existing report manifest validator.
- Metric-level comparison remains future work.
- Backfill is explicit; the registry does not scan `outputs/` automatically.
