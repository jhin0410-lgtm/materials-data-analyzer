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

After the focused review queue exists, generate the evidence from the existing
import and analysis artifacts:

```powershell
.\scripts\run_nasa_pcoe_review_evidence.ps1
```

Custom paths are supported:

```powershell
.\scripts\run_nasa_pcoe_review_evidence.ps1 `
  -ImportOutput <import-output> `
  -AnalysisOutput <analysis-output>
```

## Provenance and consistency gates

Generation fails rather than silently combining incompatible artifacts when:

- required queue, validation, import, or manifest files are missing;
- analysis-manifest checksums do not match the review queue, queue summary, or
  validation predictions;
- import-manifest checksums do not match the protocol summary, source inventory,
  or excluded-operation table;
- the queue summary differs from the summary stored in `run_manifest.json`;
- queue battery identities differ from the import protocol or inventory;
- overlapping protocol or inventory values differ between the queue and import;
- per-battery prediction counts, exclusion counts, or MAE values do not reconcile.

This binds the evidence table to one analysis run and one import run without
relying only on aggregate counts or filenames.

## Outputs

```text
<analysis-output>/
├── tables/
│   └── nasa_protocol_review_evidence.csv
└── reports/
    ├── nasa_protocol_review_evidence.json
    └── nasa_protocol_review_evidence.md
```

The CSV contains one row per battery in review order. The JSON preserves the same
flat records with a provenance summary. The Markdown report provides a human
review packet for every battery.

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
