# NASA PCoE Protocol-Aware Post-hoc Audit

## Purpose

The official NASA PCoE workflow can produce a broad source/protocol review count
because most experiments do not begin with a full 2 Ah discharge. That fact is
important context, but it is not equivalent to a corrupted target or a battery
that should be removed.

This audit separates five evidence dimensions:

1. **rated-reference start context** — the first observed discharge differs by
   more than 5 percentage points from the documented 2 Ah rating;
2. **source quality** — invalid Capacity quarantine, reference inconsistency, or
   a target outside the configured plausibility range;
3. **trajectory continuity** — a source discharge ordinal gap or an adjacent
   target jump larger than 20 percentage points;
4. **evaluation coverage** — no exact-horizon validation row exists;
5. **error influence** — a battery contributes disproportionately to pooled
   absolute error under an existing model.

A rated-reference start deviation is retained in the battery profile but does
not, by itself, become a hard target-integrity failure.

## Invocation

After the official import and Battery Intelligence analysis already exist, run:

```powershell
.\scripts\run_nasa_pcoe_protocol_audit.ps1
```

The command reads existing artifacts only. It does not re-read the source ZIP,
reimport MAT files, extract signal features, fit Ridge, recompute predictions,
or delete existing output rows.

Custom output directories remain available:

```powershell
.\scripts\run_nasa_pcoe_protocol_audit.ps1 `
  -ImportOutput <import-output> `
  -AnalysisOutput <analysis-output>
```

## Inputs

The audit requires:

```text
<import-output>/
├── nasa_pcoe_protocol_summary.csv
└── nasa_pcoe_source_inventory.csv

<analysis-output>/
├── tables/
│   ├── target_integrity_by_battery.csv
│   ├── battery_diagnostic_priority.csv
│   └── validation_predictions.csv
└── reports/
    ├── scientific_closeout.json
    └── signal_feature_comparison.json  # optional
```

Battery identities in protocol, target-integrity, and priority artifacts must
match exactly. Every protocol battery must also appear in the filtered source
inventory. Extra skipped inventory rows are allowed, but a missing protocol
battery fails explicitly so import and analysis outputs from different runs
cannot silently suppress quarantine evidence. A prediction for an unknown
battery also fails explicitly.

The audit reads the existing `scientific_closeout.json` evidence level and
preserves it. The audit does not independently upgrade or downgrade the declared
predictive evidence. When no prior evidence level exists, the audit reports
`Inconclusive` rather than inventing a stronger conclusion.

## Diagnostics

### Battery profile

Every imported battery remains visible with:

- explicit protocol-summary fields;
- source invalid-Capacity counts;
- target/reference and continuity diagnostics;
- exact-horizon evaluation coverage;
- persistence and Ridge battery-level error;
- context, structural-review, and influence-review reason codes.

No row or battery is filtered. Older or minimal inventories that contain valid
battery identities but no quarantine counter columns remain readable; their
missing counters are reported as zero rather than causing a scalar/Series error.

### Temperature strata

The audit retains metadata for exact repeated
`ambient_temperature_median_c` values. A stratum is supported for
within-stratum description only when at least three evaluated batteries share
that value.

For one- or two-battery strata, battery and prediction counts remain visible but
all model MAE and improvement fields are unavailable. This prevents sparse,
favorable subgroup scores from being promoted despite the declared support
threshold.

Supported stratum metrics are still not replacement validation scores. A
favorable stratum cannot override the declared battery-disjoint pooled result.

### Error associations

For each available protocol field, the audit calculates battery-level Spearman
rank associations with persistence MAE, Ridge MAE, and Ridge-minus-persistence
MAE when at least five complete batteries and sufficient variation are present.

The associations are univariate, observational, and confounded. They do not
identify a degradation mechanism or causal protocol effect.

## Outputs

```text
<analysis-output>/
├── tables/
│   ├── nasa_protocol_battery_profile.csv
│   ├── nasa_protocol_temperature_strata.csv
│   └── nasa_protocol_error_associations.csv
└── reports/
    ├── nasa_protocol_audit.json
    └── nasa_protocol_audit.md
```

The run manifest and scientific closeout are updated with checksums and a
`Diagnostic` component. The existing overall predictive evidence level is
preserved unchanged. Re-running the audit replaces only its paired Markdown
marker section and preserves all sections written after it by other tools.

The limitation added to the closeout is constructed from observed nonzero
counts and supported diagnostics. When those dimensions are absent or
underpowered, the text remains neutral rather than asserting trajectory or
condition effects that were not observed.

## Scientific interpretation

A valid official-source import and admitted raw signal establish provenance and
software behavior. They do not establish predictive value.

For the current official NASA run, persistence remains better than Ridge and
signal-enriched Ridge is worse than capacity-only Ridge, so the pre-existing
predictive evidence remains `Unsupported`. The primary model sentence is always
derived from the loaded pooled metrics, while the overall evidence level is
preserved from the existing closeout. Protocol-aware diagnostics explain where
error and heterogeneity occur; they do not manufacture a positive model result.
