# PGIR Current Architecture Audit

Status: `accepted_for_v2_3`

This audit maps the existing v2.2 implementation to the v2.3.1 Physically
Grounded Intermediate Representation (PGIR) governance model. It is based on
the current source tree and tracked compact artifacts. It does not introduce a
new runtime hierarchy, solver, model, feature builder, or data acquisition.

## Audit Scope

Reviewed implementation families:

- `ScientificEntity`, `EntityRecord`, and entity specializations in `src/platform_core/scientific_entities.py`
- `ScientificQuantity` and `UncertaintySpec`
- `ScientificRelation` and selected `ScientificOperatorMetadata`
- scientific execution, trust, artifact, lineage, and report records
- Materials composition and crystal-structure adapters
- DataFrame/dict compatibility adapters

## Findings

| Implementation | Current Role | Persisted Form | PGIR Mapping | Status |
| --- | --- | --- | --- | --- |
| `ScientificEntity` | JSON-safe entity helper | entity record or artifact-backed metadata | PhysicalEntity, Observation, State, Result | `partial` |
| `EntityRecord` | persisted entity wrapper | canonical JSON plus checksum | Result, Provenance | `exact` |
| `MaterialCompositionEntity` | composition entity type | entity attributes | PhysicalEntity/composition representation | `partial` |
| `CrystalStructureEntity` | known-structure metadata | lattice/site attributes or local artifact | PhysicalEntity/StructuralState by context | `partial` |
| `MeasurementSeriesEntity` | measurement-series metadata | axis metadata plus artifact refs | Observation | `exact` |
| `StateEntity` | state metadata scaffold | state variables and conditions | State, Field, InitialCondition, BoundaryCondition | `partial` |
| `TrajectoryEntity` | ordered state sequence metadata | artifact-backed state refs | Observation/State sequence | `partial` |
| `GraphEntity` | graph artifact metadata | artifact-backed graph metadata | representation Result | `partial` |
| `ScientificQuantity` | value/unit record | JSON quantity | Quantity/Parameter/Result | `partial` |
| `UncertaintySpec` | structured uncertainty | JSON uncertainty | Uncertainty | `exact` |
| `ScientificRelation` | relation metadata | JSON-safe relation metadata | Relation | `exact` |
| `ScientificOperatorMetadata` | selected operator metadata | explicit registry record | Operator | `exact` |

## Boundaries

- Observation is not automatically State.
- Dimensional validity is not physical correctness.
- Graph artifact generation is not GNN or predictive evidence.
- v2.2 composition and known-structure decisions remain unchanged.
- PGIR names are canonical roles, not a mass rename of persisted schemas.
- Runtime helper classes are not persisted as live Python objects.

The machine-readable mapping lives in
[`data/platform/pgir_current_mapping_matrix_v1.json`](../data/platform/pgir_current_mapping_matrix_v1.json).
