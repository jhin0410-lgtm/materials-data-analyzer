# Dynamic Physics and Graph Readiness

Status: `v2.2.4_graph_artifact_pilot_complete`

v2.2.2 defines metadata contracts for future dynamic simulation and graph
representation. It does not implement a solver, simulator, graph neural network,
tensor generator, or structure acquisition workflow.

## Dynamic State and Trajectory Contract

`StateEntity` and `TrajectoryEntity` can represent initial conditions, boundary
conditions, parameter quantities, time-step metadata, transition operator refs,
solver metadata, numerical tolerance, convergence status, and uncertainty or
numerical error metadata.

## Graph Contract

`CrystalStructureEntity` and `GraphEntity` can represent lattice/site metadata,
node/edge records, periodic-edge metadata, graph construction operator refs, and
source checksums. The phrase GNN-ready means schema readiness only, not model
readiness or predictive validity.

For v2.2.4, the existing 838 Materials Project structure entities were assessed
as graph candidates and 838 deterministic periodic radius-graph artifacts were
generated locally. The graph artifacts have unique checksums, exclude target
values, and record `gnn_execution=false`.

This remains representation readiness only. A graph artifact is not evidence
that a GNN, graph tensor, graph embedding, or structure-aware predictive model
is valid.

v2.2.5 keeps that boundary: known-structure predictive comparison uses Tier-1
descriptor columns only. The periodic graph artifacts remain local evidence of
deterministic representation, not model inputs.

## Non-goals

No DFT, FEM, CFD, differential equation solver, graph model, GNN training,
feature tensor generation, or new predictive claim is introduced in this step.

## v2.3.1 PGIR Boundary

PGIR defines how future dynamic state, field, parameter, initial condition, and
boundary condition records should be governed. The current project remains at
representation governance for those concepts. `Propagator` capability is
`concept_defined` only, so dynamic physics execution remains future work.
