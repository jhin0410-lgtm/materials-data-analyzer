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
- standalone usable domain-verified contradiction;
- conflicting verified support and contradiction/falsification;
- absence of represented domain-verified counterevidence;
- **positive-support independence not established by the current graph contract**;
- empirical/mixed-scope claims supported only by simulations;
- **empirical/mixed-scope positive support whose empirical inference scope is not established by complete verifier and transition provenance**;
- proposal/diagnostic directional relations that are not domain verified;
- completed `tests` results that still lack a directional scientific interpretation;
- targets that have no completed recorded discriminating test or usable verified directional relation.

These are methodological graph findings, not new scientific evidence.

## Verified means usable in the evaluator, not merely labeled

The critic does not reconstruct verified scientific authority from `assessment_level: domain_verified` alone. It consumes the exact verified support/contradiction/falsification edge IDs produced by `evaluate_epistemic_graph`.

This preserves the evaluator's source-usability gate. In particular:

- planned or failed analysis/simulation/experiment nodes do not become verified evidence merely because an attached edge is labeled `domain_verified`;
- unsupported evidence nodes likewise cannot affect verified target status;
- only the evaluator-authorized usable verified relations drive critic findings such as support, conflict, contradiction, or falsification.

A standalone usable verified contradiction is emitted as `VERIFIED_CONTRADICTION_PRESENT` and receives `reassess_or_reframe_contradicted_target`. It cannot fall through to a positive closeout-style recommendation.

## Recorded tests require completed execution

A `tests` edge is counted as a recorded discriminating test only when its executable source has `execution_status: completed`.

A planned or failed analysis/simulation/experiment therefore:

- does not trigger `COMPLETED_TESTS_WITHOUT_DIRECTIONAL_INTERPRETATION`;
- does not suppress `NO_RECORDED_DISCRIMINATING_TEST`;
- cannot satisfy a scientific testing obligation merely because the edge was created before execution completed.

This preserves the distinction between a test plan, execution success, and scientific interpretation.

## Independence is not inferred from artifact identity

Distinct node IDs, filenames, checksums, instruments, or derivative analyses do not by themselves prove statistical or experimental independence. Two apparently separate results may still share a parent sample, source dataset, acquisition session, preprocessing lineage, or another dependence.

Therefore any verified positive support receives `SUPPORT_INDEPENDENCE_NOT_ESTABLISHED` unless a future first-class provenance/independence contract can prove the required disjointness dimensions. The critic does **not** call multiple artifacts independent replication merely because their direct identifiers differ.

A proposed replication action:

- has `automatic_execution_authorized: false`;
- has `availability_asserted: false`;
- requires separate evidence/capability establishment before execution can be considered.

## Empirical support requires complete provenance

An `analysis` node may represent a computational analysis or an empirically derived analysis. Therefore the critic does **not** treat “not a simulation” as proof that an empirical or mixed-scope target has empirical support.

Before consuming any `domain_verification_decision.inference_scope`, the policy overlay re-reads the exact checksum-bound verifier bytes and validates the complete v1.0 decision contract. Required fields include the decision/verifier identities, transition/proposal/base-graph bindings, result and target identities, relation, inference scope, rationale, limitations, and explicit `domain_verified: true`. Missing/unknown fields, duplicate JSON keys, invalid enums, empty required text, or checksum drift fail closed.

The verifier is then cross-checked against graph provenance:

- verifier artifact SHA-256 and the graph edge binding;
- verifier `result_node_id`, `target_node_id`, and relation and the graph edge;
- verifier `transition_id` and the source result node metadata;
- verifier `proposal_sha256` and the matching graph `transition_lineage` record;
- verifier `base_graph_sha256` and lineage `parent_graph_sha256`;
- verifier artifact SHA-256 and lineage `verification_decision_sha256`;
- source result node ID and lineage `result_node_id`.

### Exact inference-edge identity is currently a blocking provenance gap

The transition-lineage v1.0 contract currently records the proposal SHA but not the proposal's `proposed_inference.inference_edge_id`. That means a verifier for one edge could not be distinguished solely from another edge with the same source, target, and relation after only the graph/lineage artifacts are available.

The critic therefore **does not accept any verifier inference scope as empirical authority when exact `inference_edge_id` is absent from the bound transition lineage**. If a future strengthened lineage contract records that field, it must exactly equal the graph edge ID; a mismatch fails closed.

This intentionally leaves current transition-v1 empirical support scope unestablished rather than guessing the intended edge. A follow-up transition-provenance hardening must add a first-class exact inference-edge binding before the critic can rely on it.

### `empirical_derived` is also blocked by unclassified input provenance

Current `input_evidence_bindings` contain only `workstream_id`, `role`, and checksum. They prove identity and membership in the verified program state, but they do **not** classify whether the bound input is empirical measurement data, simulation output, computational derivation, or another origin.

Therefore a non-empty input binding list is not sufficient evidence for `empirical_derived`. The critic keeps `empirical_derived` unestablished until a provenance-bound evidence-origin classification contract exists. It will not infer empirical origin from a role name, workstream name, filename, or action label.

`empirical_direct` can only be considered after exact inference-edge identity is available and the source is provenance-compatible with an external physical experiment.

If empirical scope cannot be established, the critic emits `EMPIRICAL_SUPPORT_SCOPE_NOT_ESTABLISHED`. This does **not** downgrade or remove the evaluator's existing usable `domain_verified` relation. It records that the critic cannot independently establish the stronger empirical-scope provenance needed for an empirical/mixed claim.

The corresponding next action is `plan_only`: strengthen provenance contracts or, if no empirical support exists, plan independent empirical validation. The critic does not authorize or execute that validation.

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
- plan-only empirical provenance/validation review;
- manual interpretation of completed test artifacts.

An information-gain priority is qualitative only. It is **not** a calibrated probability or expected-value estimate.

Every proposed action carries:

- `automatic_execution_authorized: false`;
- `availability_asserted: false`.

An `execution_mode` describes only the control boundary of a proposed next step. It never proves that a corresponding request, registry entry, dataset, instrument, or other execution resource exists. In particular, sensitivity analysis, conflict reanalysis, and replication remain `plan_only` unless a separate verified planning/action layer establishes the required data and capability.

External evidence search requires explicit authorization. Physical validation remains plan-only. The critic has no generic command, network, laboratory, or execution surface.

## Public API boundary

The structural critic builder is an internal implementation layer. The public `build_scientific_critic_report` entry point in `materials_data_analyzer.research_loop.scientific_critic` delegates to the same policy-hardened facade used by the package and installed CLI.

Therefore importing the function directly from the module does not bypass:

- usable-source filtering;
- completed-test semantics;
- independence hardening;
- empirical verifier/provenance checks;
- workstream evidence-gap scoping;
- action-availability conservatism.

The private structural builder exists only so the policy overlay can compose deterministic structural findings without an import cycle.

## Falsification-first behavior

A target already `falsified_within_verified_scope` receives a `stop_and_reframe_current_target` recommendation. The negative result is preserved rather than silently averaged away or rescued by seeking additional positive results.

A target that is `contradicted_within_verified_scope` receives `reassess_or_reframe_contradicted_target`, preserving the standalone verified objection even when no positive support exists.

Neither recommendation grants an automatic stop or scientific closeout; mission/domain control remains external to the critic.

## Scientific boundary

The critic never:

- creates or upgrades evidence;
- creates `supports`, `contradicts`, or `falsifies` edges;
- changes target epistemic status;
- assigns scientific confidence scores or probabilities;
- counts unusable sources as verified scientific relations;
- counts planned/failed test executions as completed scientific tests;
- infers independence from artifact multiplicity;
- infers empirical support scope from source-node type;
- accepts verifier scope from an incomplete verifier-decision schema;
- accepts empirical scope without exact inference-edge identity;
- infers `empirical_derived` origin from unclassified input bindings;
- attributes workstream evidence requirements to targets without an explicit mapping;
- treats an action proposal as execution authorization or proof of resource availability;
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

Before the critic can accept empirical scope from transition-generated support, the transition provenance contract must additionally bind exact inference-edge identity and, for `empirical_derived`, first-class empirical input origin.

This preserves the central invariant: **research can become more autonomous without making scientific authority self-granting.**
