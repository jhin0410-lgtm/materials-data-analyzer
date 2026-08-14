# Autonomous Materials Research Program

## Purpose

The project is not limited to recommending the next experiment after a user supplies a fixed research question. The target system is a provenance-aware autonomous materials research program that can repeatedly:

1. interpret a bounded research mission;
2. inspect verified scientific state across multiple workstreams;
3. generate the next research goals from observed blockers, contradictions, and evidence gaps;
4. formulate or accept falsifiable competing hypotheses through an evidence-bound reasoning contract;
5. choose among reanalysis, external evidence search, computational experiments, sensitivity analysis, simulation, replication, or physical experiment design;
6. execute only actions that pass the existing typed authorization boundary;
7. re-evaluate the resulting evidence and spawn later-stage questions;
8. stop when a bounded conclusion, falsification, unresolved external requirement, or no-positive-value condition is reached.

The scientific target is therefore a closed-loop research system, not an analyzer collection and not an automatic material-identification tool.

## Current architecture

```text
Research mission
      |
      v
Mission-level research program
      |
      +---- NIST AM-Bench planning state
      +---- NASA battery research-loop state
      +---- characterization-consumer state
      +---- external-source search state
      |
      v
Self-generated goal frontier
      |
      v
Evidence-bound reasoning proposal
  hypotheses + falsifiers + discriminating evidence
      |
      v
Typed action / evidence requirement / manual review
      |
      v
Existing authorization and execution boundary
      |
      v
New verified state -> replan
```

`materials-characterization-analyzer` remains the instrument-specific evidence producer. `materials-data-analyzer` remains the downstream research and decision layer. Neither repository may silently turn a descriptive feature, successful checksum, passing software test, or model output into scientific truth.

## Mission contract

The versioned mission at
`configs/research/autonomous_materials_research_mission.v1.json` declares:

- mission-level success criteria;
- global scientific constraints;
- stop rules;
- autonomy boundaries;
- enabled domain workstreams and their policy priority.

The mission is intentionally broader than one fixed question. Individual goals are derived from the latest verified blocker and evidence-gap state of each workstream.

Policy priority is **not** expected information gain. Until a defensible information-gain model exists for a domain, the program records information gain as `not_quantified` rather than inventing a pseudo-scientific number.

## Autonomy tiers

### Tier 1 — deterministic goal autonomy

Implemented in `research_program.py`.

The program may autonomously create a bounded goal such as:

- resolve an experimental-design identifiability gap;
- restore a missing provenance-bound runtime context;
- acquire evidence required to reopen a stopped scope;
- delegate a selected typed diagnostic or analysis action;
- route unresolved semantics to manual review.

These goals come only from verified planning state. The program does not create measurements or claim that an evidence gap has been closed.

### Tier 2 — scientific reasoning proposals

A domain reasoning provider may propose:

- scientific hypotheses;
- explicit falsification criteria;
- discriminating evidence;
- second- or later-stage analyses;
- computational experiments;
- sensitivity studies;
- simulations;
- replication;
- physical experiment designs.

The proposal is accepted only when it binds the exact evidence already present in the verified program state. A validated proposal remains `validated_for_planning_only`; it does not upgrade evidence and does not authorize execution.

This interface allows a future LLM, symbolic reasoner, physics model, or human domain expert to generate scientific ideas without bypassing provenance or action authorization.

### Tier 3 — bounded computational execution

Existing research-loop execution already supports explicit typed actions with preconditions, prohibited effects, expected outputs, verification, budget accounting, and ledger binding.

The next implementation stage is to classify which local deterministic action categories can safely participate in multi-cycle autonomous execution. That stage must preserve:

- predeclared action registries;
- exact request binding;
- per-action cost budget;
- negative results;
- independent verification;
- one-way claim boundaries;
- a hard maximum cycle count.

Network acquisition and arbitrary command generation must not be smuggled into this tier.

### Tier 4 — external evidence acquisition

Searching for papers, public datasets, repositories, or reference structures is scientifically useful but changes the evidence universe and requires explicit source and licensing checks. Network access therefore remains a separately authorized capability.

A credible evidence-acquisition cycle is:

```text
verified evidence gap
-> minimum external-evidence requirement
-> candidate search
-> source/version/license audit
-> checksum-bound acquisition
-> independence and semantic audit
-> accept or reject
-> replan
```

The goal is not to maximize downloads. Each acquired source must address a named uncertainty or falsification requirement.

### Tier 5 — physical experiments

The program may design a physical experiment, including variables, controls, sample count, acquisition conditions, and the evidence that would discriminate hypotheses. It does not claim that the experiment occurred.

Actual XRD, SEM, TEM, SAED, Raman, heat treatment, additive-manufacturing builds, or other laboratory operations remain external until a separately authorized laboratory automation interface exists. Returned measurements must enter through provenance-preserving intake before they can affect scientific state.

## First benchmark workstreams

### NIST AM-Bench

Purpose: autonomous experimental-design reasoning.

The current case is valuable because software execution is already supported while the present three process conditions do not support predictive, causal, or power-speed interaction claims. The program should therefore generate a goal around the design blocker and route toward the minimum staged experiment rather than fitting an unjustified model.

### NASA battery

Purpose: repeated longitudinal analysis and hypothesis discrimination.

The existing immutable research loop, audit action, target/reference sensitivity, protocol stratification, external-data requirement, and planned model candidates form a realistic multi-stage computational research benchmark. NASA requires an existing research-run directory and action registry at runtime; the mission-level program fails closed to `runtime_context_required` when they are absent.

### Characterization consumer / TM-Fe-Si

Purpose: cross-repository evidence integration.

This workstream checks whether checksum-bound characterization features can be consumed defensibly without converting descriptive evidence into phase, causal, mechanistic, or engineering claims.

### Materials Project external-source search

Purpose: evidence-gap and reopen reasoning.

This workstream exercises the case in which a current scope is scientifically closed but materially new independent evidence could justify a new versioned objective.

## CLI

Build the current mission-level agenda:

```powershell
mda-research-program show `
  --mission configs/research/autonomous_materials_research_mission.v1.json `
  --repository-root .
```

NASA will appear as `runtime_context_required` unless a runtime-context file is supplied.

A context file has the following shape:

```json
{
  "schema_version": "1.0",
  "workstreams": {
    "nasa-battery": {
      "research_run": "outputs/nasa_autonomous_loop_...",
      "action_registry_path": "configs/research/nasa_research_action_registry.v1.json"
    }
  }
}
```

Then run:

```powershell
mda-research-program show `
  --mission configs/research/autonomous_materials_research_mission.v1.json `
  --repository-root . `
  --context path/to/runtime_context.json
```

Validate an evidence-bound scientific reasoning proposal:

```powershell
mda-research-program validate-proposal `
  --mission configs/research/autonomous_materials_research_mission.v1.json `
  --repository-root . `
  --context path/to/runtime_context.json `
  --proposal path/to/reasoning_proposal.json
```

Validation does not execute the proposal.

## Scientific hypothesis contract

A scientific hypothesis is not generated from a checksum alone. A reasoning proposal must state:

- the hypothesis;
- at least one falsification criterion;
- the evidence that would discriminate it from alternatives;
- the exact verified evidence bindings used to motivate it;
- the proposed next actions;
- known limitations;
- an explicit stop condition.

A new hypothesis begins as `proposed_not_evidence_upgraded`.

## Action classes

The mission-level reasoning contract currently recognizes:

- `existing_data_reanalysis`;
- `external_evidence_search`;
- `computational_experiment`;
- `sensitivity_analysis`;
- `simulation`;
- `physical_experiment_design`;
- `replication`;
- `manual_review`.

`external_evidence_search` must use `explicit_authorization_required`.
`physical_experiment_design` is `plan_only`.
A `typed_local_action` is permitted only for bounded computational/data action classes and still does not become executable merely because the proposal validated.

## What this PR does not claim

This control plane does **not** yet provide:

- free-form autonomous internet search;
- autonomous paper interpretation;
- automatic CALPHAD, DFT, FEM, phase-field, or molecular-dynamics execution;
- arbitrary Python or shell generation;
- self-authorized model retraining;
- physical laboratory execution;
- automatic causal or mechanistic conclusions;
- quantitative expected information gain.

Those capabilities must be added as typed tools with domain-specific validation and failure boundaries, not as an unrestricted agent loop.

## Next implementation sequence

1. Merge and verify the mission-level program control plane.
2. Add a bounded multi-cycle executor for explicitly classified local computational actions.
3. Add a simulation-tool registry with typed input/output and independent verification.
4. Add an external-evidence search/acquisition registry with source, version, license, checksum, independence, and task-match gates.
5. Add an epistemic claim graph connecting hypotheses, supporting evidence, contradicting evidence, analyses, simulations, and conclusions.
6. Add stopping logic based on falsification, unresolved external evidence, budget, repeated non-improvement, and no-positive-value actions.
7. Exercise the same engine on NIST, NASA, and characterization benchmarks before expanding analyzer count or UI.

The target milestone is not “the agent ran many steps.” The target milestone is a reproducible chain in which each new research question, hypothesis, analysis, simulation, experiment design, and conclusion can be traced to the exact evidence and policy state that justified it.
