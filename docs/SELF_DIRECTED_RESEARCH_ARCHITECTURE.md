# Self-Directed Research Architecture

## Purpose

The materials-data-analyzer research loop is moving from a provenance-aware blocker
resolver toward a bounded self-directed materials-research system.

The target loop is:

```text
externally bounded mission
→ reconstruct verified research state
→ derive research objective
→ maintain competing hypotheses
→ identify evidence gaps
→ generate analysis / evidence-search / simulation / experiment-design candidates
→ rank candidates by explicit information/discrimination/cost assumptions
→ pass one selected candidate through the existing authorization boundary
→ execute only an already audited typed action
→ verify and record the result
→ update the epistemic graph
→ criticize the updated graph
→ revise the next objective
→ repeat until a declared stop rule fires
```

This is intentionally not an unconstrained agent and not a second executor.

## What this PR adds

Two planning layers are introduced.

### `autonomous_inquiry.py`

Builds a bounded inquiry from the existing verified research program:

- mission-scoped research objectives;
- explicit evidence gaps;
- three generic methodological rivals per active objective:
  - evidence-sufficiency/readiness alternative;
  - artifact-or-bias rival;
  - null-or-scope-limited rival;
- optional domain hypotheses from an already validated reasoning proposal;
- optional alternatives/actions from the deterministic scientific critic;
- deterministic non-probabilistic ranking of candidate work;
- budget and minimum-utility stop rules;
- proposal-only objective revision.

The utility score is deliberately **not** a Bayesian posterior and not calibrated
expected information gain. It is a transparent ordering heuristic:

```text
information score
× hypothesis-discrimination score
× feasibility
× (1 - risk penalty)
÷ cost
```

The individual scores remain planning assumptions and are retained in the output.

### `self_directed_research.py`

Adds conservative evidence-gap action synthesis and finite-loop protection.

For each declared evidence requirement it may propose:

- authoritative external evidence search;
- bounded reanalysis/sensitivity design;
- solver-bounded simulation design;
- physical experiment design;
- manual discrimination design when no safe action class can be inferred.

No generated action is executed by this module. Physical experiment actions are always
`plan_only`. Unregistered simulation actions are always `plan_only`. Network evidence
search requires explicit authorization.

A repeated iteration with the same verified program binding and the same selected action
stops as:

```text
stagnation_no_new_verified_evidence
```

A finite `max_iterations` guard prevents unbounded autonomous looping.

## Trust boundary

The authority chain remains:

```text
self-directed planner
→ candidate action
→ existing action/request authorization
→ authenticated request compilation / independent verification where applicable
→ existing hardcoded typed executor
→ immutable result / ledger recording
→ domain verification
→ epistemic transition
```

The new planner cannot:

- create empirical evidence;
- mark synthetic/interpolated data as experimental evidence;
- access the network;
- operate laboratory equipment;
- execute arbitrary commands;
- add a safe executor by editing a JSON registry;
- upgrade a scientific claim;
- mutate the externally supplied mission;
- convert an information-ranking score into scientific confidence.

## Scientific evidence ladder

Public and private datasets should no longer be reduced to a binary “usable / unusable”
decision. Each source may support different evidence levels.

```text
L0  file/software integration
L1  raw representation and byte identity
L2  acquisition/provenance integrity
L3  detector/instrument/calibration validity
L4  method/algorithm validation
L5  material-domain validation
L6  independent external validation
L7  replicated multi-source scientific support
L8  engineering/decision readiness under an explicit domain contract
```

Evidence cannot silently skip a level. For example, calibrated electron diffraction on a
different material may strongly support L1-L4 SAED method behavior while remaining
insufficient for Co3O4 L5-L6 claims.

## Current real blockers as examples

### NIST AM-Bench process-design augmentation

The remaining Stage-1 process-design gap requires real independently traceable traces in
three missing power/scan-speed cells. The self-directed planner may rank source search and
physical experiment design, but it must never interpolate the missing cells and call the
values empirical traces.

### Independent Co3O4 TEM validation

The evidence gap requires an exact/bounded cobalt-oxide domain, raw/lossless detector
representation, source-assigned sample/acquisition identities, at least two independent
samples/acquisitions, development non-use, and later blinded annotation. Existing
model-development-coupled data may remain useful at lower evidence levels but cannot be
promoted into independent validation.

### Calibrated SAED validation

The gap requires raw/lossless patterns, stable identity/reuse terms, material and
acquisition metadata, accelerating voltage, traceable reciprocal calibration/camera
constant, center provenance, and at least two independent patterns/acquisitions. A lossy
publication image can validate software integration but cannot satisfy the scientific
validation contract.

## Simulation boundary

The planner now recognizes simulation as a first-class research action, but a simulation
result is scientific evidence only after a **solver-specific** contract exists and the
result is independently verified. A generic “run arbitrary solver/command” executor is
intentionally forbidden.

A future solver adapter must hardcode and review at least:

- solver identity/version;
- scientific domain and equations/model class;
- input schema, units, parameter bounds, and initial/boundary conditions;
- material-property provenance;
- deterministic/random-seed policy;
- output schema and checksums;
- numerical convergence/mesh/time-step checks where applicable;
- validation range and known failure modes;
- whether the output is mechanistic, surrogate, sensitivity, or diagnostic evidence.

Initial useful materials adapters should be added one at a time rather than through a
generic command runner. Candidate families include CALPHAD/phase equilibrium, diffusion,
thermal/FEM, phase-field, electrochemical models, DFT, and MD when their dependencies and
validation data are available.

## Domain hypothesis generation

The deterministic planner can autonomously create methodological rivals because they do
not assert a material mechanism. Domain-mechanism hypotheses remain subject to the
existing evidence-bound reasoning proposal contract.

That distinction is deliberate. An autonomous system should be able to propose creative
mechanisms, but the mechanism text must remain a hypothesis and must bind to known
evidence, falsification criteria, discriminating evidence, and mission scope before it
can influence action planning. No language-model or human-generated hypothesis may
self-promote to truth.

## Iterative operating procedure

1. Build the verified research program from mission + runtime context.
2. Evaluate the current epistemic graph.
3. Run the scientific critic.
4. Validate any domain reasoning proposal.
5. Build one self-directed plan.
6. If stopped, preserve the stop reason and revise scope only under mission authority.
7. If an action is selected, route it to the existing authorization chain.
8. Execute only if the downstream typed action is already audited and authorized.
9. Verify the action report and append it through the existing immutable transition path.
10. Rebuild program/graph/critic state from the new evidence.
11. Build the next self-directed iteration using the prior plan for stagnation detection.

The planner must not be called repeatedly against unchanged evidence merely to generate
activity.

## CLI

One bounded iteration can be built with:

```powershell
python -m materials_data_analyzer.self_directed_research_cli `
  --mission .\configs\research\mission.json `
  --repository-root . `
  --context .\runtime_context.json `
  --critic-report .\critic.json `
  --validated-reasoning-proposal .\reasoning.validated.json `
  --output .\outputs\research_iteration_001.json
```

For the next iteration, after new verified evidence has changed program state:

```powershell
python -m materials_data_analyzer.self_directed_research_cli `
  --mission .\configs\research\mission.json `
  --repository-root . `
  --context .\runtime_context.json `
  --previous-plan .\outputs\research_iteration_001.json `
  --output .\outputs\research_iteration_002.json
```

If the verified state and selected action have not changed, the second invocation stops
as stagnated rather than pretending that another research cycle occurred.

## Remaining work toward the full autonomous-scientist target

This PR raises the control plane but does not claim the final system is complete. The
next evidence-bearing milestones are:

1. connect verified epistemic-graph assessments to explicit hypothesis portfolio updates;
2. add solver-specific audited simulation adapters rather than a generic simulator;
3. add domain-specific objective/hypothesis generators under evidence-bound proposal
   contracts;
4. compute information value from validated uncertainty models where scientifically
   defensible, while retaining the current heuristic fallback;
5. add experiment-design optimizers that respect facility feasibility/safety constraints;
6. integrate characterization evidence-ladder metadata through the existing handoff
   contract;
7. run complete positive end-to-end validation cases in addition to fail-closed blocker
   cases;
8. keep physical equipment execution outside the system until a separately reviewed
   laboratory-control trust boundary exists.
