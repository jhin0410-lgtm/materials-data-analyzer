# Physics-Aware Roadmap

Status: `v2.2.2 foundation implemented`.

v2.1 adds bounded scientific execution for scalar/small-list metadata checks
and v2.1.5 adds feature-candidate eligibility and scientific trust boundaries.
v2.2.1 adds the first bounded Materials composition feature builders and a
matched predictive-value validation. The result is negative/limited:
`performance_degraded` versus the matched v1.3 group-aware baseline.

v2.2.2 adds the entity, quantity, unit-backend, relation, uncertainty, schema
evolution, and graph/trajectory readiness foundation needed before richer
physics-aware extensions. It does not add simulators, GNNs, new acquisition, or
new predictive claims.

## Current Foundation

- unit and dimension registry
- explicit scientific constraint registry
- code-registered safe evaluators
- domain knowledge packs
- applicability checks for small JSON metadata
- scientific evidence-graph helper
- bounded scientific execution and local finding persistence
- scientific trust-boundary evaluation
- metadata-only scientific feature-candidate registry
- registered scientific claim IDs
- CLI list/inspect/validate/execute/export commands
- bounded Materials composition feature builders with property-source metadata
- matched Materials predictive-value validation with explicit claim boundary
- JSON-safe scientific entity, quantity, relation, uncertainty, and schema
  evolution contracts

## Future Sequence

1. v2.1.4: execute bounded scientific checks and persist findings locally.
2. v2.1.5: classify constraint roles, feature eligibility, and claim
   boundaries without generating features.
3. v2.2.1: build selected Materials composition features and validate their
   predictive value against matched v1.3 baselines without arbitrary equations.
4. v2.2.2: add entity, quantity, uncertainty, schema-evolution, and graph /
   trajectory metadata foundations without simulators or new model claims.
5. Later v2.x: add optional scientific descriptors only after contracts,
   provenance, applicability, and trust boundaries are in place.

## Explicitly Deferred

- symbolic math engines
- DFT/FEM/CFD execution
- physics-informed neural networks
- graph neural networks
- SHAP/explainability for weak models
- causal mechanism claims
- production control or maintenance automation

Physics-aware extensions should be added only when the dataset supplies the
semantic metadata, units, assumptions, and validation evidence needed to bound
the claim.
