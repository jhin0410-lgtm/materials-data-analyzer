# Cross-Domain PGIR Reuse Evidence

Status: `demonstrated_with_restrictions`

Battery and Materials now use the same representation-governance machinery,
while retaining distinct domain semantics.

## Reused Framework

- PGIR concept registry;
- representation declaration;
- schema ownership;
- maturity assessment;
- conformance findings;
- context compatibility;
- transition validation;
- selected operator registry framework;
- uncertainty boundary;
- provenance and lineage references; and
- trust and claim boundaries.

## Domain Differences Preserved

| Dimension | Battery | Materials |
| --- | --- | --- |
| Source semantics | Measured cycle records | Computed relaxed structures |
| Primary forms | Observation, bounded operational State, Trajectory | Composition, `CrystalStructureEntity`, descriptor, `GraphEntity` |
| Time | Cycle index; physical time incomplete | Post-relaxation snapshot context |
| Uncertainty | Source measurement uncertainty unavailable | Per-record structure uncertainty unavailable |
| Evaluator scope | Descriptive trajectory consistency | Structure integrity and composition consistency |
| Scientific claim | No mechanism or prediction | No DFT replacement, GNN, or broad predictive improvement |

## Verdict Dimensions

- Architecture reuse: `true`
- Representation-contract reuse: `true`
- Conformance-engine reuse: `true`
- Operator-framework reuse: `true`
- Physical-operator reuse: `false` / `not_demonstrated`
- Independent validation: `false`
- Production validation: `false`

This is second-domain representation reuse, not evidence for a universal
physics platform. A shared registry and conformance engine do not imply that
Battery and Materials use the same physical relations, operators, mechanisms,
uncertainty models, or claim scope.
