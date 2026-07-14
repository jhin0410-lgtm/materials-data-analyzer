# Platform Reporting

Status: `scaffold_stage` for v2.0.5.

The platform report engine creates a local-only summary of v2 registry metadata
and tracked compact case-study artifacts. It is read-only: it does not run
acquisition, normalization, feature engineering, model training, trust
analysis, raw-data reads, row-level prediction reads, or scientific metric
recomputation.

## Data Model

`src/platform_core/reports.py` defines the report model:

- `PlatformReport`
- `CaseStudyReport`
- `StageReport`
- `ArtifactReport`
- `ValidationReport`
- `TrustReport`
- `ExecutionReport`
- `ReportWarning`

Unknown or unavailable fields are represented explicitly as `unknown`,
`unavailable`, or `unavailable_or_legacy` instead of being inferred.

## Source Boundary

Allowed inputs:

- plugin, adapter, artifact, validation, trust, execution, and case-study
  registry metadata
- tracked compact JSON/CSV artifacts
- tracked contracts/specifications
- tracked Markdown documentation
- safe file sizes and checksums

Prohibited inputs:

- `data/raw/**`
- full analysis-ready local datasets
- row-level prediction outputs
- serialized models
- user credentials
- host absolute paths
- arbitrary `outputs/` files
- network sources

## Extraction Policy

`src/platform_core/report_extractors.py` maps each case study to explicit
tracked compact artifact IDs. It checks expected columns and records warnings
for missing artifacts or schema mismatches.

The report stage does not choose a new best model, tune a threshold, recompute
confidence intervals, rescore predictions, or infer absent fields. Existing
closeout/conclusion artifacts remain the source of truth.

## Output Policy

Generated reports are local-only under:

```text
outputs/platform_reports/<report_id>/
```

Generated files:

- `platform_report.json`
- `platform_report.md`
- `report_manifest.json`

The writer rejects absolute paths, traversal, symlink escapes, and accidental
overwrite unless `--overwrite` is supplied. Report outputs are ignored by Git.

## Manifest

`report_manifest.json` records:

- report ID, schema version, platform version, and code commit
- generated formats
- registry snapshot counts
- source artifact relative paths and checksums
- case-study IDs
- warnings and errors
- output files and checksums
- `local_only = true`
- `scientific_recomputation_performed = false`

The manifest does not store credentials, usernames, host names, or absolute
local paths.

## CLI

Preview without writing files:

```powershell
python -m src.cli preview-report --config configs/examples/platform_report_all_case_studies.json
```

Generate a local report:

```powershell
python -m src.cli generate-report --config configs/examples/platform_report_all_case_studies.json
```

Validate and inspect a generated report:

```powershell
python -m src.cli validate-report outputs/platform_reports/platform_v2_all_case_studies
python -m src.cli inspect-report outputs/platform_reports/platform_v2_all_case_studies
python -m src.cli list-report-sources
```

Add `--json` before the command for deterministic JSON output.

## Limitations

- HTML, PDF, dashboard, and UI report formats are not implemented.
- The report summarizes existing artifacts; it is not a new analysis run.
- Battery Archive remains a legacy/partial trust case study in the v2 report.
- CI/test status is supplied as metadata; the report engine does not execute
  pytest.
