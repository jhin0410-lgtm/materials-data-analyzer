# Battery Observation, Operational State, And Trajectory

Status: `development_stage`

v2.3.2 separates three battery representation levels.

## Observation

A cycle-level discharge summary is an Observation. It records measured or
source-reported quantities, derivation metadata, units, source provenance, and
uncertainty availability. It is not a latent electrochemical state.

## Operational State Summary

An operational State summary is a bounded row-level summary derived from one
Observation. It can contain measured discharge capacity, capacity retention,
ambient temperature, cycle index, and cycle type. It explicitly marks
`complete_electrochemical_state = false`.

## Trajectory

A Trajectory is an ordered per-cell sequence of operational State summaries
using `cycle_index` as the ordering axis. It rejects mixed cells and duplicate
cycle indices. The cycle-index axis is not treated as physical elapsed time.

## Local Artifact Policy

The row-level Observation, State, and Trajectory JSONL files are local-only
outputs under `outputs/battery_pgir_v2_3/`. Tracked outputs are compact
coverage, maturity, transition, mechanism-readiness, and decision summaries.

## v2.3.3 Identifiability Boundary

The v2.3.3 audit treats the Trajectory as ordered cycle metadata. It can
support descriptive capacity-trajectory checks, but it is not a diffusion
trajectory, calendar-aging axis, or complete electrochemical state path.

## v2.3.4 Evaluator Use

The capacity evaluator consumes the local ordered State references and checks
lineage before computation. It does not promote the Trajectory entity itself to
PGIR L6; only the result artifact records bounded evaluator execution evidence.
Cycle gaps remain ordering findings and are never interpreted as physical time.
