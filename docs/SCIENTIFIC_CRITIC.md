# Deterministic Scientific Critic

## Purpose

The Scientific Critic is a deterministic, non-authoritative layer above the epistemic graph and the policy-authorized local research loop.

It asks:

> **What could still make the current interpretation wrong, and what evidence would discriminate those alternatives most directly?**

It does not create scientific evidence, invent domain mechanisms, grant positive closeout, or execute proposed work.

## Inputs and bindings

`mda-research-program criticize-graph` rebuilds the current mission-level research program and evaluates the supplied graph against that exact program state and artifact root.

A critic report binds:

- exact graph path, SHA-256, and byte count;
- canonical SHA-256 of the rebuilt program state;
- mission/runtime-context bindings when present;
- selected hypothesis/claim/conclusion targets.

The mission must explicitly permit `reasoning_proposals: schema_validated`.

## Evaluator status and critic authority are separate

The structural critic does not treat `assessment_level: domain_verified` as sufficient by itself. It consumes the usable verified edge IDs produced by `evaluate_epistemic_graph`.

This preserves the evaluator's source-usability boundary:

- planned or failed analysis/simulation/experiment nodes do not become verified evidence;
- unsupported evidence nodes do not affect verified target status;
- only evaluator-usable verified relations enter structural support, contradiction, conflict, and falsification analysis.

The hardened facade adds a second boundary: **an evaluator status is preserved, but the critic does not automatically gain authority to act on a directional relation whose exact inference-edge provenance is not authenticated.**

For example, a target may remain `contradicted_within_verified_scope` or `falsified_within_verified_scope` in its embedded evaluator assessment while the hardened critic withholds a stop/reframe recommendation until the exact directional verifier provenance is stronger.

## Recorded tests require completed execution

A `tests` edge counts as a recorded discriminating test only when its executable source has `execution_status: completed`.

Planned or failed test sources therefore:

- do not trigger `COMPLETED_TESTS_WITHOUT_DIRECTIONAL_INTERPRETATION`;
- do not suppress `NO_RECORDED_DISCRIMINATING_TEST`;
- do not satisfy a testing obligation merely because a test edge was created.

Execution success and scientific interpretation remain separate states.

## Independence is not inferred from artifact multiplicity

Distinct node IDs, filenames, checksums, instruments, or derivative analyses do not prove statistical or experimental independence. They may still share a parent sample, source dataset, acquisition session, preprocessing lineage, or another dependence.

The hardened critic therefore emits `SUPPORT_INDEPENDENCE_NOT_ESTABLISHED` for verified positive support unless a future first-class provenance/independence contract proves the required disjointness dimensions.

It never calls multiple artifacts independent replication merely because their direct identifiers differ.

The corresponding replication proposal remains `plan_only` with `availability_asserted: false` until a separate verified planning/action layer establishes suitable disjoint evidence and execution capability.

## Current verifier provenance checks

When an edge carries a recognized `domain_verification_decision`, the critic re-reads the exact checksum-bound bytes and validates the complete v1.0 decision contract. Required fields include:

- `schema_version`;
- `decision_id`;
- `transition_id`;
- `proposal_sha256`;
- `base_graph_sha256`;
- `result_node_id`;
- `target_node_id`;
- `relation`;
- `inference_scope`;
- `verifier_id`;
- `rationale`;
- `limitations`;
- `domain_verified`.

Missing or unknown fields, duplicate JSON keys, invalid enums, malformed required values, or checksum drift fail closed.

The critic also cross-checks everything the current transition-v1 lineage can authenticate:

- verifier artifact SHA-256 and graph edge binding;
- verifier source/result node, target node, and relation against the graph edge;
- verifier `transition_id` against source-node transition metadata;
- verifier `proposal_sha256` against graph transition lineage;
- verifier `base_graph_sha256` against lineage `parent_graph_sha256`;
- verifier artifact SHA-256 against lineage `verification_decision_sha256`;
- source result node against lineage `result_node_id`.

These checks reject malformed or inconsistent provenance. They still do not prove the exact inference-edge identity under the currently merged transition-v1 contract.

## Exact inference-edge identity is not authenticated by transition-v1

Transition provenance v1.0 binds the proposal SHA but does not separately checksum-authenticate the exact `proposed_inference.inference_edge_id` as a validated lineage field.

Graph `metadata` is intentionally extensible. A caller can therefore insert an `inference_edge_id` into `metadata.transition_lineage`; the field's presence or apparent match to the current edge does not prove that it came from the checksum-bound transition proposal.

The critic consequently treats opaque metadata as non-authoritative. Merely adding a matching `inference_edge_id` key to graph metadata cannot upgrade scientific authority.

A future provenance contract must authenticate exact inference-edge identity through the transition/proposal/verifier chain and validate that contract independently before the critic may consume it as authority.

## Negative directional relations are provenance-gated

The exact-edge problem applies to negative evidence as well as positive empirical support.

For evaluator-verified `contradicts` or `falsifies` relations, the hardened critic validates all provenance that the current contract can prove. If a recognized current-format verifier is malformed or inconsistent, the report fails closed.

Even when the available verifier and lineage checks pass, transition-v1 still cannot authenticate the exact inference edge. Therefore the hardened critic does **not** let that negative relation directly drive critic-level stop/reframe authority.

Instead it:

- preserves the evaluator assessment status unchanged;
- removes structural-core authority findings such as `VERIFIED_CONTRADICTION_PRESENT`, `VERIFIED_FALSIFICATION_PRESENT`, or `VERIFIED_EVIDENCE_CONFLICT` from the hardened output when they depend on unauthenticated exact-edge provenance;
- emits `NEGATIVE_DIRECTIONAL_PROVENANCE_NOT_ESTABLISHED`;
- proposes a `plan_only` manual provenance review;
- uses `verify_directional_provenance_before_scientific_reframe` rather than stopping, narrowing, or reframing the target automatically;
- keeps `automatic_stop_authorized: false` and `positive_scientific_closeout_granted: false`.

This is deliberately conservative: the critic does not downgrade the evaluator's scientific state, but it also does not compound an unresolved provenance ambiguity into a stronger research-control decision.

## Empirical support authority is intentionally blocked under transition-v1

An `analysis` node can be computational or empirically derived. Source-node type therefore cannot establish empirical support for an empirical/mixed target.

For positive support of an empirical/mixed target, the hardened critic validates the current verifier bytes and lineage as described above but still emits `EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED`, because exact inference-edge identity is not authenticated.

### `empirical_derived` has an additional input-origin gap

Current `input_evidence_bindings` prove only:

- `workstream_id`;
- `role`;
- checksum identity.

They do not provenance-classify the bound input as empirical measurement data versus simulation output, computational derivation, or another origin.

The critic therefore does not infer `empirical_derived` authority from a non-empty binding list, role name, workstream name, filename, or action label.

### `empirical_direct` is also withheld under the current contract

Even a source compatible with an external physical experiment does not receive critic-level empirical authority until exact inference-edge identity is authenticated. A matching field injected into opaque graph metadata is not sufficient.

### Resulting behavior

`EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED` does **not** downgrade the evaluator's existing verified relation. It records a stronger provenance obligation required before the critic may describe that support as authenticated empirical evidence.

The corresponding action is plan-only: strengthen provenance contracts or, if no empirical support exists, plan independent empirical validation. The critic does not authorize or execute validation.

## Workstream evidence gaps remain workstream-scoped

Mission-program goals may contain exact `evidence_requirements`. The critic preserves open requirements in `program_evidence_gaps` with their original `goal_id` and `workstream_id`.

It does not silently attach a workstream requirement to a hypothesis/claim merely because the topics appear related. Each copied requirement carries:

- `target_attribution: not_inferred`;
- `automatic_acquisition_authorized: false`.

Target-specific attribution requires a separate provenance-bound target↔workstream mapping.

## Proposed alternatives and actions are non-authoritative

The critic may propose methodological alternatives such as:

- shared/dependent provenance;
- measurement, preprocessing, or selection artifacts;
- protocol/sample/condition/scope heterogeneity.

It may propose next work such as:

- sensitivity analysis;
- stratified conflict reanalysis;
- provenance-disjoint replication planning;
- counterexample-oriented external evidence search;
- directional/empirical provenance review;
- manual interpretation of completed tests.

Every proposed action carries:

- `automatic_execution_authorized: false`;
- `availability_asserted: false`.

An `execution_mode` describes only the proposed control boundary. It does not prove that a suitable request, registry entry, dataset, instrument, or execution resource exists.

Sensitivity analysis, conflict reanalysis, and replication remain plan-only unless a separate verified planning/action layer establishes the required data and capability. External evidence search requires explicit authorization. Physical validation remains plan-only.

## Public API boundary

The structural critic builder is internal. The public `materials_data_analyzer.research_loop.scientific_critic.build_scientific_critic_report` delegates through the same policy-hardened facade used by the package and installed CLI.

Direct module imports therefore cannot bypass:

- evaluator source-usability semantics;
- completed-test semantics;
- independence hardening;
- directional verifier/provenance restrictions;
- workstream evidence-gap scoping;
- action-availability conservatism.

## Scientific boundary

The critic never:

- creates or upgrades evidence;
- creates `supports`, `contradicts`, or `falsifies` relations;
- changes target epistemic status;
- assigns scientific confidence scores or probabilities;
- counts unusable sources as verified evidence;
- counts planned/failed executions as completed tests;
- infers independence from artifact multiplicity;
- infers empirical authority from source-node type;
- trusts malformed verifier decisions;
- trusts opaque graph metadata as scientific authority;
- lets unauthenticated exact-edge negative provenance drive stop/reframe authority;
- accepts empirical scope without an authenticated exact inference-edge contract;
- infers empirical-derived origin from unclassified input bindings;
- attributes workstream evidence requirements to targets without explicit provenance;
- treats action proposals as execution authorization or resource availability;
- grants positive scientific closeout;
- executes typed/network/physical actions;
- claims material identity, phase identity, mechanism, causality, prediction, or engineering readiness.

A critic report is therefore a **research-planning proposal, not a scientific result**.

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

## Required follow-up provenance work

The next safe provenance work is separate from the critic itself:

1. strengthen transition/verifier provenance so exact `proposed_inference.inference_edge_id` is checksum-authenticated and independently validated rather than copied into opaque metadata;
2. add first-class provenance-bound evidence-origin classification so `empirical_derived` can distinguish empirical measurement inputs from computational/simulation inputs;
3. only then relax the critic's current fail-closed directional/empirical authority boundary with dedicated regression tests.

The intended research loop remains:

```text
verified Research State
→ deterministic critic report
→ evidence-bound reasoning proposal
→ separately authorized discriminating work
→ immutable result ingestion
→ independent directional/domain verification
→ successor epistemic graph
→ critic again
```

The governing invariant is: **research may become more autonomous without making scientific authority self-granting.**
