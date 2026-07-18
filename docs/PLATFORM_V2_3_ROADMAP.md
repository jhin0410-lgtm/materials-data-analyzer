# Platform v2.3 Roadmap

Status: `released_as_v2.3.0`

v2.3 moves from v2.2 scientific metadata and Materials structure evidence
toward a Physically Grounded Intermediate Representation (PGIR). The roadmap is
governance-first: it introduces representation contracts before any mechanism
solver, model retraining, or experiment recommendation.

## v2.3.1

- PGIR architecture RFCs.
- Current implementation to PGIR mapping.
- Representation maturity model.
- Schema ownership and compatibility governance.
- Capability-stage registry.
- CLI inspection commands and optional platform-report section.

## v2.3.2

- PGIR conformance gates for representation declarations, maturity promotion,
  context compatibility, registered transitions, and capability eligibility.
- Battery Observation, bounded operational State, and Trajectory adapter pilot
  using existing processed battery summaries only.
- Compact tracked Battery PGIR coverage, maturity, transition,
  mechanism-readiness, and decision summaries.
- Battery cycle rows remain observations unless a registered transformer and
  sufficient context justify a bounded operational summary.
- No degradation mechanism fitting, solver execution, SOH/RUL model, or
  predictive claim.

## v2.3.3

- Dynamic mechanism candidate audit completed for Battery PGIR.
- Diffusion versus Arrhenius feasibility comparison completed as an
  evidence-gap and identifiability audit.
- Data sufficiency and identifiability gates completed with actual Battery
  coverage.
- Outcome: `descriptive_evaluator_only`; no Arrhenius, diffusion, SOH/RUL, or
  predictive mechanism claim.

## v2.3.4

- Completed the selected bounded capacity-trajectory consistency Evaluator on
  34 actual trajectories and 2,495 operational states.
- Recorded 33 eligible-with-warning trajectories, one blocked short
  trajectory, deterministic findings, separated trust dimensions, and compact
  claim evidence.
- Result: `descriptive_evaluator_executed_with_restrictions`; not a general
  solver, Propagator, Arrhenius fit, diffusion model, or predictive model.

## v2.3.5

- Completed exact immediate-source lineage for 34 cells and recovered only
  source-supported timestamp, ambient-temperature, duration, measured-signal,
  group-protocol, and impedance-availability metadata.
- Completed nine predeclared threshold, reference, window, and gap sensitivity
  runs and consolidated overlapping findings into bounded descriptive events.
- Result: `descriptive_evaluator_stable_with_policy_restrictions`; mechanism
  attribution remains blocked, source uncertainty remains unavailable, and the
  official original NASA snapshot/version remains unresolved.

## v2.3.6

- Deferred beyond v2.3.0 and addressed in v2.4.1: second-domain
  representation-governance reuse over existing Materials structure records.
- v2.4.1 demonstrates architecture, representation-contract, conformance, and
  operator-framework reuse with restrictions. It does not demonstrate a
  cross-domain physical operator or mechanism.

## v2.3 Closeout

v2.3.0 closes one dynamic-domain workflow with explicit mechanism-evidence and
claim boundaries. It preserves `descriptive_evaluator_stable_with_policy_restrictions`,
selects no representative mechanism, and leaves source uncertainty and the
official original NASA snapshot unresolved. General physics intelligence,
production scientific decisions, GNN/PINN, dashboard UI, and autonomous
experiment recommendation remain out of scope unless separately implemented
and validated.
