# Characterization Feature Handoff

## Purpose

This workflow consumes the stable long-format feature CSVs exported by
`materials-characterization-analyzer` and prepares them for tabular process,
quality, reliability, or modeling workflows in `materials-data-analyzer`.

The workflow is a contract and table-integration layer. It does not re-run an
instrument analyzer or reinterpret XRD, SEM, EDS, Raman, TEM, or SAED results.

## Accepted Contract

Every input feature CSV must contain these columns:

```text
sample_id
measurement_id
instrument
feature_name
feature_label
value
unit
method
source_file
source_sha256
preprocessing_id
quality_flag
```

The handoff validates:

- non-empty sample, measurement, instrument, feature, unit, method, and quality
  identifiers;
- numeric finite feature values;
- optional SHA-256 format;
- one sample and instrument mapping per `measurement_id`;
- one method and preprocessing identity per semantic feature definition;
- at most one record per sample and semantic feature.

Multiple measurements of the same semantic feature are not averaged. A user must
select a measurement or define and document an aggregation before the handoff.

## Synthetic Clean-Checkout Example

```powershell
python scripts/build_characterization_handoff.py `
  --characterization data/sample/synthetic_characterization_features_long.csv `
  --process-table data/sample/synthetic_process_characterization_samples.csv `
  --output outputs/characterization_handoff_demo
```

The synthetic files test software behavior only. They are not experimental
evidence.

## Outputs

### `characterization_features_validated_long.csv`

The normalized 12-column feature records after contract validation.

### `characterization_feature_dictionary.csv`

One row per semantic feature definition, including:

- stable wide-table key;
- instrument;
- feature name and optional label;
- unit;
- method;
- preprocessing identity;
- observed quality flags;
- sample, measurement, and record counts.

### `characterization_features_wide.csv`

One row per `sample_id`. Characterization columns use a stable prefix such as:

```text
char__xrd__detected_peak_count__count
char__sem__mean_equivalent_diameter__um
char__eds__element_weight_percent__fe__percent
```

Feature names include instrument, semantic feature, optional label, and unit.
Methods and preprocessing IDs are validated for consistency rather than hidden in
the column name.

### `integrated_sample_table.csv`

Written only when `--process-table` is supplied. The process and characterization
tables are outer-joined through `sample_id`. No row-order join is permitted.

### `sample_join_audit.csv`

Records each sample as:

- `matched`;
- `process_only`;
- `characterization_only`.

No unmatched sample is silently discarded.

### `characterization_handoff_manifest.json`

Records source file checksums, row and feature counts, quality-flag counts,
provenance coverage, join counts, generated artifacts, and scientific boundaries.

## Failure Conditions

The workflow stops when it finds:

- missing contract columns;
- blank required identifiers;
- missing, non-numeric, or non-finite values;
- invalid optional SHA-256 values;
- duplicate records;
- a measurement ID associated with multiple samples or instruments;
- mixed methods or preprocessing IDs for the same semantic feature;
- multiple records for one sample and semantic feature;
- duplicate process-table sample IDs;
- process columns that collide with generated characterization feature columns.

## Scientific Boundary

Successful execution establishes that the files satisfy the software handoff
contract. It does not establish:

- physical sample identity merely because IDs match;
- representative image or spectrum sampling;
- instrument calibration or uncertainty;
- valid phase, compound, particle, grain, pore, or mechanism interpretation;
- comparability across different preprocessing methods;
- target validity, leakage safety, causal relationships, or engineering readiness.

Before downstream analysis, the integrated table still requires sample,
processing-history, measurement-condition, target, grouping, time, and leakage
review appropriate to the scientific question.
