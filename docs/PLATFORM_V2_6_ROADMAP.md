# Platform v2.6 Roadmap

Status: `v2.6.8_snl_lfp_bounded_schema_read_feature_stage_complete`

## Release Boundary

`v2.4.0` remains the current public release. v2.6.1 through v2.6.8 are
feature-stage work and do not create a tag, release, or public version change.

## v2.6.1 Scope

v2.6.1 uses the existing tracked Kaggle NASA-derived Battery analysis-ready
table. It adds:

- exact five-cycle capacity-retention target alignment;
- current and lagged retention plus trailing rolling features;
- battery-disjoint deterministic GroupKFold evaluation;
- persistence and fixed Ridge baselines;
- train-only imputation and scaling;
- per-battery and pooled metrics;
- leakage, plausibility, source-mutation, and deterministic checksum audits;
- preview, run, and validate CLI commands.

The result is `unsupported`: Ridge does not improve pooled MAE over persistence
and improves only 13 of 33 evaluated batteries. This negative result is kept
without tuning or benchmark redesign.

## Boundaries

The scenario is warm-start cross-battery forecasting. It permits only
pre-origin history from each held-out battery and is not zero-shot. It does
not establish lifetime, RUL, SOH, mechanism, causal, calibrated-probability,
external-generalization, or engineering-decision evidence.

## v2.6.2 Failure Diagnostics

v2.6.2 preserves every v2.6.1 metric and adds deterministic, read-only
diagnostics over the existing predictions. The top five batteries account for
`90.35%` of Ridge excess absolute error, but no leave-one-battery-out result
reverses persistence superiority. Ridge is worse in the fixed early, middle,
and late regimes. Sparse batteries, abrupt-transition proximity, and three
nonphysical Ridge predictions are not primary aggregate drivers.

Source/test-condition comparability remains `comparability_not_established`.
The scientific closeout is `diagnostic`, not a mechanism or predictive
generalization finding. See
[Battery Forecast Failure Diagnostics](BATTERY_FORECAST_FAILURE_DIAGNOSTICS.md).

## v2.6.3 Comparability Evidence

v2.6.3 preserves the v2.6.1 model and metrics and the v2.6.2 diagnostic
conclusion. It audits a predeclared evidence matrix for chemistry, nominal
capacity, ambient temperature, charge/discharge protocols, cutoff voltage,
measurement calibration/uncertainty, and source snapshot/version.

The immediate Kaggle distribution and cycle-level ambient-temperature records
are verified, but no required field establishes cross-battery condition
equivalence. Chemistry, nominal capacity, cycle-specific commanded protocols,
cutoff policy, calibration/uncertainty, and the official NASA snapshot remain
unresolved; recorded temperatures are heterogeneous. The result is
`comparability_not_established` with an `inconclusive` scientific closeout.
See [Battery Comparability Evidence Package](BATTERY_COMPARABILITY_EVIDENCE_PACKAGE.md).

## v2.6.4 External Cohort Admission

v2.6.4 adds a prospective admission gate before any external Battery cohort is
merged or evaluated. It separates raw inventory review, cross-cohort
comparability, and predictive-validation eligibility.

The first candidate is the local Battery Archive-style bundle. Its nine archives,
196 cycle files, and 196 time-series files support a restricted inventory review,
but filename-encoded chemistry and C-rate labels are not source-backed metadata.
Nominal capacity, cycle-specific commanded protocols, cutoff policy,
calibration/uncertainty, official snapshot identities, and a verified target
contract remain unresolved.

The recorded decision is:

- inventory review: `admitted_with_restrictions`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- overall: `not_admitted_for_cross_cohort_validation`.

No raw archive is read or extracted, no filename metadata is parsed, and no model
or metric is executed or changed. See
[Battery External Cohort Admission Gate](BATTERY_EXTERNAL_COHORT_ADMISSION_GATE.md).

## v2.6.5 SNL LFP Source Evidence Recovery

v2.6.5 narrows the nine-archive candidate to `SNL LFP.zip` and records official
source documentation from Battery Archive, DOE OSTI, and Sandia. The bounded
study documents the commercial A123 APR18650M1A LFP cell, 1.1 Ah nominal
capacity, study equipment, protocol groups, capacity-check procedure, and the
2.0-3.6 V range for the 100% DOD LFP regime.

This evidence remains document-level. It is not yet checksum-bound to local
archive entries, cycles, command logs, or instrument channels. A publication DOI,
OSTI ID, and SAND number identify the study but not a versioned data distribution.
The source 80% capacity benchmark is also not treated as the v2.6.1 five-cycle
target.

The recorded decision is:

- source document recovery: `completed_with_remaining_binding_gaps`;
- bounded inventory binding: `eligible_for_read_only_inventory_binding`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- overall: `source_evidence_recovered_gate_not_passed`.

See [Battery SNL LFP Source Evidence Recovery](BATTERY_SNL_LFP_SOURCE_EVIDENCE_RECOVERY.md).

## v2.6.6 SNL LFP Artifact Binding

v2.6.6 implements the bounded archive identity audit authorized by v2.6.5. It
streams `SNL LFP.zip` to compute SHA-256 and reads its ZIP central directory to
record entry names, sizes, CRC values, safe paths, cycle/time-series pairing,
and filename-label provenance. It does not read entry payloads or CSV rows and
does not extract the archive.

The verified local result records:

- archive SHA-256:
  `006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d`;
- entry-manifest checksum:
  `f85e6f1ac333f7ff20b7bfd01b8599cfe86e8950c4971e9fc074a367da86a75c`;
- 60 safe entries, 30 cycle CSVs, 30 time-series CSVs, and 30 complete pairs;
- local artifact inventory binding: `local_artifact_inventory_bound`;
- document-to-archive binding: `not_established`;
- official distribution snapshot: `not_established`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- overall: `local_artifact_inventory_bound_gate_not_passed`.

The raw ZIP and row-level manifest remain uncommitted. See
[Battery SNL LFP Artifact Binding Audit](BATTERY_SNL_LFP_ARTIFACT_BINDING_AUDIT.md).

## v2.6.7 SNL LFP Source-to-Entry Binding

v2.6.7 links the official publication and Battery Archive documentation to the
checksum-bound local archive at the narrowest defensible level.

The official Battery Archive nomenclature defines institution, form factor,
cathode, environment temperature, beginning-of-life SOC window, bulk-cycling
charge/discharge rate, and replicate tokens. The 30 observed SNL LFP cell stems
aggregate into 12 condition-group entry patterns that match this nomenclature
and the documented SNL study variables.

The recorded decision is:

- publication to Battery Archive repository: `established`;
- repository filename nomenclature: `established`;
- study to condition groups: `established_condition_group_only`;
- condition groups to entry patterns:
  `established_repository_nomenclature_only`;
- physical cell to entry: `not_established`;
- cycle command to CSV rows: `not_established`;
- instrument channel to CSV columns: `not_established`;
- official distribution snapshot: `not_established`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- overall: `condition_group_nomenclature_bound_gate_not_passed`.

No archive bytes, entry payloads, CSV headers, or CSV rows are read in v2.6.7.
No filename label is promoted to a measured value, physical cell identity, or
cycle-specific command. See
[Battery SNL LFP Source-to-Entry Binding Review](BATTERY_SNL_LFP_SOURCE_ENTRY_BINDING_REVIEW.md).

## v2.6.8 SNL LFP Bounded CSV Schema Read

v2.6.8 implements the smallest payload-read contract justified by v2.6.7. It
predeclares three 25 °C, replicate-`a` cycle-data/time-series pairs—one pair for
each 0–100%, 20–80%, and 40–60% SOC protocol family.

The implementation:

- verifies the exact v2.6.6 archive SHA-256 before entry access;
- inspects the ZIP central directory;
- opens only the six exact representative entries;
- reads one header and at most five data rows per entry;
- rejects a physical line longer than 65,536 bytes;
- records headers, explicit header units, conservative candidate roles, sampled
  numeric/non-empty counts, and sampled row-width consistency;
- retains no raw sample values.

The reviewed local result records:

- archive identity: `verified`;
- representative entries opened: `6 / 6`;
- headers read: `6`;
- sampled rows read: `30`;
- schema-contract matches: `6`;
- schema-contract mismatches: `0`;
- sampled row-width matches: `6 / 6`;
- cycle-data schema: 12 columns, common header checksum
  `02c4b1f087f1133349cfb60f52443c75099c1d5742a266b4b2889701a344d88c`;
- time-series schema: 11 columns, common header checksum
  `730d272a0c60f8bce285e4659f437253af1da663b6ec69d2153fe39c531ac2b5`;
- tracked compact-result checksum:
  `28c68acecdce55787189ddd981c097d1748504dab43b3777b896638652fb70f2`.

The observed cycle-data headers contain cycle index, start/end time, test time,
minimum/maximum current and voltage, charge/discharge capacity, and
charge/discharge energy. The time-series headers additionally expose timestamp,
environment-temperature, and cell-temperature columns. Header units are retained
as source evidence only and are not calibration or channel-binding evidence.

The recorded decision remains bounded:

- bounded schema observation: `bounded_schema_observed`;
- capacity-check versus bulk-cycle discrimination:
  `header_and_first_rows_insufficient`;
- cycle command to rows: `not_established`;
- instrument channel to columns: `not_established`;
- physical cell to entry: `not_established`;
- official distribution snapshot: `not_established`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- overall: `bounded_schema_observed_gate_not_passed`;
- scientific closeout: `diagnostic`.

Candidate roles are not promoted to command, measurement-channel, calibration,
or physical-cell bindings. The six representatives do not establish all-file or
full-file consistency. See
[Battery SNL LFP Bounded CSV Schema Read](BATTERY_SNL_LFP_BOUNDED_SCHEMA_READ.md).

The v2.5 compatibility and retrieval-reproducibility conclusions are unchanged.
Battery retrieval reproducibility remains `insufficient_evidence`, and no
network, credential, acquisition, source mutation, cohort merge, model training,
metric recomputation, or public-version change is added.

## Next Evidence

The next step must remain a separate bounded contract. v2.6.9 may test whether
capacity-check and bulk-cycling records can be discriminated without reading
complete files or inferring undocumented command semantics.

Before implementation, the contract must predeclare:

- the minimum cycle-index span or exact cycle rows required;
- whether cycle-data alone is sufficient or a matched time-series slice is
  necessary;
- explicit stop conditions for missing, non-monotonic, or ambiguous cycle indices;
- rules separating observed values from commanded setpoints;
- output fields that record ambiguity rather than forcing a classification.

The next stage must not silently expand to all files, full-file reads, cohort
merging, target alignment, model execution, or mechanism claims.

Independently, a provider-issued release identifier or official checksum for the
exact `SNL LFP.zip` remains the strongest missing source-snapshot evidence.

## Non-Goals

v2.6 does not add deep learning, LSTM, Transformer, GNN, PINN, AutoML,
hyperparameter search, automatic acquisition, heterogeneous dataset merging,
mechanism fitting, lifetime prediction, UI, tag, or release work.
