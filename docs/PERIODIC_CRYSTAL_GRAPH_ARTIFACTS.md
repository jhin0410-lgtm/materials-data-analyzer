# Periodic Crystal Graph Artifacts

Status: `v2.2.4_complete`

v2.2.4 creates deterministic periodic graph artifacts from
`CrystalStructureEntity` records using a bounded radius graph policy. The graph
artifact is a representation pilot, not a GNN input validation or model result.

## Graph Builder

Default operator:

```text
crystal_structure_to_radius_graph_v1
```

Policy:

- fixed radius cutoff
- periodic image handling
- deterministic node ordering
- deterministic edge ordering
- bounded `max_neighbors`
- bounded `max_edges`
- no self-edges
- no target values in nodes or edges

## Actual v2.2.4 Result

- source entities: 838
- graph artifacts generated: 838
- graph-eligible entities: 838
- graph checksums unique: true
- target values included: false
- GNN execution: false

The row-level graph JSONL is local-only under:

```text
outputs/materials_project_structure_v2_2/graphs/
```

Tracked outputs contain only compact eligibility and size summaries.

## Boundary

The graph artifact preserves periodic geometry and construction metadata. It
does not create graph tensors, graph embeddings, a graph neural network,
structure-aware model evidence, or a feature-importance explanation.

## v2.2.6 Closeout

The capability matrix records periodic graphs as `artifact_generated` only.
They were not model inputs, not group-evaluated, and not used as evidence for a
GNN, graph embedding, or graph-model claim.
