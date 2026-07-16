# Dynamic Physics and Graph Readiness

Status: `schema_readiness_only`

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

For v2.2.3, crystal structures can be assessed as
`graph_adapter_candidate`, `blocked_disorder`, `blocked_missing_lattice`,
`blocked_missing_sites`, or `blocked_unknown_semantics`. This is graph
construction contract eligibility only; no neighbor policy is selected and no
graph is built.

## Non-goals

No DFT, FEM, CFD, differential equation solver, graph model, GNN training,
feature tensor generation, or new predictive claim is introduced in this step.
