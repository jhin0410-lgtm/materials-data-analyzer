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
- change predictions, targets, warnings, exclusions, or scientific closeout;
- overwrite the import or analysis directories.

The command fails explicitly when a required result artifact is missing.

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

The flags support source- and protocol-aware investigation. They do not authorize
silent deletion, favorable cohort selection, renormalization, clipping,
interpolation, or a stronger scientific claim.

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
