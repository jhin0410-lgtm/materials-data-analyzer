# Crystal Structure Entity Adapter

Status: `v2.2.3_complete`

The Materials Project structure adapter converts a small runtime structure mapping, or an object exposing `as_dict()`, into a JSON-safe `CrystalStructureEntity`. Runtime objects are not persisted.

## Mapping

Identity:

- `entity_id`: deterministic material ID plus structure checksum suffix
- `entity_type`: `CrystalStructureEntity`
- `schema_id`: `scientific_entity_schema_v2`
- `schema_version`: `2.2.2`
- `domain`: `materials`

Attributes:

- 3x3 lattice matrix in angstrom
- periodic axes
- site index
- species and occupancy
- fractional coordinates
- structure-derived composition
- reduced composition
- ordered/disordered status
- source material ID and adapter version

Quantities:

- lattice lengths in `angstrom`
- lattice angles in `degree`
- cell volume in `angstrom^3`
- density in `g/cm^3` when safely available
- target quantity in `eV/atom`

## Validation Boundary

The integrity check validates shape and metadata only:

- finite 3x3 lattice matrix
- positive lattice determinant/volume
- non-empty sites
- finite fractional coordinates
- valid species identifiers
- positive occupancy
- duplicate site records
- disorder warnings

The validator does not mutate source artifacts, infer symmetry, identify phases, construct graphs, or prove predictive value.

## Uncertainty

Materials Project summary and structure payloads do not provide direct uncertainty for lattice, density, volume, or energy-above-hull values. v2.2.3 records uncertainty as `unavailable` with reason `source_does_not_provide_uncertainty`; it does not write zero uncertainty or an invented confidence score.
