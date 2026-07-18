# Materials Structure PGIR Reuse

Status: `second_domain_pgir_reuse_demonstrated_with_restrictions`

v2.4.1 applies the released v2.3 PGIR declaration, maturity, conformance, and
transition framework to the existing v2.2 Materials structure workflow. No
Materials acquisition, descriptor/graph regeneration, or model execution is
performed.

## Existing Evidence Reused

- 838 bounded existing material IDs requested and returned;
- 838 JSON-safe `CrystalStructureEntity` records;
- 838 structure-integrity-valid records;
- 838 reduced-composition matches;
- 12 Tier-1 descriptor definitions and 838 descriptor rows;
- 838 deterministic periodic graph artifacts;
- zero audited target drifts;
- `performance_degraded` composition-only decision;
- `structure_predictive_value_limited` known-structure decision; and
- no representative model.

## PGIR Mapping

| Materials implementation | PGIR role | Context |
| --- | --- | --- |
| MP source document | source record / provenance | Computed record, not measurement |
| Composition | `MaterialCompositionEntity` | Composition representation |
| Relaxed structure | `CrystalStructureEntity` / physical entity | `known_structure_post_relaxation` |
| Integrity check | Evaluator result | Bounded structural validity only |
| Composition match | Evaluator result | Representation consistency only |
| Descriptors | Transformer-derived result | Candidate representation |
| Periodic graph | `GraphEntity` result | Representation-only |
| Predictive comparison | Existing evidence artifact | Read-only limited result |

The relaxed structure is not available in the composition-only pre-structure
screening context. It is not described as an experimental structure.

## Actual Conformance

The local audit read 838 existing entity envelopes and produced 838 PGIR
declarations. All 838 passed the existing declaration gate and were promoted
from `schema_valid` to `physically_admissible` using explicit schema,
semantics, units, dimensional, finite-range, and registered integrity evidence.
This does not promote the dataset to independently or production validated.

Five registered Transformer/Evaluator transitions passed:

- MP structure document to `CrystalStructureEntity`;
- structure integrity evaluation;
- composition/structure consistency evaluation;
- structure to descriptor summary; and
- structure to periodic radius graph.

Seven existing Materials operators were found in the selected operator
registry. No Propagator or physical mechanism operator was reused.

## Maturity Boundary

Source records are semantically mapped; crystal entities are structurally and
dimensionally admissible; integrity results are bounded scientifically
evaluated results; descriptors and graphs are transformed/generated
representations; existing predictive evidence remains limited. Independent
and production validation are both false.

## Outputs

Row-level declarations, findings, maturity rows, and transition rows remain
local-only. Tracked outputs contain aggregate counts and decisions only. They
contain no material IDs, structure bodies, target rows, or graph bodies.
