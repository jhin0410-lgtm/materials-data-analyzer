# Platform v2.6 Roadmap

Status: `released_as_v2.6.0`

## Release Boundary

v2.6.1 through v2.6.14 are completed internal feature stages included in the
public `v2.6.0` release. The checksum-bound evidence line is closed; no automatic
v2.6.15 stage is authorized.

The v2.5.1-v2.5.2 compatibility and retrieval-reproducibility stages are also
included in v2.6.0. A separate v2.5.0 release was not created.

## v2.6.1 Warm-Start Forecast Benchmark

v2.6.1 uses the tracked Kaggle NASA-derived Battery table and adds exact
five-cycle target alignment, current and lagged retention features,
battery-disjoint GroupKFold evaluation, persistence and fixed Ridge baselines,
train-only preprocessing, per-battery and pooled metrics, and deterministic
validation artifacts.

The result is `unsupported`: Ridge pooled MAE is `4.1537` versus persistence
`3.4256`, and Ridge improves on 13 of 33 evaluated batteries. The scenario is
warm-start cross-battery forecasting, not zero-shot. It does not establish SOH,
RUL, lifetime, mechanism, causal, external-generalization, or engineering
evidence.

## v2.6.2 Failure Diagnostics

Deterministic diagnostics preserve every v2.6.1 prediction and metric. The top
five batteries account for `90.35%` of Ridge excess absolute error, but no
leave-one-battery-out result reverses persistence superiority. Ridge remains
worse in fixed early, middle, and late regimes. The result remains diagnostic,
not a mechanism or predictive-generalization finding.

## v2.6.3 Comparability Evidence

The evidence matrix reviews chemistry, nominal capacity, temperature,
charge/discharge protocols, cutoff voltage, calibration/uncertainty, and source
snapshot/version. Required cross-battery equivalence is not established.
Chemistry, nominal capacity, cycle-specific commands, cutoff policy,
calibration/uncertainty, and the official NASA snapshot remain unresolved or
heterogeneous. Decision: `comparability_not_established`; scientific closeout:
`inconclusive`.

## v2.6.4 External-Cohort Admission

The first local Battery Archive-style candidate receives:

- inventory review: `admitted_with_restrictions`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- overall: `not_admitted_for_cross_cohort_validation`.

No raw archive is extracted, no filename label is promoted to source-backed
metadata, and no model or metric is changed.

## v2.6.5 SNL LFP Source Evidence

Official Battery Archive, DOE OSTI, and Sandia documentation identifies the
commercial A123 APR18650M1A LFP cell, 1.1 Ah nominal capacity, study equipment,
protocol groups, capacity-check procedure, and the 2.0-3.6 V 100% DOD regime.
This remains document-level evidence and is not bound to exact local cells,
cycles, commands, channels, or a versioned distribution snapshot. Overall:
`source_evidence_recovered_gate_not_passed`.

## v2.6.6 SNL LFP Artifact Binding

The bounded ZIP audit records archive SHA-256
`006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d`,
60 safe entries, 30 cycle CSVs, 30 time-series CSVs, and 30 complete pairs.
Entry payloads are not read or extracted. Local inventory identity is verified,
but official distribution identity and row semantics remain unestablished.
Overall: `local_artifact_inventory_bound_gate_not_passed`.

## v2.6.7 Source-to-Entry Binding

Official nomenclature is linked to 12 condition-group entry patterns. The
publication-to-repository and repository nomenclature links are established,
but physical cell identity, cycle-command-to-row binding, instrument-channel
binding, and official snapshot identity are not. Overall:
`condition_group_nomenclature_bound_gate_not_passed`.

## v2.6.8 Bounded CSV Schema Read

Six predeclared representative CSVs are opened. Six headers and 30 sampled rows
match the bounded schema contract. The observations do not establish capacity-
check versus bulk-cycle semantics, cycle commands, measurement channels,
physical-cell identity, or cross-cohort admission. Scientific closeout:
`diagnostic`; overall: `bounded_schema_observed_gate_not_passed`.

## v2.6.9 Bounded Cycle-Regime Review

Exactly 24 cycle-summary rows are read from three predeclared representatives.
Positions 1-3 are recorded as `capacity_check_candidate`; positions 4-8 are
`bulk_cycle_candidate`. These source-sequence candidates are not promoted to
confirmed labels. No common separating field exists across all protocol
families, and row 4 remains transition-ambiguous. Overall:
`bounded_cycle_regime_evidence_recorded_gate_not_passed`.

## v2.6.10 Transition-Artifact Closeout

Study-level transition evidence is checked against the bounded row observations.
The evidence is consistent with a transition artifact candidate but is not bound
to an exact row or command. Decision:
`transition_artifact_consistency_recorded_gate_not_passed`; scientific status:
`diagnostic`.

## v2.6.11 Next External Source Selection

Michigan Formation is selected as the next source candidate for source-binding
work only. This selection does not admit it as an external validation cohort.
Decision: `next_source_candidate_selected_gate_not_passed`.

## v2.6.12 Michigan Provider-Package Structure

Provider-package structure is recovered, but an exact file manifest and
provider-to-local artifact binding are not established. Decision:
`provider_package_structure_recovered_exact_manifest_not_established_gate_not_passed`.

## v2.6.13 Michigan Provider-Metadata Access

The bounded provider metadata request records an HTTP 403. This observation
prevents top-level file-set metadata recovery for that path but does not prove
global Deep Blue API unavailability. Decision:
`provider_metadata_endpoint_access_denied_gate_not_passed`; scientific status:
`inconclusive`.

## v2.6.14 External-Evidence-Line Closeout

The final closeout verifies all 13 v2.6 stage artifacts in order with canonical
checksums. Final decisions:

- evidence-line integrity: `verified`;
- registered NASA benchmark: `preserved`;
- persistence scope: `registered_nasa_warm_start_benchmark_only`;
- Ridge generalization: `unsupported`;
- cross-cohort comparability: `not_established`;
- external-cohort admission: `not_admitted`;
- predictive-validation readiness: `not_ready`;
- provider-to-local binding: `not_established`;
- engineering-decision readiness: `not_ready`;
- scientific closeout: `inconclusive`.

The primary limitation is missing source-backed compatible chemistry, nominal
capacity, commanded protocols, cutoff policy, calibration/uncertainty, target
definition, stable source snapshot, and provider-to-local row-level binding. It
is not a lack of model complexity.

## Integrated v2.6.0 Public Scope

The public release also includes reviewed public-repository hardening,
checksum-bound characterization-bundle consumption, pinned DWCNT/RWGS/four-
carbon/NIST cross-repository workflows, and the representative NIST process-
characterization workflow with identifiability audit and bounded next-design
planning.

These integrations do not change the Battery evidence-line conclusions. The
complete public release scope and nonclaims are recorded in
[`docs/releases/V2_6_0.md`](releases/V2_6_0.md).

## Reopen Conditions

The Battery evidence line may be reopened only when materially new predeclared
evidence exists, such as an official versioned source snapshot with stable
checksums, source-backed protocol and calibration metadata, verified
provider-to-local binding, or an independent cohort that passes comparability
and admission gates.

Repeated provider-access workarounds, larger arbitrary reads, another model
family, hyperparameter tuning, or purposeless dataset collection are not valid
reopen conditions.

## Non-Goals

v2.6 does not claim deep-learning superiority, zero-shot forecasting, SOH/RUL or
lifetime prediction, mechanism fitting, automatic acquisition, heterogeneous
cohort merging, independent predictive validation, UI deployment, or autonomous
engineering decisions.
