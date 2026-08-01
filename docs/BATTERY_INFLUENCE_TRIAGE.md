# Battery Influence and Observed-Condition Triage

## Purpose

A pooled mean absolute error can be dominated by a few batteries even when the
median row error is small. Removing those batteries would create a more favorable
number but would not establish scientific comparability.

This diagnostic stage therefore answers a narrower question:

> Which batteries have disproportionate error contribution, how sensitive is the
> pooled score to each battery, and which explicit target, continuity, or observed
> condition fields require source-aware review?

It does not infer protocol identity, assign batteries to cohorts, remove records,
or replace the declared battery-disjoint validation score.

## Automatic execution

Both installed commands run the triage automatically after the target
comparability audit:

```powershell
mda-battery-intelligence `
  --cycle-summary <cycle-summary.csv> `
  --output <run-output>
```

```powershell
mda-battery-result-audit `
  --run-output <existing-run-output>
```

The second command reuses existing predictions. It does not rerun model fitting.

## Diagnostics

For every model and battery, the triage records:

- prediction count;
- battery MAE, median absolute error, maximum absolute error, and total absolute
  error fraction;
- equal-contribution baseline and excess ratio;
- row-weighted pooled MAE with that battery omitted;
- battery-macro MAE with that battery omitted;
- the change relative to the complete declared validation result;
- error-contribution and influence ranks.

The omission delta is a sensitivity statistic only. It is not a replacement
performance metric and cannot justify deleting the battery.

The priority table combines those metrics with explicit reasons already present
in the target-integrity audit:

- target outside the configured plausibility range;
- inconsistent or invalid reference capacity;
- first target not near 100 percent;
- large adjacent target jump;
- cycle-index gap.

Observed-condition medians are carried into a separate profile table. The
software does not convert those values into inferred protocol labels.

## Outputs

```text
<run-output>/
├── tables/
│   ├── battery_influence_by_model.csv
│   ├── battery_diagnostic_priority.csv
│   └── battery_condition_error_profile.csv
└── reports/
    ├── battery_influence_triage.json
    └── battery_influence_triage.md
```

The scientific closeout and run manifest are updated with the new diagnostic
component and artifact checksums.

## Scientific interpretation

A battery is marked for source/protocol review when it has an explicit target or
continuity reason, or when its error contribution exceeds 1.5 times the
equal-contribution baseline for at least one model.

This threshold identifies disproportionate influence; it does not prove the
battery is erroneous. A defensible cohort comparison still requires authoritative
protocol metadata and predeclared inclusion rules.
