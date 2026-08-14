# Deterministic Scientific Critic

## Purpose

The scientific critic is the next non-authoritative layer above the immutable epistemic graph and the policy-authorized local execution loop.

It answers a deliberately narrower question than a scientific conclusion:

> **What could still make the current interpretation wrong, and what evidence would discriminate those alternatives most directly?**

The critic does not invent domain mechanisms. It deterministically audits the structure already present in the checksum-bound epistemic graph.

## Inputs

`mda-research-program criticize-graph` first rebuilds the current mission-level research program and then evaluates the supplied graph against that exact program state and artifact root.

The critic binds:

- exact graph path, SHA-256, and byte count;
- a canonical SHA-256 of the rebuilt program state;
- mission and runtime-context bindings when present;
- selected target hypothesis/claim/conclusion nodes.

The mission must explicitly permit `reasoning_proposals: schema_validated`.

## Findings

The first policy version can detect:

- domain-verified falsification already present;
- conflicting verified support and contradiction/falsification;
- absence of represented domain-verified counterevidence;
- concentration of positive support in one direct provenance identity;
- empirical/mixed-scope claims supported only by simulations;
- proposal/diagnostic directional relations that are not domain verified;
- completed `tests` results that still lack a directional scientific interpretation;
- targets that have no recorded discriminating test.

These are methodological graph findings, not new scientific evidence.

## Alternative explanations

Alternatives are intentionally generic and methodological, for example:

- shared provenance rather than independent replication;
- measurement/preprocessing/selection artifacts;
- protocol-, sample-, condition-, or scope-dependent heterogeneity.

Every alternative is marked:

- `alternative_type: methodological_not_domain_mechanism`;
- `proposal_status: proposed_not_evidence_upgraded`;
- `scientific_mechanism_claim: false`.

Domain-specific mechanisms still require a separate evidence-bound reasoning proposal and appropriate domain verification.

## Discriminating next actions

The critic may propose bounded next work such as:

- prespecified sensitivity analysis;
- stratified reanalysis of conflicting evidence;
- provenance-disjoint replication;
- independent counterexample-oriented evidence search;
- plan-only empirical validation design;
- manual interpretation of completed test artifacts.

An information-gain priority is qualitative only. It is **not** a calibrated probability or expected-value estimate.

Every proposed action carries `automatic_execution_authorized: false`.

External evidence search requires explicit authorization. Physical validation remains plan-only. The critic has no generic command, network, laboratory, or execution surface.

## Falsification-first behavior

A target already `falsified_within_verified_scope` receives a `stop_and_reframe_current_target` recommendation. The negative result is preserved rather than silently averaged away or rescued by seeking additional positive results.

Even this recommendation has `automatic_stop_authorized: false`; mission/domain control remains external to the critic.

## Scientific boundary

The critic never:

- creates or upgrades evidence;
- creates `supports`, `contradicts`, or `falsifies` edges;
- changes target epistemic status;
- assigns scientific confidence scores or probabilities;
- grants positive scientific closeout;
- executes a typed action;
- starts network acquisition;
- executes a physical experiment;
- claims material identity, phase identity, mechanism, causality, prediction, or engineering readiness.

A critic report is therefore a **research-planning proposal**, not a scientific result.

## CLI

```powershell
mda-research-program criticize-graph `
  --mission configs/research/autonomous_materials_research_mission.v1.json `
  --repository-root . `
  --context path/to/runtime_context.json `
  --graph path/to/epistemic_graph.json `
  --artifact-root . `
  --target hypothesis-id
```

`--target` may be repeated. When omitted, every assessed hypothesis/claim/conclusion is reviewed.

## Intended next integration

The safe next composition is:

```text
verified Research State
→ deterministic critic report
→ evidence-bound reasoning proposal
→ separately authorized discriminating analysis / evidence acquisition / experiment plan
→ immutable result ingestion
→ independent directional/domain verification
→ successor epistemic graph
→ critic again
```

This preserves the central invariant: **research can become more autonomous without making scientific authority self-granting.**
