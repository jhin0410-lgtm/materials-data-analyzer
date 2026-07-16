# Materials v2.2 Scientific Evidence

Status: `release_ready`.

v2.2 records three distinct evidence levels:

| Evidence item | Context | Status | Interpretation |
| --- | --- | --- | --- |
| Composition-derived physics features | `composition_only_pre_structure` | `predictive_value_not_supported` | Features were built and used, but the matched group-aware comparison degraded. |
| Known-structure descriptors | `known_structure_post_relaxation` | `predictive_value_limited` | Descriptors improved only one primary group split. |
| Periodic graph artifacts | `known_structure_post_relaxation` | `artifact_generated` | Deterministic graph artifacts exist, but no graph model or GNN used them. |

The original v1.3 `energy_above_hull` target remains the source of truth. The
current Materials Project target value was used only for snapshot-alignment
auditing.

## Key Counts

- composition feature rows: 838
- existing-ID structure documents returned: 838
- snapshot-aligned structures: 838
- valid `CrystalStructureEntity` records: 838
- known-structure cohort rows: 838
- periodic graph artifacts: 838

## Preserved Results

- v2.2.1 remains `performance_degraded`.
- v2.2.5 remains `structure_predictive_value_limited`.
- representative model remains `none`.

These outcomes are intentionally retained; the release does not tune, rerun, or
reinterpret the results to make them look stronger.
