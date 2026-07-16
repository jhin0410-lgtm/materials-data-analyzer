# Materials Structure Descriptors

Status: `v2.2.4_complete`

v2.2.4 defines and builds Tier-1 structure descriptor candidates from
JSON-safe `CrystalStructureEntity` records. Descriptors are available only in
the `known_structure_post_relaxation` prediction context.

## Descriptor Set

The tracked descriptor definition snapshot includes 12 Tier-1 definitions:

- `structure_volume_per_atom`
- `structure_density`
- `ordered_structure_flag`
- `crystal_system_category`
- `space_group_number_category`
- `nearest_neighbor_distance_mean`
- `nearest_neighbor_distance_std`
- `nearest_neighbor_distance_cv`
- `coordination_number_mean`
- `coordination_number_std`
- `packing_fraction_candidate`
- `site_count`

`crystal_system_category` and `space_group_number_category` use source-provided
symmetry metadata only. v2.2.4 does not perform its own symmetry
identification.

## Actual Coverage

Descriptors were generated for 838 converted structure entities. All generated
rows record `target_accessed=False`.

`packing_fraction_candidate` is intentionally unavailable because this step
does not introduce a radius table or a validated packing-fraction definition.

## Invariance Boundary

Raw lattice matrices, raw lattice constants, flattened fractional coordinates,
row indices, material IDs, and database timestamps are not primary predictive
features in v2.2.4. They are representation-dependent or identity-like fields.

Future use of raw lattice or coordinate features would require a standardized
cell policy, equivalent-cell checks, and invariance tests.

## Claim Boundary

These descriptors are candidates and diagnostics. They are not validated
predictive features, not a physics-constrained model, and not evidence that
the v2.2.1 composition-feature result improved.
