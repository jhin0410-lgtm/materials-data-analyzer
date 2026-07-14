# Physics-Aware Roadmap

Status: `planned`.

v2.1.4 adds bounded scientific execution for scalar/small-list metadata checks.
It is the first step toward physics-aware governance, not a physics-aware
modeling release.

## Current Foundation

- unit and dimension registry
- explicit scientific constraint registry
- code-registered safe evaluators
- domain knowledge packs
- applicability checks for small JSON metadata
- scientific evidence-graph helper
- bounded scientific execution and local finding persistence
- registered scientific claim IDs
- CLI list/inspect/validate/execute/export commands

## Future Sequence

1. v2.1.4: execute bounded scientific checks and persist findings locally.
2. v2.1.5: close out v2.1 registry/science execution release readiness.
3. v2.x: allow approved constraints to annotate feature builders and validation
   reports without executing arbitrary equations.
4. Later v2.x: add optional scientific descriptors only after contracts,
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
