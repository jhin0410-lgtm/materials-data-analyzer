# Platform v2.6 Roadmap

Status: `released_within_v2.7.0_line_closed`

## Release Boundary

v2.6.1 through v2.6.14 are completed internal feature stages included in the
public `v2.7.0` release. The checksum-bound Battery evidence line remains closed;
no automatic v2.6.15 stage is authorized.

This boundary is preserved rather than erased. The later characterization
handoff, public producer-consumer workflows, representative NIST workflow,
repository hardening, and release governance are post-v2.6 work and establish
the v2.7.0 public minor-release boundary.

## v2.6.1 Warm-Start Forecast Benchmark

v2.6.1 uses the tracked Kaggle NASA-derived Battery table and adds exact
five-cycle target alignment, battery-disjoint GroupKFold evaluation,
persistence and fixed Ridge baselines, train-only preprocessing, per-battery and
pooled metrics, and deterministic validation artifacts.

The result is `unsupported`: Ridge pooled MAE is `4.1537` versus persistence
`3.4256`, and Ridge improves on 13 of 33 evaluated batteries. The scenario is
warm-start cross-battery forecasting, not zero-shot. It does not establish SOH,
RUL, lifetime, mechanism, external-generalization, or engineering evidence.

## v2.6.2 Failure Diagnostics

The deterministic diagnostics preserve every v2.6.1 prediction and metric. The
top five batteries account for `90.35%` of Ridge excess absolute error, but no
leave-one-battery-out exclusion reverses persistence superiority. The result
remains diagnostic, not a mechanism or generalization finding.

## v2.6.3 Comparability Evidence

Chemistry, nominal capacity, cycle-specific commanded protocols, cutoff policy,
calibration/uncertainty, and the official NASA snapshot remain unresolved or
heterogeneous. Decision: `comparability_not_established`; scientific closeout:
`inconclusive`.

## v2.6.4 External-Cohort Admission

The local Battery Archive-style candidate receives:

- inventory review: `admitted_with_restrictions`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- overall: `not_admitted_for_cross_cohort_validation`.

No raw archive is extracted, no filename label is promoted to source-backed
metadata, and no model or metric is changed.

## v2.6.5-v2.6.10 SNL LFP Evidence

The bounded SNL line performs source-document recovery, local ZIP identity and
safe-entry inventory, repository nomenclature review, six-file schema
observation, 24-row cycle-regime review, and transition-artifact consistency
closeout.

Useful document, archive, schema, and candidate-regime evidence is recorded, but
exact physical-cell identity, cycle-command-to-row binding, instrument-channel
semantics, official versioned distribution identity, cross-cohort comparability,
and predictive-validation eligibility remain unestablished.

Recorded stage decisions include:

- v2.6.5: `source_evidence_recovered_gate_not_passed`;
- v2.6.6: `local_artifact_inventory_bound_gate_not_passed`;
- v2.6.7: `condition_group_nomenclature_bound_gate_not_passed`;
- v2.6.8: `bounded_schema_observed_gate_not_passed`;
- v2.6.9: `bounded_cycle_regime_evidence_recorded_gate_not_passed`;
- v2.6.10: `transition_artifact_consistency_recorded_gate_not_passed`.

Candidate source-sequence labels are never promoted to confirmed command or
measurement semantics.

## v2.6.11-v2.6.13 Michigan Source Path

v2.6.11 selects Michigan Formation for source binding only, not cohort
admission. v2.6.12 recovers provider-package structure but not an exact file
manifest or provider-to-local artifact binding. v2.6.13 records an observed
provider metadata-access HTTP 403 without claiming global Deep Blue
unavailability.

Decisions:

- v2.6.11: `next_source_candidate_selected_gate_not_passed`;
- v2.6.12:
  `provider_package_structure_recovered_exact_manifest_not_established_gate_not_passed`;
- v2.6.13: `provider_metadata_endpoint_access_denied_gate_not_passed`.

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

## Closeout and Reopen Conditions

`v2.6 is closed`. No automatic v2.6.15 feature stage is authorized. The line may
be reopened only when materially new predeclared evidence exists, such as an
official versioned source snapshot with stable checksums, source-backed protocol
and calibration metadata, verified provider-to-local binding, or an independent
cohort that passes comparability and admission gates.

Repeated provider-access workarounds, larger arbitrary reads, another model
family, hyperparameter tuning, or purposeless dataset collection are not valid
reopen conditions.

## v2.7.0 Integration Context

The later public-repository and process-characterization work does not alter the
v2.6 Battery conclusions. Its separate public minor-release context is recorded
in [`docs/releases/V2_7_0.md`](releases/V2_7_0.md).

## Non-Goals

v2.6 does not claim deep-learning superiority, zero-shot forecasting, SOH/RUL or
lifetime prediction, mechanism fitting, automatic acquisition, heterogeneous
cohort merging, independent predictive validation, UI deployment, or autonomous
engineering decisions.
