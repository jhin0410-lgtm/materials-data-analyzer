# Scientific Entity Model

Status: `scaffold_stage`

v2.2.2 introduces JSON-safe scientific entity records for compositions,
structures, measurement series, states, trajectories, and graphs. The goal is to
represent scientific identity and relationships without storing live Python
objects or replacing existing DataFrame workflows.

## Runtime Object vs Persisted Record

Runtime dataclasses are convenience wrappers. Persisted records are deterministic
JSON-compatible dictionaries with schema identifiers and checksums. The local
registry stores compact metadata and artifact references, not live objects.

## Initial Entity Types

- `MaterialCompositionEntity`: formula, elements, stoichiometric amounts,
  normalized atomic fractions, and composition provenance.
- `CrystalStructureEntity`: lattice, sites, species, fractional coordinates,
  occupancy and periodic-boundary metadata.
- `MeasurementSeriesEntity`: independent/dependent quantity metadata, axis
  metadata, conditions, calibration metadata, and optional artifact-backed data.
- `StateEntity`: state variables, time, conditions, and boundary-condition refs.
- `TrajectoryEntity`: ordered state refs, time axis, transition/operator refs,
  solver metadata, numerical tolerance, and convergence status.
- `GraphEntity`: node/edge records, periodic-edge metadata, graph construction
  metadata, and source entity refs.

## Boundary

The entity layer is not a simulator, structure acquisition tool, GNN feature
generator, or model runner. Graph and trajectory entities are metadata contracts
for future work only.
