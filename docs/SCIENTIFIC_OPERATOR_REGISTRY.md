# Scientific Operator Registry

Status: `v2.2.5_complete`

The selected scientific operator registry is an explicit metadata registry. It stores operator contracts, not arbitrary Python callables. It does not import config-supplied modules, scan the filesystem, call the network, train models, or execute acquisition.

## Registered Operators

- `mp_summary_to_composition_entity_v1`
- `mp_structure_to_crystal_entity_v1`
- `mp_target_to_quantity_v1`
- `crystal_structure_integrity_check_v1`
- `composition_structure_consistency_check_v1`
- `crystal_basic_geometry_summary_v1`
- `crystal_structure_to_descriptor_summary_v1`
- `crystal_structure_to_radius_graph_v1`
- `structure_snapshot_alignment_check_v1`

Each operator records input entity types, output types, required fields, side-effect policy, network policy, uncertainty policy, provenance policy, determinism, and bounded input policy.

## Execution Boundary

The registry supports inspection and validation. It does not make a generic
execution engine and does not allow arbitrary callable references. Current
adapter behavior is limited to bounded, already-loaded runtime mappings and
local-only artifact construction.

## Claim Boundary

Geometry and graph summaries are descriptive metadata or candidate artifacts.
v2.2.5 evaluates selected structure descriptors in a bounded known-structure
comparison and records `structure_predictive_value_limited`. It does not add
arbitrary operator execution, use graph artifacts as model inputs, or change
the v2.2.1 `performance_degraded` conclusion.
