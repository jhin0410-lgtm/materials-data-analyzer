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

## v2.2.6 Closeout

The closeout records `CrystalStructureEntity` as executed representation
evidence, structure descriptors as limited predictive evidence, and
`GraphEntity` artifacts as representation-only. Entity availability is not
treated as proof of predictive value, DFT replacement, or GNN readiness.

## v2.3.1 PGIR Mapping

PGIR maps existing entity records to canonical roles without renaming the
runtime classes or persisted schema IDs. `MeasurementSeriesEntity` maps to
Observation, `StateEntity` maps to State/Field/condition concepts by context,
and `GraphEntity` remains a representation artifact. Observation is not
automatically State, and entity availability is not mechanism evidence.

## v2.3.2 Battery Entity Pilot

The Battery PGIR pilot instantiates this boundary on actual processed battery
cycle summaries: cycle rows become `MeasurementSeriesEntity` Observation
metadata, derived operational summaries become `StateEntity`, and ordered
per-cell summaries become `TrajectoryEntity`. The State is explicitly bounded
to operational summary variables and is not a latent electrochemical state.

## v2.4.1 External Source And Materials Reuse

External source contracts are provenance records, not new scientific entity
types. They reference released Materials entities and Battery artifacts through
stable IDs and compatibility adapters. The Materials reuse audit keeps all 838
row-level declarations local-only and tracks only aggregate conformance counts.
Runtime pymatgen objects, API responses, structure bodies, and graph bodies are
not persisted in the source registry.
