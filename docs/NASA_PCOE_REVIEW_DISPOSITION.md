# NASA PCoE Review Disposition

## Purpose

The review-evidence workflow produces provenance-bound packets for all 34
protocol-audited batteries and identifies the priority review order. It does not,
and should not, invent the result of a human source and model-error review.

The disposition layer provides the missing reviewer-controlled record. It creates
an editable worksheet from the exact current evidence CSV, binds every row to that
file's SHA-256, validates reviewer entries, and persists an immutable snapshot and
summary. It does not inspect the NASA archive automatically, infer a degradation
mechanism, or change the existing predictive closeout.

The priority list is an ordering aid only. The worksheet always contains all 34
battery records, and a complete audit requires every row to receive an explicit
review disposition.

## Local output visibility

NASA analysis outputs are generated locally under `outputs/` and are intentionally
excluded from Git by `.gitignore`. They therefore do not appear in the GitHub file
browser after a pull or push.

The review script now prints whether the analysis directory exists, the recursive
file count, and an `explorer.exe` command for opening the exact directory. The same
location can be inspected manually with:

```powershell
Get-ChildItem `
  .\outputs\nasa_pcoe_signal_enriched_battery_intelligence `
  -Recurse -File -Force |
  Select-Object FullName, Length
```

Open the directory directly on Windows with:

```powershell
explorer.exe ".\outputs\nasa_pcoe_signal_enriched_battery_intelligence"
```

## 1. Refresh evidence

Run the combined existing-artifact workflow first:

```powershell
.\scripts\run_nasa_pcoe_review_workflow.ps1
```

This refreshes the protocol audit, verified import-to-analysis binding, focused
queue, and evidence packets without importing data or fitting a model.

## 2. Initialize the reviewer worksheet

```powershell
.\scripts\run_nasa_pcoe_review_disposition.ps1 -Initialize
```

The command creates:

```text
outputs/nasa_pcoe_signal_enriched_battery_intelligence/
└── tables/
    └── nasa_protocol_review_disposition.csv
```

Initialization refuses to overwrite an existing worksheet by default. `-Overwrite`
must be explicit and should be used only after preserving any manual work.

The following columns are evidence-bound and must not be edited:

- `source_evidence_sha256`;
- `review_order`;
- `battery_id`;
- `review_tier`;
- `recommended_action_class`;
- `review_check_codes`;
- `predictive_evidence_level`.

The reviewer fills only:

- `review_status`;
- `conclusion_code`;
- `reviewer`;
- `reviewed_at_utc`;
- `evidence_refs`;
- `rationale`;
- `follow_up_action`.

## Allowed review states

`review_status` accepts:

- `pending`;
- `completed`;
- `follow_up_required`.

A `pending` row must keep every other reviewer field blank. A reviewed row requires
a reviewer, UTC timestamp, rationale, and one of these bounded conclusion codes:

- `no_confirmed_issue`;
- `source_quality_issue_confirmed`;
- `trajectory_continuity_issue_confirmed`;
- `evaluation_coverage_issue_confirmed`;
- `model_or_protocol_mismatch_suspected`;
- `inconclusive`.

A confirmed or suspected issue requires exact `evidence_refs`. A
`follow_up_required` row additionally requires `follow_up_action`. Evidence
references should point to packet fields such as source locations, source operation
indices, excluded cycle indices, or validation row numbers. They are audit links,
not causal proof.

## 3. Validate and snapshot dispositions

After editing the worksheet:

```powershell
.\scripts\run_nasa_pcoe_review_disposition.ps1 -Finalize
```

A separate reviewer CSV can be supplied:

```powershell
.\scripts\run_nasa_pcoe_review_disposition.ps1 `
  -Finalize `
  -DispositionInput <reviewer-csv>
```

Finalization rejects:

- an evidence CSV or report that no longer matches `run_manifest.json`;
- a worksheet created from a different evidence SHA-256;
- changed battery identities, review order, tiers, action classes, checks, or
  evidence level;
- missing or duplicate rows;
- unsupported statuses or conclusion codes;
- reviewed rows without reviewer, timestamp, or rationale;
- issue conclusions without evidence references;
- follow-up states without an explicit action.

It writes:

```text
<analysis-output>/
├── tables/
│   └── nasa_protocol_review_disposition_final.csv
└── reports/
    ├── nasa_protocol_review_disposition.json
    └── nasa_protocol_review_disposition.md
```

The immutable snapshot and reports are checksummed in `run_manifest.json`.
Incremental snapshots are allowed: pending rows remain visible and the summary is
reported as `in_progress` until all rows are reviewed.

## 4. Package every generated file for a full audit

To review the complete generated analysis rather than only the priority queue,
package the entire analysis-output directory:

```powershell
.\scripts\package_nasa_pcoe_full_audit.ps1
```

The command creates:

```text
outputs/nasa_pcoe_full_audit_bundle.zip
```

The ZIP includes every file recursively under the current NASA analysis-output
directory plus:

- `_audit_bundle_inventory.csv`, containing each relative path, byte count, and
  SHA-256;
- `_audit_bundle_readme.txt`, recording the source directory, creation time, source
  file count, audit scope, and scientific boundary.

A custom source or destination can be supplied:

```powershell
.\scripts\package_nasa_pcoe_full_audit.ps1 `
  -AnalysisOutput <analysis-output-directory> `
  -Destination <audit-bundle.zip>
```

This is the preferred artifact for an external full-file audit because it avoids
selectively omitting non-priority reports, tables, manifests, or diagnostic files.
Bundling itself does not validate scientific conclusions.

## Scientific boundary

Reviewer dispositions are traceable records, not replacement validation scores.
They do not authorize battery removal, target repair, interpolation, smoothing,
renormalization, model refitting, favorable cohort selection, or causal
attribution. The current NASA result remains `Diagnostic`, and the predictive
evidence level remains `Unsupported` unless a separate scientifically valid
analysis changes it.
