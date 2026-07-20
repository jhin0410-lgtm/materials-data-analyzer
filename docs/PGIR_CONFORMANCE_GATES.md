# PGIR Conformance Gates

Status: `v2.3.2_completed`

v2.3.2 turns the v2.3.1 PGIR registries into explicit conformance checks for
representation-producing code. The gates validate concept/schema ownership,
context compatibility, maturity promotion evidence, transition registration,
and capability eligibility.

## Boundary

The conformance layer is governance, not scientific correctness. It does not
run solvers, train models, call APIs, infer mechanisms, fit parameters, or
promote compact metadata into physical evidence.

## Gate Types

- Declaration gate: validates a representation declaration against registered
  PGIR concepts and schema ownership.
- Maturity gate: blocks promotion unless context-specific evidence is present.
- Context gate: prevents Observation records from being reused as latent
  State, Field, or mechanism-ready data without a registered transformer.
- Transition gate: allows only registered deterministic representation
  transitions.
- Capability gate: blocks operations whose minimum maturity or required
  context is unavailable.

## Current Battery Use

Battery cycle rows can be declared as PGIR Observation metadata, transformed
into bounded operational State summaries, and ordered into Trajectory metadata.
That path does not infer internal concentration, diffusion coefficient, SEI
thickness, lithium inventory, RUL, SOH prediction, or degradation mechanism
evidence.

Tracked compact outputs live under `data/processed/battery_v2_3_*`. Row-level
Observation, State, and Trajectory JSONL artifacts are generated only under
ignored `outputs/battery_pgir_v2_3/`.

## v2.3.3 Mechanism Audit Gates

v2.3.3 adds mechanism requirement and identifiability audits on top of these
gates. The audits can select a bounded descriptive Evaluator, but they still
block Propagator, Estimator, Calibrator, Arrhenius fitting, diffusion solving,
and predictive battery model claims when evidence is missing.

## v2.3.4 Evaluator Gate

The capacity-trajectory evaluator requires the existing schema, ordering,
units, reference-policy, lineage, and `dimensionally_valid` maturity gates
before execution. A valid run creates result evidence only; it does not promote
the source trajectory to mechanism-compatible or independently validated.

## v2.4.1 Materials Gates

Five Materials transitions are explicitly registered: MP structure document
to crystal entity, structure integrity evaluation, composition consistency
evaluation, descriptor transformation, and periodic graph transformation.
The local 838-entity audit applies existing schema, context, dimensional,
admissibility, transition, and operator gates. A valid structure is not
promoted to phase-stability evidence, experimental validation, GNN readiness,
or predictive value.

## v2.4.2 Bounded Propagator Gate

The `bounded_physical_propagation` capability requires a registered model
contract, registered operator, physically admissible input declaration, and a
bounded execution policy. Exact, FTCS, and evaluator transitions are explicit.
Their successful execution promotes only the benchmark field/result artifacts
to bounded `scientifically_evaluated` maturity. It does not promote Battery
data, other domains, or the platform to independent or production validation.
