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

## Scientific boundary

Reviewer dispositions are traceable records, not replacement validation scores.
They do not authorize battery removal, target repair, interpolation, smoothing,
renormalization, model refitting, favorable cohort selection, or causal
attribution. The current NASA result remains `Diagnostic`, and the predictive
evidence level remains `Unsupported` unless a separate scientifically valid
analysis changes it.
