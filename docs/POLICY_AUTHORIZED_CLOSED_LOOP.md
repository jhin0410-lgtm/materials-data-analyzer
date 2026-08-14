# Policy-Authorized Local Closed Loop

## Purpose

This layer closes the first bounded autonomous execution loop without granting the
orchestrator scientific interpretation authority:

```text
epistemic graph
→ epistemic gate
→ current planner and authorization
→ one exact predeclared typed-local request
→ pinned action-result verification
→ independent report↔ledger recheck
→ record-only immutable successor graph
→ gate and replan from the successor
```

Recording is automated. Scientific interpretation is not.

## Finite authority

One invocation consumes two finite predeclared objects:

1. the existing checksum-bound execution request queue;
2. a `result_record_plan` (`schema_version: 1.1`).

Every result-record entry must bind:

- `request_id`;
- the **exact queued `request_sha256`**;
- expected action type/version;
- one gate-selected hypothesis/claim/conclusion target;
- result node ID, result type and local origin;
- a descriptive action-class label;
- neutral statement and limitations.

The plan must cover every queued request exactly once. The runner never invents a
request or extra recording semantics. A changed request file, queue file, or record-plan
file is rejected before execution.

`action_class` is descriptive plan metadata only. It cannot authorize execution,
change planner selection, or upgrade epistemic status.

## Full preflight before side effects

The runner rejects incompatibilities that can be known before an action commits:

- target node does not exist or is not a hypothesis/claim/conclusion;
- record target is outside the exact target set whose epistemic gate is used;
- predeclared result-node ID already exists;
- generated `tests` edge ID already exists;
- output root is non-empty or the next cycle directory already exists;
- the queue/plan bytes changed;
- the request bytes changed;
- the mission, current graph, or runtime-context bytes changed after gate evaluation;
- runtime-context run/registry paths differ from the actual execution paths.

The mission, graph, and runtime-context bindings are rechecked immediately before the
typed executor is delegated the request.

## Mutable orchestration state is not durable scientific provenance

NASA planning exposes `research_state` and `research_ledger` bindings whose checksums
change when an action commits. Rebinding an old evidence node to the new checksum would
silently rewrite historical provenance.

Therefore the closed-loop runner **fails before execution** if an epistemic evidence
node uses either mutable role as its durable program evidence binding:

- `research_state`
- `research_ledger`

Closed-loop graphs must instead use an immutable program evidence role or a deliberately
frozen snapshot contract. This restriction can be relaxed later only by adding a
first-class historical-snapshot registry; it is not bypassed by replacing checksums in
place.

## Verifier-to-graph TOCTOU closure

The existing typed verifier proves the action report against the request, action inputs,
outputs, and research ledger. Graph ingestion independently checks that proof is still
valid immediately before creating the successor:

1. hash the current action-report bytes;
2. reload the current research ledger;
3. require the current ledger SHA-256 to equal the SHA returned by the pinned verifier;
4. find exactly one matching action ID;
5. require ledger action status to equal verified execution status;
6. require exactly one ledger artifact with the current absolute report path, SHA-256,
   and byte count.

A report modified after typed verification therefore cannot become epistemic provenance.

The exact result-record-plan SHA is persisted in result metadata, graph lineage, and
the per-cycle transition manifest.

## Completed versus failed actions

A valid typed action report may describe either `completed` or `failed` execution.
These states are not conflated.

For a completed action the successor adds:

- one completed `analysis` or `simulation` node with the verified report as an artifact;
- one proposal-level `tests` edge to the selected target.

For a failed action the successor adds:

- one `analysis` or `simulation` node with `execution_status: failed`;
- the exact failed-report checksum only in failure provenance metadata/manifest;
- **no `tests` edge and no completed result artifact binding**.

This preserves the failed attempt without making it usable as a completed scientific
result.

## Record-only epistemic transition

The closed loop never creates:

- `supports`;
- `contradicts`;
- `falsifies`;
- `domain_verified` relations;
- confidence scores;
- causal, mechanistic, phase, or engineering conclusions.

The target's verified epistemic assessment is compared before and after every record
transition. Any protected-status change causes a fail-closed error.

Directional interpretation remains a separate proposal followed, where appropriate,
by the existing domain-verification boundary.

## Immutable graph evolution

Each successfully recorded attempt gets its own directory:

```text
<output>/cycle_001/
  epistemic_graph.json
  record_only_transition_manifest.json
```

The parent graph is not rewritten. Lineage includes:

- parent graph SHA-256;
- exact request SHA-256;
- exact result-record-plan SHA-256;
- verified research-ledger SHA-256;
- action ID and execution status;
- action-report SHA-256;
- result node ID.

The next cycle gates the successor graph, not the invocation's original graph.

## Execution boundary

Automatic recording accepts only local result semantics:

- `analysis` + `authorized_local_analysis`;
- `simulation` + `authorized_local_simulation`.

Descriptive local action classes are limited to:

- `existing_data_reanalysis`
- `computational_experiment`
- `sensitivity_analysis`
- `simulation`
- `replication`

Actual execution still has to pass the existing planner, action registry, budget,
request-byte snapshot, ledger transaction, hardcoded typed dispatch, and pinned result
verifier on every cycle.

The runner cannot execute arbitrary commands, initiate network evidence acquisition, or
execute a physical laboratory experiment. A local action that merely writes an external
data requirement remains a planning computation, not authorization for the subsequent
search/download.

## CLI

```powershell
mda-research-program run-closed-loop `
  --mission configs/research/autonomous_materials_research_mission.v1.json `
  --repository-root . `
  --context path/to/runtime_context.json `
  --base-graph path/to/current_epistemic_graph.json `
  --epistemic-workstream nasa-battery `
  --epistemic-target target-hypothesis-id `
  --research-run path/to/research_run `
  --action-registry path/to/action_registry.json `
  --request-queue path/to/request_queue.json `
  --result-record-plan path/to/result_record_plan.json `
  --artifact-root . `
  --output outputs/closed_loop_run `
  --max-cycles 8
```

`--context` is mandatory for this subcommand. One invocation is hard-bounded to at most
32 cycles.

## Scientific boundary and next layer

This proves a provenance-aware **execute → observe → update state → replan** mechanism.
It does not prove autonomous scientific truth discovery.

The next layer should be a Scientific Critic that consumes the immutable graph and
produces only evidence-bound **proposals** for:

- favored and alternative hypotheses;
- counterevidence and strongest counterexamples;
- confounders, leakage, dependence and non-independence;
- robustness/falsification checks;
- discriminating next evidence or experiment;
- explicit claim boundaries.

Those proposals must remain non-authoritative until the appropriate domain verifier
accepts the exact evidence and inference contract.
