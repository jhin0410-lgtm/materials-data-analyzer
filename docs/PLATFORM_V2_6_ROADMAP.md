# Platform v2.6 Roadmap

Status: `v2.6.6_snl_lfp_artifact_binding_feature_stage_complete`

## Release Boundary

`v2.4.0` remains the current public release. v2.6.1 through v2.6.6 are
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
may stream `SNL LFP.zip` to compute SHA-256 and read its ZIP central directory to
record entry names, sizes, CRC values, safe paths, cycle/time-series pairing,
and filename-label provenance. It does not read entry payloads or CSV rows and
does not extract the archive.

The raw archive is ignored by Git and is unavailable in the GitHub execution
context. The tracked result therefore records:

- local artifact inventory binding: `pending_local_artifact`;
- document-to-archive binding: `not_established`;
- official distribution snapshot: `not_established`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`.

A local run may produce `local_artifact_inventory_bound` only when the archive
matches the expected 60-entry, 30-pair contract and has no traversal, duplicate,
or encrypted entries. That result still does not promote filename labels to
scientific metadata or establish an official source snapshot.

See [Battery SNL LFP Artifact Binding Audit](BATTERY_SNL_LFP_ARTIFACT_BINDING_AUDIT.md).

The v2.5 compatibility and retrieval-reproducibility conclusions are unchanged.
Battery retrieval reproducibility remains `insufficient_evidence`, and no
network, credential, acquisition, source mutation, model training, metric
recomputation, or public-version change is added.

## Next Evidence

Run v2.6.6 in a local checkout that contains the ignored
`data/raw/battery_archive/SNL LFP.zip`. Retain the resulting archive checksum and
central-directory manifest as local evidence. Do not commit the raw archive or
row-level manifest.

If the local inventory binds successfully, the next scientific task is not a
loader. It is a source-to-entry binding review that seeks an independently
verifiable official distribution identity and explicit mapping from documented
study cells and conditions to archive entries. CSV row or header inspection must
remain deferred until that review defines a justified, bounded read contract.

## Non-Goals

v2.6 does not add deep learning, LSTM, Transformer, GNN, PINN, AutoML,
hyperparameter search, automatic acquisition, heterogeneous dataset merging,
mechanism fitting, lifetime prediction, UI, tag, or release work.
