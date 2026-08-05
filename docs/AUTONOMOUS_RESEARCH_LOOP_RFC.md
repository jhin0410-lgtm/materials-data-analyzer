# Autonomous Research Loop RFC

Status: `experimental-kernel`

## Objective

Add a bounded autonomous-research layer above the existing Materials Data
Analyzer and Materials Characterization Analyzer tools without allowing a language
model to invent metrics, rewrite evidence, bypass validation, or silently expand
scientific claims.

The long-term loop is:

```text
research objective
-> research state
-> hypotheses
-> candidate actions
-> action selection
-> deterministic tool execution
-> independent verification
-> evidence and hypothesis update
-> continue / stop / request evidence
```

This RFC does not claim that the current software is an autonomous scientist. The
first implementation supplies only the state and immutable-ledger kernel required
before planner or model-selection logic can be added safely.

## Why this layer is needed

The repository already provides substantial execution and verification capability:

- tabular EDA, process, SPC, reliability, candidate screening, and Battery workflows;
- battery-, group-, time-, and source-aware validation;
- provenance, source receipts, checksums, output safety, and scientific closeout;
- installed characterization-handoff consumption from the companion repository;
- real-data positive, diagnostic, inconclusive, and unsupported evidence cases.

The missing capability is research-action selection. A person still chooses which
analysis to run, interprets a negative result, decides whether to change the target,
features, model, data source, or experiment, and manually carries the result into
the next iteration.

The research loop must automate that selection and update cycle while preserving
the existing deterministic trust boundary.

## Non-goals of the first kernel

The initial kernel does not:

- call an LLM;
- generate hypotheses automatically;
- fit or select a model;
- search the web or download data;
- execute Battery, Materials, process, or characterization analyzers;
- calculate expected information gain;
- change an existing scientific evidence level;
- infer target semantics, units, sample identity, or comparability;
- resume a stopped run;
- establish decision-grade or engineering readiness.

Those capabilities require later, separately reviewed contracts.

## Current command

The installed command is:

```text
mda-research-loop
```

Initialize a research run:

```powershell
mda-research-loop init `
  --objective configs/research/nasa_exact_horizon_research_objective.example.json `
  --output outputs/nasa_research_loop
```

Register a hypothesis:

```powershell
mda-research-loop add-hypothesis `
  --run outputs/nasa_research_loop `
  --hypothesis-id H1 `
  --statement "Protocol heterogeneity dominates signal-feature value." `
  --rationale "Errors are concentrated by source cohort rather than uniformly distributed."
```

Register checksum-bound evidence:

```powershell
mda-research-loop add-evidence `
  --run outputs/nasa_research_loop `
  --evidence-id E1 `
  --evidence-type baseline_result `
  --source outputs/nasa_pcoe_signal_enriched_battery_intelligence/model_comparison.json `
  --summary "Persistence remains stronger than the fixed Ridge hypothesis."
```

Record one completed, failed, or rejected action:

```powershell
mda-research-loop record-action `
  --run outputs/nasa_research_loop `
  --action-id A1 `
  --action-type feature_family_ablation `
  --status completed `
  --summary "Signal-derived feature families did not improve battery-macro MAE." `
  --cost-units 2 `
  --artifact outputs/nasa_ablation/feature_family_ablation.csv
```

Verify the complete run:

```powershell
mda-research-loop verify --run outputs/nasa_research_loop
```

Stop the run:

```powershell
mda-research-loop stop `
  --run outputs/nasa_research_loop `
  --reason-code external_evidence_required `
  --summary "No protocol-compatible independent cohort is available."
```

## Research objective contract

The objective declares:

- a stable `research_id`;
- one explicit scientific question;
- primary and secondary metrics;
- scientific and operational constraints;
- maximum action count and cost units;
- stop-rule identifiers;
- optional descriptive metadata.

The parser rejects duplicate JSON keys, missing required fields, unknown fields,
invalid budgets, empty strings, and duplicate list values. A valid objective does
not establish that the question or metric is scientifically appropriate. It only
creates an explicit versioned contract for later review and execution.

## Immutable ledger

The source of truth is `research_ledger.jsonl`, not the mutable-looking state
snapshot.

Every event records:

- schema version;
- monotonically increasing sequence number;
- event type;
- UTC timestamp;
- previous event hash;
- event payload;
- SHA-256 hash of the complete event excluding its own hash.

Changing, deleting, inserting, or reordering a ledger event breaks verification.
The current event types are:

- `objective_registered`;
- `hypothesis_registered`;
- `evidence_registered`;
- `action_recorded`;
- `research_stopped`.

Evidence files and action artifacts are bound by path, byte count, and SHA-256.
The ledger does not copy or reinterpret those artifacts.

## Reconstructed state

`research_state.json` is rebuilt from the ledger after each valid event. It
contains:

- current active or stopped status;
- objective metrics, constraints, and stop rules;
- remaining action and cost budgets;
- registered hypotheses;
- registered evidence;
- recorded action outcomes;
- terminal stop decision when present;
- latest event hash and complete ledger SHA-256.

Verification fails when the snapshot differs from the ledger reconstruction.
A stopped run is terminal.

## Safety boundary

The first kernel uses the existing transactional output-directory contract for
initialization. It does not overwrite an existing run and it protects the source
objective from output overlap.

Subsequent events are appended by verifying the entire existing chain, rebuilding
the complete ledger text, replacing it atomically, and regenerating the state
snapshot. A process interruption may leave the ledger and snapshot temporarily
out of agreement; this is detected fail-closed on the next operation rather than
silently accepted.

This is an append-only application contract, not a cryptographic protection
against an administrator who deliberately rewrites all files and recomputes every
hash. Future signed releases or remote attestation are separate concerns.

## Scientific boundary

The ledger can prove that a recorded event and artifact binding have not changed
within the local run. It cannot prove that:

- a hypothesis is meaningful;
- an action is scientifically justified;
- a metric answers the engineering question;
- a file contains valid measurements;
- a model result generalizes;
- an evidence summary correctly interprets the source artifact;
- a next experiment has high information value.

Those claims require deterministic action adapters, domain-specific verifiers,
locked evaluation, and human-approved scientific contracts.

## Planned implementation stages

### Stage 1 — State kernel

Current scope:

- objective contract;
- immutable hash-chained ledger;
- hypothesis, evidence, action, and stop events;
- budget enforcement;
- installed CLI;
- verification and regression tests.

### Stage 2 — NASA deterministic action registry

Wrap existing, already validated behavior as bounded actions. Candidate actions
include:

- strongest-baseline reproduction;
- target-reference sensitivity;
- feature-family ablation;
- protocol stratification;
- source-cohort leave-one-out evaluation;
- hierarchical or state-space baseline evaluation;
- conformal calibration audit;
- selective prediction and abstention;
- exact external-data requirement generation;
- scientific stop and closeout.

Each adapter must define inputs, outputs, preconditions, cost, artifact markers,
and independent verification rules. Arbitrary generated Python is out of scope.

### Stage 3 — Planner and verifier

The planner may rank only registered actions. It must provide a structured reason,
the unresolved hypothesis it targets, expected outcome branches, estimated cost,
and known failure modes.

The verifier independently recomputes critical metrics and checks dataset roles,
leakage, artifact integrity, budget use, action duplication, and claim boundaries.
Only verified action results may enter the research state.

### Stage 4 — Retrospective closed-loop benchmark

Partition a real case into:

- seed evidence visible at the start;
- acquisition pool revealed only through costed actions;
- locked test evidence never exposed to the planner.

Compare agent-selected actions against random acquisition, the current fixed
pipeline, and a documented human-designed sequence. Evaluate prediction,
calibration, abstention, action count, data acquired, compute cost, invalid actions,
and unsupported claims.

### Stage 5 — Additional benchmark families

Use complementary cases so the system does not learn only to stop:

- NASA Battery: negative-result recovery and minimum external-data requirement;
- Materials Project hidden pool: positive active discovery and sample efficiency;
- NIST AM-Bench: confounding, identifiability, and bounded next-experiment design;
- characterization handoffs: conflicting methods and missing physical-comparability
  evidence.

### Stage 6 — Method incubator

Physics-guided residual models, Neural ODE, PINN, deep UQ, and domain adaptation
remain optional actions, not mandatory pipeline stages. Each method requires
explicit eligibility checks, a fixed simple baseline, ablation, independent
validation, physical-violation auditing, and a rejection path.

## Promotion criteria

The research-loop layer must not be promoted from experimental status merely
because it runs end to end. Promotion requires evidence that it:

- reduces manual action selection or command execution;
- does not fabricate metrics or artifacts;
- does not repeat known failed actions without new evidence;
- respects action and data budgets;
- preserves locked evaluation boundaries;
- improves research efficiency or reaches a correct stop decision;
- produces an exact, reviewable next-evidence requirement when progress is blocked;
- remains compatible with the stable installed analyzers.

## Current scientific decision

The state kernel is a software and provenance capability only. It creates no new
Battery, process, Materials, reliability, or characterization result. The closed
NASA Ridge predictive conclusion remains `Unsupported`; current characterization
readiness and external-validation decisions remain unchanged.
