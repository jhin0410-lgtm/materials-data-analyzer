# Physics-Aware Roadmap

Status: `v2.2.6 scientific trust closeout release_ready`.

v2.1 adds bounded scientific execution for scalar/small-list metadata checks
and v2.1.5 adds feature-candidate eligibility and scientific trust boundaries.
v2.2.1 adds the first bounded Materials composition feature builders and a
matched predictive-value validation. The result is negative/limited:
`performance_degraded` versus the matched v1.3 group-aware baseline.

v2.2.2 adds the entity, quantity, unit-backend, relation, uncertainty, schema
evolution, and graph/trajectory readiness foundation needed before richer
physics-aware extensions. It does not add simulators, GNNs, new acquisition, or
new predictive claims.

v2.2.3 audits the existing 838-row Materials Project acquisition scope,
documents that it is Fe/Si-containing and multinary, adds structure entity
adapters and selected operator metadata, and preserves the v2.2.1
`performance_degraded` conclusion.

v2.2.4 executes bounded current Materials Project structure enrichment for the
same 838 material IDs, audits target snapshot alignment, converts 838 valid
structures to JSON-safe entities, builds Tier-1 descriptor candidates, and
generates 838 deterministic periodic graph artifacts. It still does not train a
structure-aware model or alter the v2.2.1 conclusion.

v2.2.5 runs a fixed known-structure post-relaxation comparison on the
snapshot-aligned 838-row cohort. The result is
`structure_predictive_value_limited`: one primary group split showed limited
structure-descriptor improvement, no representative model was selected, and no
GNN, SHAP, DFT replacement, or hybrid physics-ML claim is made.

v2.2.6 closes the cycle with machine-readable capability, evidence, claim,
prediction-context, uncertainty, and release-readiness summaries. It preserves
the negative and limited conclusions instead of rerunning models or promoting
them into representative-model claims.

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
- Materials Project acquisition-scope audit, structure entity adapter, and
  selected scientific operator registry
- bounded Materials Project structure enrichment, snapshot-alignment audit,
  structure descriptor candidates, and periodic graph artifact pilot
- bounded known-structure post-relaxation comparison with prediction-interval
  diagnostics and explicit claim boundary
- v2.2 scientific evidence closeout with `release_ready` status, no
  representative model, and graph artifacts kept as representation-only

## Future Sequence

1. v2.1.4: execute bounded scientific checks and persist findings locally.
2. v2.1.5: classify constraint roles, feature eligibility, and claim
   boundaries without generating features.
3. v2.2.1: build selected Materials composition features and validate their
   predictive value against matched v1.3 baselines without arbitrary equations.
4. v2.2.2: add entity, quantity, uncertainty, schema-evolution, and graph /
   trajectory metadata foundations without simulators or new model claims.
5. v2.2.3: audit Materials Project acquisition scope and add structure
   adapter/operator metadata without full structure acquisition or model
   retraining.
6. v2.2.4: enrich the existing 838 material IDs with current structures,
   build JSON-safe entities, audit snapshot alignment, and pilot deterministic
   descriptors and graph artifacts without training.
7. v2.2.5: run the fixed known-structure comparison and preserve the limited
   result without selecting a representative model.
8. v2.2.6: close capability, claim, prediction-context, uncertainty, and
   release-readiness evidence without adding features or models.
9. Later v2.x: use only stronger evidence, cleaner external validation, or
   clearer task separation before adding graph models or richer structure-aware
   learning.

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

## v2.3.1 PGIR Governance

v2.3.1 introduces PGIR as architecture and representation governance. It
defines canonical concepts, maturity levels, current implementation mapping,
schema ownership, and capability stages. It does not add descriptors, rerun
Materials models, train graph models, execute solvers, or change the v2.2
`performance_degraded` and `structure_predictive_value_limited` decisions.

## v2.3.2 PGIR Conformance And Battery Pilot

v2.3.2 adds explicit PGIR conformance gates and applies them to existing
processed battery cycle summaries. This creates representation evidence for
Observation, bounded operational State, and Trajectory metadata, plus a
mechanism-readiness audit. It still does not run mechanisms, train predictors,
fit degradation laws, or make physics-aware battery performance claims.

## v2.3.3 Battery Mechanism Audit

v2.3.3 completes a data-sufficiency and identifiability audit for Battery
mechanism candidates. Arrhenius and diffusion remain blocked by evidence gaps;
the selected next step is a descriptive capacity-trajectory consistency
Evaluator only. Any physics-aware battery model, parameter fit, or solver
remains future work.
