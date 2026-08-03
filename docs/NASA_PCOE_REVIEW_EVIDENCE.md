# NASA PCoE Battery Review Evidence

## Purpose

The focused review queue identifies batteries that deserve source, continuity,
coverage, or model-error review. This evidence layer makes that queue actionable by
linking each battery to:

- exact quarantined source operations and source discharge ordinals;
- cycle-gap and adjacent-target-jump diagnostics;
- battery-level persistence and Ridge error contribution;
- the highest-error validation rows, referenced by the original CSV row number;
- a deterministic review action and checklist.

The layer reads existing artifacts only. It does not reimport the NASA archive,
extract new features, refit a model, repair targets, or remove batteries.

## Invocation

After pulling the change, use the combined existing-artifact workflow:

```powershell
.\scripts\run_nasa_pcoe_review_workflow.ps1
```

The workflow first refreshes the protocol-aware audit, verified import-to-analysis
binding, and focused review queue. It then creates the review evidence packets.
The order is intentional: evidence generation fails closed when the binding or
queue is stale relative to the current import and analysis artifacts.

Custom paths and a custom Python executable are supported:

```powershell
.\scripts\run_nasa_pcoe_review_workflow.ps1 `
  -PythonExecutable python `
  -ImportOutput <import-output> `
  -AnalysisOutput <analysis-output>
```

The same workflow may be run as two explicit steps when stage-by-stage inspection
is required:

```powershell
.\scripts\run_nasa_pcoe_protocol_audit.ps1
.\scripts\run_nasa_pcoe_review_evidence.ps1
```

Neither form imports the NASA ZIP or refits a model. The protocol-audit stage reads
the existing import and analysis artifacts, refreshes protocol diagnostics,
records the import-to-analysis binding, and regenerates the queue. The evidence
stage creates the linked battery packets.

The evidence stage also supports custom paths when run separately:

```powershell
.\scripts\run_nasa_pcoe_review_evidence.ps1 `
  -ImportOutput <import-output> `
  -AnalysisOutput <analysis-output>
```

## Provenance and consistency gates

Generation fails rather than silently combining incompatible artifacts when:

- required queue, validation, import, or manifest files are missing;
- analysis-manifest checksums do not match the review queue, queue summary,
  validation predictions, protocol profile, or protocol-audit JSON;
- the queue's recorded source hashes do not match the current protocol profile and
  protocol-audit JSON;
- the analysis run lacks a verified import-artifact binding written by the
  protocol-audit CLI;
- the supplied import manifest identity or bound artifact hashes differ from the
  import recorded for the analysis run;
- import-manifest checksums do not match the protocol summary, source inventory,
  or excluded-operation table;
- queue battery identities differ from the import protocol or are missing from the
  source inventory;
- overlapping protocol or inventory values differ between the queue and import;
- per-battery prediction counts, exclusion counts, or MAE values do not reconcile.

An import may contain an inventory-only battery when every usable degradation
target for that battery was quarantined. Such a battery is outside the protocol
profile and review queue. It is not converted into a packet; its identity and
ignored exclusion count are recorded explicitly in the evidence summary.

## Outputs

```text
<analysis-output>/
├── tables/
│   └── nasa_protocol_review_evidence.csv
└── reports/
    ├── nasa_protocol_review_evidence.json
    └── nasa_protocol_review_evidence.md
```

The CSV contains one row per queue battery in review order. The JSON preserves the
same records with their boolean types and provenance summary. The Markdown report
includes exact source locations, source operation indices, and highest-error
validation row references for human review.

## Interpretation

`recommended_action_class` is a work-routing label, not a scientific diagnosis.
For example, `source_quality_and_error_influence_review` means that source-quality
flags and disproportionate model error co-occur and should be inspected together.
It does not mean that the source quarantine caused the model error.

`top_*_error_rows` refer to the one-based line number in
`validation_predictions.csv`, including the header as line 1. They identify where
to inspect; they do not authorize deletion or favorable cohort selection.

## Scientific boundary

The evidence remains **Diagnostic**. It preserves the existing predictive evidence
level, including `Unsupported` when that is the declared closeout. No packet
establishes a degradation mechanism, causal relationship, external
transferability, or engineering readiness. No action class authorizes battery
removal, target repair, interpolation, smoothing, renormalization, or model-result
replacement.
