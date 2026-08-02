# NASA PCoE Focused Review Queue

## Purpose

The protocol-aware audit separates rated-capacity start context from source
quality, trajectory continuity, evaluation coverage, and disproportionate model
error. The next useful step is not another model family. It is a deterministic
review order showing where those observed dimensions intersect.

This queue is operational and diagnostic. It does not assign a causal degradation
mechanism, remove batteries, change targets, refit models, or replace the declared
battery-disjoint validation result.

## Invocation

After `nasa_protocol_battery_profile.csv`, `nasa_protocol_audit.json`, and their
`run_manifest.json` provenance record exist:

```powershell
.\scripts\run_nasa_pcoe_review_queue.ps1
```

A custom analysis directory can be supplied:

```powershell
.\scripts\run_nasa_pcoe_review_queue.ps1 `
  -AnalysisOutput <analysis-output>
```

The command reads existing audit artifacts only. It does not read the NASA ZIP,
run the importer, extract signal features, or fit a model.

The normal protocol-audit command and the complete NASA pipeline generate this
queue automatically. The standalone command is for regenerating or inspecting
the queue from an already audited run.

## Review tiers

The tier is a review sequence, not a scientific severity score:

1. no exact-horizon evaluation coverage;
2. source-quality flag with disproportionate error influence;
3. trajectory-continuity flag with disproportionate error influence;
4. disproportionate error influence without a structural or coverage flag;
5. source-quality flag without disproportionate influence;
6. trajectory-continuity flag without disproportionate influence;
7. rated-reference start context only;
8. no current review flag.

A battery may have several review dimensions. The queue retains those dimensions
as a semicolon-delimited field even though one tier is used for deterministic
ordering.

## Validation and consistency gates

The queue fails explicitly when:

- required profile columns are missing;
- battery identities are blank or duplicated;
- a required boolean cell is blank, missing, or outside the accepted true/false
  token set;
- evaluation status conflicts with prediction count;
- `structural_or_coverage_issue` does not equal the union of source-quality,
  trajectory-continuity, and evaluation-coverage flags;
- evaluated battery MAE values are missing or non-finite;
- Ridge-minus-persistence MAE does not reconcile;
- profile counts differ from `nasa_protocol_audit.json`;
- `run_manifest.json` does not contain the same protocol-audit summary;
- the manifest lacks SHA-256 entries for the profile or protocol-audit JSON;
- either source artifact checksum differs from the manifest.

Count reconciliation catches ordinary schema inconsistencies. Manifest-summary
and SHA-256 validation bind the profile and summary to the same audited run even
when two runs happen to have identical aggregate counts.

## Outputs

```text
<analysis-output>/
├── tables/
│   └── nasa_protocol_review_queue.csv
└── reports/
    ├── nasa_protocol_review_queue.json
    └── nasa_protocol_review_queue.md
```

The queue summary records the verified source-artifact SHA-256 values. Its
artifact paths, summary, and output checksums are then added idempotently to the
same `run_manifest.json`.

## Scientific boundary

Co-occurrence is not causality. A battery with both an invalid-Capacity quarantine
and high error deserves source-aware review, but the intersection does not prove
that the quarantined operation caused the error. Similarly, error influence
without an existing structural flag is a candidate for protocol or model-mismatch
investigation, not evidence of a mechanism.

No queue category authorizes battery deletion, favorable cohort selection,
renormalization, interpolation, target repair, or promotion of the current
`Unsupported` predictive result.
