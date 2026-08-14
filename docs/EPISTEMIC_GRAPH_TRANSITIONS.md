# Provenance-Bound Epistemic Graph Transitions

## Purpose

A self-directed research system must let completed analyses, simulations, data experiments, and externally executed physical experiments change the scientific state. It must not equate successful execution with scientific truth.

This transition layer makes that boundary explicit:

```text
completed typed/external result artifact
-> checksum-bound transition proposal
-> append result node to successor graph
-> proposed support / contradiction / falsification relation
-> optional separate domain-verification decision
-> only then may the inference relation become domain_verified
-> re-evaluate target epistemic status
```

The base graph is never rewritten. Every successful transition creates a new graph version plus a transition manifest that binds the exact parent graph, proposal, verifier decision, result artifacts, and successor graph bytes.

## Two-stage scientific authority

### 1. Result ingestion

A completed result must bind one or more exact artifacts. The transition can record that a result tests a hypothesis, claim, or conclusion and can add a proposed `supports`, `contradicts`, or `falsifies` edge.

Without a verification decision, that edge remains `proposal`. It does not change verified epistemic status.

This means:

> action success != scientific verification

A simulation that exits successfully, a statistical analysis that produces a table, or a physical measurement that is uploaded successfully is only a provenance-bearing result until the applicable scientific verifier assesses what it establishes.

### 2. Domain verification

A separate verification-decision JSON must bind:

- the exact transition ID;
- the exact proposal SHA-256;
- the exact parent graph SHA-256;
- result node ID;
- target node ID;
- proposed inference relation;
- verifier identity;
- inference scope;
- rationale and limitations.

Only a decision with `domain_verified: true` can promote the proposed inference edge to `domain_verified`. The verification-decision file itself becomes the checksum-bound verifier artifact on that edge.

Positive support remains only `provisionally_supported`; final scientific truth is never granted automatically.

## Evidence-class separation

The transition contract prevents computational evidence from being silently relabelled as empirical evidence.

| Result type | Allowed verified inference scope |
|---|---|
| simulation | `structural`, `computational` |
| analysis | `structural`, `computational`, or `empirical_derived` when bound empirical inputs exist |
| data experiment | `empirical_derived` with bound input evidence |
| external physical experiment | `empirical_direct` |

The target node must declare `metadata.claim_scope` as one of:

- `structural`
- `computational`
- `empirical`
- `mixed`

A verified inference must be compatible with that target scope. A structural design simulation therefore cannot directly verify an empirical materials-response claim.

## Physical experiments

This layer does not operate laboratory equipment.

A physical experiment result may enter the graph only as an `external_result_ingest` result whose origin is `external_physical_experiment`. The transition records and verifies the returned evidence; it does not claim that the software executed the experiment.

A future laboratory-control capability would require its own authorization, safety, equipment, calibration, and execution contracts before producing a result eligible for this intake path.

## Immutable lineage

Each successor graph appends a transition-lineage entry containing:

- transition ID;
- parent graph ID;
- parent graph SHA-256;
- transition-proposal SHA-256;
- optional verification-decision SHA-256;
- result node ID.

The emitted transition manifest additionally records before/after target assessments and the successor graph SHA-256.

The output directory must not already exist. Validation, checksum verification, scope compatibility, and graph evaluation all complete before any output file is written.

## CLI

The existing research-program entry point exposes the transition without adding a separate authority path:

```powershell
mda-research-program apply-graph-transition `
  --mission configs/research/autonomous_materials_research_mission.v1.json `
  --repository-root . `
  --base-graph path/to/current_epistemic_graph.json `
  --transition-proposal path/to/transition_proposal.json `
  --verification-decision path/to/domain_verification.json `
  --artifact-root path/to/result/artifacts `
  --output outputs/epistemic_transition_001
```

Omit `--verification-decision` to record a result and proposed inference without changing verified target status.

## Relationship to repeated research

The bounded multi-cycle runner determines whether a predeclared typed action may execute and replans after the action. The epistemic graph records what verified results establish. This transition is the bridge between them:

```text
planner / research cycle
-> authorized typed action
-> result artifact
-> epistemic transition proposal
-> domain verifier
-> successor graph
-> graph-gated replanning
```

The transition does not generate a new execution request, access the network, or grant itself authorization. Those remain separate trust boundaries.

## Scientific boundary

This feature establishes provenance-aware scientific-state evolution. It does not establish that any particular materials mechanism, phase assignment, model prediction, characterization interpretation, or engineering decision is correct.

The domain verifier must remain specific to the scientific question. Structural rank, software success, checksum integrity, simulation agreement, and repeated computational results cannot substitute for independent empirical evidence when the target claim is empirical.
