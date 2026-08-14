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

The policy-hardened critic can detect:

- domain-verified falsification already present;
- conflicting verified support and contradiction/falsification;
- absence of represented domain-verified counterevidence;
- **positive-support independence not established by the current graph contract**;
- empirical/mixed-scope claims supported only by simulations;
- proposal/diagnostic directional relations that are not domain verified;
- completed `tests` results that still lack a directional scientific interpretation;
- targets that have no recorded discriminating test.

These are methodological graph findings, not new scientific evidence.

## Independence is not inferred from artifact identity

Distinct node IDs, filenames, checksums, instruments, or derivative analyses do not by themselves prove statistical or experimental independence. Two apparently separate results may still share a parent sample, source dataset, acquisition session, preprocessing lineage, or another dependence.

Therefore any verified positive support receives `SUPPORT_INDEPENDENCE_NOT_ESTABLISHED` unless a future first-class provenance/independence contract can prove the required disjointness dimensions. The critic does **not** call multiple artifacts independent replication merely because their direct identifiers differ.

A proposed replication action:

- has `automatic_execution_authorized: false`;
- has `availability_asserted: false`;
- uses `explicit_authorization_required` until suitable provenance-disjoint evidence or an external experiment is actually available.

## Program evidence gaps remain workstream-scoped

The rebuilt mission program may already contain exact `evidence_requirements` for NIST-, NASA-, characterization-, or other workstreams. The critic preserves those requirements verbatim in `program_evidence_gaps` when their goals remain open.

However, the critic does **not** silently attach a workstream requirement to a particular hypothesis/claim merely because the topics appear related. Every copied requirement has:

- its original `goal_id`;
- its original `workstream_id`;
- `target_attribution: not_inferred`;
- `automatic_acquisition_authorized: false`.

A future target↔workstream mapping must itself be provenance-bound before target-specific evidence-gap attribution is permitted. This prevents cross-workstream evidence leakage and avoids inventing domain requirements.

## Alternative explanations

Alternatives are intentionally generic and methodological, for example:

- shared or dependent provenance rather than independent replication;
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
- establishing an explicit provenance-disjointness contract and replication plan;
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
- infers independence from artifact multiplicity;
- attributes workstream evidence requirements to targets without an explicit mapping;
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
