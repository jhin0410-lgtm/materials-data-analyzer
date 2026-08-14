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

## Verified relations use evaluator authority

The critic does not treat `assessment_level: domain_verified` as sufficient by itself. It consumes the usable verified edge IDs produced by `evaluate_epistemic_graph`.

This preserves the evaluator's source-usability boundary:

- planned or failed analysis/simulation/experiment nodes do not become verified evidence;
- unsupported evidence nodes do not affect verified target status;
- only usable verified relations drive critic support, contradiction, conflict, and falsification findings.

A standalone usable verified contradiction produces `VERIFIED_CONTRADICTION_PRESENT` and a `reassess_or_reframe_contradicted_target` recommendation. It cannot fall through to positive-closeout language.

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

## Empirical support authority is intentionally blocked under the current transition-v1 contract

An `analysis` node can be computational or empirically derived. Source-node type therefore cannot establish empirical support for an empirical/mixed target.

Before even considering verifier scope, the critic re-reads the exact checksum-bound `domain_verification_decision` and validates the complete v1.0 decision contract. Required fields include:

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

The critic also cross-checks current provenance:

- verifier artifact SHA-256 and graph edge binding;
- verifier source/result node, target node, and relation against the graph edge;
- verifier `transition_id` against source-node transition metadata;
- verifier `proposal_sha256` against graph transition lineage;
- verifier `base_graph_sha256` against lineage `parent_graph_sha256`;
- verifier artifact SHA-256 against lineage `verification_decision_sha256`;
- source result node against lineage `result_node_id`.

These checks are necessary, but under the current merged contract they are **not sufficient to grant empirical authority**.

### Why exact inference-edge identity is still unproven

Transition provenance v1.0 binds the proposal SHA but does not checksum-authenticate the exact `proposed_inference.inference_edge_id` as an independently validated lineage field.

Graph `metadata` is intentionally extensible. Consequently, a caller could manually insert an `inference_edge_id` into `metadata.transition_lineage`. The field's presence or apparent match to the current edge would not prove that it came from the checksum-bound transition proposal.

Therefore the critic does **not** accept any `empirical_direct` or `empirical_derived` verifier scope as empirical authority under the current transition-v1 contract, even when opaque graph metadata contains a matching `inference_edge_id`.

A future provenance change must bind exact inference-edge identity through an authenticated transition/proposal/verifier contract and validate that contract before the critic can consume it. Merely adding another opaque metadata key is insufficient.

### Why `empirical_derived` is also unproven

Current `input_evidence_bindings` prove only:

- `workstream_id`;
- `role`;
- checksum identity.

They do not provenance-classify the bound input as empirical measurement data versus simulation output, computational derivation, or another origin.

The critic therefore does not infer `empirical_derived` authority from a non-empty binding list, role name, workstream name, filename, or action label.

### Resulting behavior

For an empirical/mixed target with positive verified support, the critic emits `EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED` whenever the current provenance contract cannot independently establish empirical authority.

This finding does **not** downgrade the evaluator's existing verified relation. It records a stronger provenance obligation required before the critic may describe that support as empirical evidence.

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
- empirical-provenance review;
- manual interpretation of completed tests.

Every proposed action carries:

- `automatic_execution_authorized: false`;
- `availability_asserted: false`.

An `execution_mode` describes only the proposed control boundary. It does not prove that a suitable request, registry entry, dataset, instrument, or execution resource exists.

Sensitivity analysis, conflict reanalysis, and replication therefore remain plan-only unless a separate verified planning/action layer establishes the required data and capability. External evidence search requires explicit authorization. Physical validation remains plan-only.

## Public API boundary

The structural critic builder is internal. The public `materials_data_analyzer.research_loop.scientific_critic.build_scientific_critic_report` delegates through the same policy-hardened facade used by the package and installed CLI.

Direct module imports therefore cannot bypass:

- evaluator source-usability semantics;
- completed-test semantics;
- independence hardening;
- empirical provenance restrictions;
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
3. only then relax the critic's current fail-closed empirical-scope boundary with dedicated regression tests.

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
