# Battery Comparability Evidence Package

Status: `v2.6.3_battery_comparability_evidence_feature_stage_complete`

## Purpose

v2.6.3 audits whether the tracked Kaggle NASA-derived Battery cohort contains
enough source evidence to treat batteries and cycles as scientifically
comparable. It does not infer missing metadata and does not change, retrain, or
re-evaluate the v2.6.1 persistence/Ridge benchmark.

The package audits a fixed evidence matrix:

1. chemistry;
2. nominal capacity;
3. ambient temperature;
4. charge protocol;
5. discharge protocol;
6. cutoff voltage;
7. measurement calibration and uncertainty;
8. source snapshot/version.

Each row records the evidence status, granularity, coverage, source reference,
limitation, external-data requirement, and explicit `false` flags for inference,
same-condition assumptions, and established comparability.

## Verified Inputs

The audit is read-only over:

- `data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv`;
- `data/processed/battery_v2_3_5_source_lineage_summary.json`;
- `data/processed/battery_v2_3_5_metadata_recovery_summary.csv`;
- `data/processed/battery_v2_6_1_generalization_forecast_summary.json`;
- `data/processed/battery_v2_6_2_forecast_failure_diagnostic_summary.json`.

The v2.6.1 and v2.6.2 deterministic checksums are mandatory inputs. A mismatch
blocks execution rather than silently recalculating or replacing metrics.

## Result

The evidence matrix covers all 34 tracked batteries and 2,495 analysis-ready
cycle rows, but none of the eight required fields establishes cross-battery
test-condition equivalence.

- Chemistry is absent.
- `reference_capacity_ah` is a derived `first_n_median` reference and is not
  nominal capacity.
- Ambient temperature is recorded for all rows, but five values are present and
  four batteries span more than one recorded value.
- Protocol evidence is group-level or measured-signal evidence, not
  cycle-specific commanded charge/discharge logs.
- Cutoff-voltage policy is absent.
- Calibration and measurement uncertainty are absent; zero uncertainty is not
  assigned.
- The immediate local Kaggle distribution is checksum-verified, but the
  official original NASA snapshot/version is not verifiable from local package
  metadata.

The decision remains:

```text
comparability_not_established
```

The scientific closeout is `inconclusive`: the package is suitable for metadata
gap auditing and evidence-acquisition planning, but not for causal explanation,
mechanism inference, cross-battery equivalence, predictive-generalization
claims, or engineering decisions.

## Metric and Model Preservation

The package verifies and preserves the existing benchmark boundary:

- persistence pooled MAE: `3.425575369058076`;
- Ridge pooled MAE: `4.15369918179312`;
- v2.6.1 scientific assessment: `unsupported`;
- v2.6.2 comparability status: `comparability_not_established`;
- model retraining: `false`;
- metric recomputation: `false`;
- source mutation: `false`;
- network or credentials: `false`.

## Run

Preview without writes:

```powershell
python -m src.platform_core.battery_comparability_evidence --json preview
```

Run the audit and write local details plus the tracked compact summary:

```powershell
python -m src.platform_core.battery_comparability_evidence --json run
```

Validate a generated result:

```powershell
python -m src.platform_core.battery_comparability_evidence --json validate outputs/v2_6_battery_comparability/comparability_summary.json
```

Generated local details:

- `outputs/v2_6_battery_comparability/evidence_matrix.csv`;
- `outputs/v2_6_battery_comparability/comparability_summary.json`.

Tracked compact evidence:

- `data/processed/battery_v2_6_3_comparability_evidence_summary.json`.

## What Would Change the Conclusion

A future comparability claim requires source-backed, battery-level chemistry and
nominal capacity, cycle-specific commanded charge/discharge protocols and
cutoff policy, calibration/uncertainty records, and an independently verifiable
official source snapshot/version. These records must be evaluated before, not
after, a new model experiment is selected.
