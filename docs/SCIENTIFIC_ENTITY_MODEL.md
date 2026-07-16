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

## v2.2.3 Materials Project Structure Adapter

`CrystalStructureEntity` now has a concrete synthetic/adapter contract for
Materials Project structure payloads. Runtime MP or pymatgen-like objects may
be read inside the adapter, but persisted records contain only JSON-safe
lattice matrices, sites, composition metadata, quantity fields, provenance
references, and checksums. Row-level real MP structures remain local-only.

## v2.2.4 Structure and Graph Artifacts

The existing 838 Materials Project material IDs were enriched with current MP
structures and converted into 838 valid `CrystalStructureEntity` records. A
deterministic periodic radius-graph artifact was generated for each valid
entity as a local-only `GraphEntity` JSONL.

These records demonstrate representation and lineage readiness. They do not
make a graph neural network claim, a structure-aware model claim, or a DFT
replacement claim.

## v2.2.5 Known-Structure Comparison

v2.2.5 uses Tier-1 descriptor columns derived from the structure entities for a
bounded known-structure comparison. It does not persist live objects, use graph
entities as model inputs, or select a representative structure-aware model.
