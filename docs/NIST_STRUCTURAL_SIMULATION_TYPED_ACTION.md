# NIST AM-Bench structural simulation typed action

## Purpose

`nist_structural_design_simulation@1.0` is the first audited `simulation` action admitted to the common bounded research executor. It answers one narrow question: whether the predeclared nine-trace Stage 1 augmentation would make a two-factor interaction design structurally estimable.

It does **not** answer the process-response question and does not satisfy the physical-data requirement in issue #76.

## Frozen bounded run

Use `configs/research/nist_ambench_structural_research_objective.v1.json` to initialize a research run. The objective permits one action and two cost units. The bounded planner `nist-ambench-structural` selects only `nist_structural_design_simulation@1.0` from `configs/research/nist_ambench_structural_action_registry.v1.json`.

The selected action is bound to the tracked response-free design specification:

`configs/research/nist_ambench_stage1_structural_design_simulation.v1.json`

A request that substitutes a different simulation specification is rejected before typed execution.

## Execution boundary

The action is dispatched only by `research_loop.authorized_execution.execute_authorized_action`. No second generic executor is introduced. The common executor retains:

- exact request-byte snapshotting;
- current planner and authorization re-evaluation;
- execution-registry identity and SHA-256 binding;
- hardcoded action/version/cost dispatch;
- output-to-ledger transaction recovery;
- exactly one research action per invocation; and
- pinned-snapshot post-execution verification.

There is no shell, subprocess, `eval`, `exec`, dynamic callable registry, network authority, or physical-equipment-control path.

## Scientific boundary

The simulation may compute design-grid completeness, matrix rank, full-column-rank status, and residual degrees of freedom. It must not:

- consume or synthesize response values;
- treat proposed replicate counts as measured traces;
- estimate coefficients or effect sizes;
- fit predictive or causal response models;
- perform engineering optimization;
- authorize an engineering decision;
- execute a physical experiment; or
- promote scientific evidence.

The current predeclared augmentation changes the interaction design from rank 3 to rank 4 and produces 15 residual degrees of freedom for the interaction design after 19 total design rows. Those are **structural design facts only**. They do not establish an empirical interaction effect.

## Terminal state

After the one structural simulation, the bounded research run stops with `physical_evidence_required`. Further scientific progression requires authoritative measurements for the three missing process cells:

- 137.9 W / 800 mm/s: at least 3 real traces;
- 137.9 W / 1200 mm/s: at least 3 real traces;
- 179.2 W / 400 mm/s: at least 3 real traces.

No simulated, interpolated, or inferred response may be used to close that requirement.
