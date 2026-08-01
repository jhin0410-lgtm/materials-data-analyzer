# NASA PCoE Pipeline Result Summary

## Purpose

The official NASA PCoE import and Battery Intelligence workflow can take several
minutes because it re-reads nested archives, validates 761k+ raw-signal points,
extracts features, and repeats battery-disjoint validation. Result inspection
must not require repeating that work.

The pipeline therefore supports a read-only summary mode:

```powershell
.\scripts\run_nasa_pcoe_battery_pipeline.ps1 -SummaryOnly
```

`-SummaryOnly` reads the existing import and analysis artifacts. It does not:

- read or replace the source ZIP;
- rerun the importer;
- recompute signal features;
- retrain or revalidate Ridge;
- rerun the protocol-aware post-hoc audit;
- change predictions, targets, warnings, exclusions, or scientific closeout;
- overwrite the import or analysis directories.

The command fails explicitly when a required legacy result artifact is missing.
The protocol-audit artifact is optional in summary-only mode so existing outputs
created before the audit was introduced remain readable. Its availability is
reported explicitly.

## Complete workflow

A normal pipeline run now performs three ordered stages:

1. import the official NASA PCoE archive with retrieval-receipt verification;
2. run signal-enriched Battery Intelligence and its existing audits;
3. run the protocol-aware post-hoc audit on the completed import and analysis
   artifacts.

The third stage does not refit a model or modify source rows. It separates broad
rated-capacity start context from source-quality, trajectory-continuity,
evaluation-coverage, and error-influence findings.

## Reported fields

The summary reports:

- retrieval-receipt verification and the rated-capacity reference method;
- imported, excluded, and invalid-Capacity operation counts;
- target/reference, cycle-gap, adjacent-jump, and plausibility audit counts;
- pooled-error stability;
- source/protocol review, unevaluated-battery, and disproportionate-error counts;
- row-weighted and battery-macro MAE for persistence and Ridge;
- capacity-only versus signal-enriched Ridge MAE when available;
- the number of batteries associated with each diagnostic reason;
- the final scientific evidence level.

When `reports/nasa_protocol_audit.json` exists, the same summary also reports:

- protocol-audit status and preserved predictive evidence level;
- batteries with rated-reference start context;
- batteries for which that start context is the only review reason;
- source-quality issue count;
- trajectory-continuity issue count;
- combined structural-or-coverage issue count;
- disproportionate-error influence count;
- pooled Ridge improvement relative to persistence;
- number of batteries where Ridge beats persistence;
- number of supported exact-temperature strata.

The diagnostic-reason counts are derived from
`tables/battery_diagnostic_priority.csv`. One battery may contribute to multiple
reason counts.

## Interpretation boundary

`source_protocol_review_battery_count` is deliberately broad. A battery is
included when any of the following applies:

- the first observed target differs materially from the configured reference;
- an adjacent target jump is large;
- the cycle index contains a gap;
- a target is outside the configured plausibility interval;
- the reference-capacity reconstruction is inconsistent;
- no exact-horizon forecast row is available;
- the battery contributes disproportionately to pooled error.

Therefore a count such as `33 / 34` does **not** mean that 33 batteries are
corrupted or should be removed. In the NASA archive, experiments begin under
different load, temperature, and cutoff-voltage conditions. With retention
referenced to the documented 2 Ah rating, a first discharge that is not near
2 Ah can be physically or procedurally expected and still trigger a diagnostic
review flag.

The protocol audit makes this distinction explicit:

- `reference_context_only_battery_count` identifies batteries for which the
  rated-reference start deviation is contextual rather than accompanied by a
  structural, source-quality, coverage, or disproportionate-influence concern;
- `structural_or_coverage_issue_battery_count` identifies batteries requiring
  closer review for source quality, trajectory continuity, or missing declared
  evaluation coverage.

These categories do not authorize automatic battery deletion. A battery may
appear in multiple issue dimensions, so category counts are not additive.

The flags support source- and protocol-aware investigation. They do not authorize
silent deletion, favorable cohort selection, renormalization, clipping,
interpolation, or a stronger scientific claim. Temperature strata and protocol
associations remain diagnostic and observational; they do not replace the
battery-disjoint pooled validation result.

## Recommended use

Run the complete workflow only when source bytes, importer behavior, analysis
configuration, or code changed:

```powershell
.\scripts\run_nasa_pcoe_battery_pipeline.ps1
```

Use summary-only mode when the artifacts already exist and only the scientific
result needs to be reviewed:

```powershell
.\scripts\run_nasa_pcoe_battery_pipeline.ps1 -SummaryOnly
```

After a protocol audit has been generated once, summary-only mode reports its
separated context and issue counts without recomputing any analysis.
