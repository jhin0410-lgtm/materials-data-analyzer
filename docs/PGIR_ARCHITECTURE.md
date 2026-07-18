# PGIR Architecture

Status: `accepted_for_v2_3`

PGIR is the v2.3 governance layer for connecting the current metadata platform
to future physics-aware workflows. It defines canonical concepts, maturity
levels, schema ownership, and operator taxonomy. It does not add a solver,
GNN, PINN, feature descriptor, acquisition step, or new predictive claim.

## Principles

- Domain-neutral core, domain-explicit boundaries.
- Observation is not automatically State.
- Value is not Relation.
- Representation is not Mechanism.
- Artifact generation is not predictive evidence.
- Dimensional validity is not physical correctness.
- Physical consistency is applicability-dependent.
- Uncertainty kinds remain semantically separate.
- Runtime objects and persisted records remain separated.
- Every scientific claim requires explicit evidence and context.
- Incomplete scientific data may enter the platform with limited capabilities.
- No universal mechanism claim without cross-domain validation.

## Canonical Concepts

PGIR defines these canonical concepts: PhysicalEntity, Observation, State,
Field, Parameter, Control, InitialCondition, BoundaryCondition, Relation,
Operator, Model, Result, Uncertainty, Provenance, and Context.

The tracked concept registry is
[`data/platform/pgir_concept_registry_v1.json`](../data/platform/pgir_concept_registry_v1.json).

## Representation Maturity

PGIR uses maturity levels from `L0 raw_observed` through
`L8 production_validated`. Lower-level data can remain in the platform, but
allowed operations depend on explicit evidence and context. Successful parsing
or unit conversion does not automatically promote data to a physical state or
mechanism-ready representation.

## Operator Taxonomy

Primary roles:

- `Evaluator`: checks an existing representation against a relation or constraint.
- `Transformer`: converts one representation into another.
- `Propagator`: advances state using initial/boundary conditions and parameters.

In v2.3.1, `Propagator` was `concept_defined` only. v2.4.2 permits exactly one
bounded synthetic 1D diffusion contract with registered exact and FTCS
Propagators. This does not create a general PDE/ODE solver and does not permit
Arrhenius fitting, Battery mechanism inference, physics loss, GNN, or PINN.

## Architecture Flow

```text
Domain Adapters
-> PGIR Representation
-> Mechanism / Operator Registry
-> Inference or Scientific Execution
-> Evidence / Uncertainty / Claims
-> Registry / Reports / UI
```

The current release reaches the representation-governance layer. Future
mechanism execution requires separate readiness gates.

## Current Readiness

v2.3.1 readiness is `pgir_governance_ready` because:

- core concepts are defined,
- current implementation mappings are explicit,
- schema owners are unique,
- maturity levels and operator roles are explicit,
- future-only capabilities remain marked as future-only,
- v2.2 results are not promoted or changed.

## v2.3.2 Conformance Gates

v2.3.2 adds explicit conformance gates over the v2.3.1 registries:
representation declarations, maturity promotion checks, context compatibility,
registered transition checks, and capability eligibility checks. These gates
block unsupported promotion such as treating a terminal battery cycle
Observation as a complete electrochemical State or internal concentration
Field.

The first adapter pilot maps existing processed battery cycle rows to
Observation metadata, bounded operational State summaries, and per-cell
Trajectory metadata. It produces compact tracked summaries and local-only
row-level JSONL artifacts. It does not execute Arrhenius fitting, diffusion
solving, SOH/RUL prediction, or any battery degradation model.

## v2.3.3 Mechanism Identifiability Audit

v2.3.3 adds a Battery mechanism-candidate registry, evidence-gap registry, and
read-only identifiability audit. The audit separates structural, practical,
and contextual identifiability; records protocol and confounding limits; and
selects only a descriptive capacity-trajectory consistency Evaluator for
v2.3.4 consideration. It does not estimate mechanism parameters or execute a
dynamic model.

## v2.3.4 Bounded Evaluator Execution

The selected Battery capacity-trajectory Evaluator is now implemented and
executed as a deterministic descriptive operator. Its result artifact reaches
`scientifically_evaluated` only for the bounded evaluator/context pair. The
underlying trajectory does not gain mechanism compatibility, and blocked
Arrhenius/diffusion capabilities remain blocked.

## v2.4.1 Second-Domain Reuse

The same declaration, schema-ownership, maturity, conformance, transition, and
operator-registry framework is now applied to 838 existing Materials
`CrystalStructureEntity` records. Battery retains Observation/State/Trajectory
semantics, while Materials uses computed relaxed structures in the
`known_structure_post_relaxation` context. Physical-operator reuse is not
demonstrated, and no independent or production validation is promoted. See
[Cross-Domain PGIR Reuse Evidence](CROSS_DOMAIN_PGIR_REUSE_EVIDENCE.md).

## v2.4.2 Bounded Model Execution

The first executable PGIR Model Contract declares a synthetic scalar field,
dimensions, initial and zero Dirichlet boundary conditions, exact reference,
FTCS backend, validation criteria, and claim boundary. The result artifact only
reaches bounded `scientifically_evaluated` maturity. Physical-operator
execution is demonstrated for this benchmark; cross-domain physical-operator
reuse, independent validation, and production validation remain false. See
[PGIR Model Contract](PGIR_MODEL_CONTRACT.md) and
[Physical Propagator Validation](PHYSICAL_PROPAGATOR_VALIDATION.md).
