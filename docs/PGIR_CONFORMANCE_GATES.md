# PGIR Conformance Gates

Status: `development_stage`

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
