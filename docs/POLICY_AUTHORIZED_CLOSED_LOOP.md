# Policy-Authorized Local Closed Loop

## Purpose

This layer closes the first bounded autonomous execution loop without granting the
orchestrator scientific interpretation authority:

```text
caller inputs
→ immutable authority snapshots
→ epistemic gate over exact mission/runtime/base-graph bytes
→ current planner and authorization
→ one exact predeclared typed-local request, pinned in memory
→ typed execution from the pinned request bytes
→ pinned action-result verification
→ independent report↔ledger recheck and frozen report copy
→ record-only immutable successor graph from the exact gated base value
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
request or extra recording semantics. Queue, plan, mission, runtime context, initial
graph, and every queued request are read and checksum-validated before executable
authority is created.

`action_class` is descriptive plan metadata only. It cannot authorize execution,
change planner selection, or upgrade epistemic status.

## Immutable authority snapshots

After preflight, the invocation creates an authority tree beneath the otherwise-empty
output directory:

```text
<output>/_authority/
  mission.json
  runtime_context.json
  request_queue.json
  result_record_plan.json
  requests/
    <request-id>.json
  cycle_001/
    mission.json
    runtime_context.json
    base_graph.json
  cycle_002/
    ...
```

Each copy is written from the exact byte snapshot whose SHA-256 was already validated,
and the written bytes are re-read to confirm byte-for-byte identity. The epistemic gate
receives the per-cycle snapshot paths and must return bindings to those exact paths and
checksums.

This means a later mutation of the caller's original mission, runtime-context, graph,
queue, plan, or request pathname cannot change the bytes that authorize or execute the
current invocation. The original graph SHA reported by the run is captured at invocation
start and is never recomputed from the live caller pathname after execution.

## Full preflight before side effects

The runner rejects incompatibilities that can be known before an action commits:

- target node does not exist or is not a hypothesis/claim/conclusion;
- record target is outside the exact target set whose epistemic gate is used;
- predeclared result-node ID already exists;
- generated `tests` edge ID already exists;
- output root is non-empty or a preflight/authority path collides;
- queue, plan, or request bytes do not match their declared checksums at authority pinning;
- runtime-context run/registry paths differ from the actual execution paths;
- an evidence node attempts to use mutable orchestration state as durable provenance.

Per-cycle mission/runtime/graph snapshots are then used consistently by the epistemic
gate and research-program rebuild. The side-effecting typed executor receives the
request bytes retained in memory from invocation preflight. It does **not** reopen the
caller's mutable request pathname for request content.

The request pathname remains provenance and relative-path context only; it is not the
source of executable request content after pinning.

## Mutable orchestration state is not durable scientific provenance

NASA planning exposes `research_state` and `research_ledger` bindings whose checksums
change when an action commits. Rebinding an old evidence node to the new checksum would
silently rewrite historical provenance.

Therefore the closed-loop runner **fails before execution** if an epistemic evidence
node uses either mutable role as its durable program evidence binding:

- `research_state`
- `research_ledger`

Role and node-type strings are normalized before this check, so surrounding whitespace
cannot bypass it.

Closed-loop graphs must instead use an immutable program evidence role or a deliberately
frozen snapshot contract. This restriction can be relaxed later only by adding a
first-class historical-snapshot registry; it is not bypassed by replacing checksums in
place.

## Pinned execution boundary

`run_pinned_research_cycle` parses and executes the exact request byte string supplied by
the closed-loop authority layer. It checks the expected request SHA-256 before parsing,
rejects duplicate JSON keys, and reuses the existing authorization, transaction,
hardcoded typed-dispatch, recovery, budget, ledger, and pinned-verifier contracts.

There is no generic command or dynamic callable execution surface. A live request-file
replacement after authority pinning cannot change which bytes the typed executor sees.

## Verifier-to-graph TOCTOU closure

The typed verifier proves the action report against the pinned request, action inputs,
outputs, and research ledger. Graph ingestion independently checks that proof is still
valid immediately before creating the successor:

1. read the current action-report bytes once and hash that exact snapshot;
2. reload the current research ledger;
3. require the current ledger SHA-256 to equal the SHA returned by the pinned verifier;
4. find exactly one matching action ID;
5. require ledger action status to equal verified execution status;
6. require exactly one ledger artifact with the report path, SHA-256, and byte count;
7. freeze those verified report bytes into the cycle output before graph binding.

A report modified after typed verification therefore cannot become epistemic provenance.
The successor references the frozen verified copy rather than trusting a later live read.

The exact result-record-plan SHA is persisted in result metadata, graph lineage, and
the per-cycle transition manifest. Successor construction also receives the parsed
base-graph value and SHA that the gate actually evaluated, so post-execution mutation of
the caller's graph cannot replace the baseline epistemic state.

## Completed versus failed actions

A valid typed action report may describe either `completed` or `failed` execution.
These states are not conflated.

For a completed action the successor adds:

- one completed `analysis` or `simulation` node with the frozen verified report artifact;
- one proposal-level `tests` edge to the selected target.

For a failed action the successor adds:

- one `analysis` or `simulation` node with `execution_status: failed`;
- a self-contained base64 snapshot of the verified failure report with SHA-256 and byte
  count in failure provenance metadata;
- the frozen report locator for audit convenience;
- **no `tests` edge and no completed scientific-result artifact binding**.

The embedded snapshot prevents later deletion or replacement of the external failed
report from erasing what exact bytes were recorded, while keeping the failed attempt
unusable as a completed scientific result.

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
  verified_action_report.json
  epistemic_graph.json
  record_only_transition_manifest.json
```

The parent graph is not rewritten. Lineage includes:

- parent graph SHA-256;
- exact request SHA-256;
- exact result-record-plan SHA-256;
- verified research-ledger SHA-256;
- action ID and execution status;
- verified action-report SHA-256;
- result node ID.

The next cycle copies the successor bytes into a new `_authority/cycle_NNN/base_graph.json`
and gates that exact snapshot. It does not silently return to the invocation's original
graph or re-read a mutable predecessor pathname as scientific authority.

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
pinned-request authorization, ledger transaction, hardcoded typed dispatch, and pinned
result verifier on every cycle.

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

## Validation expectations

Focused regressions must prove, at minimum, that:

- result-record plans bind the exact request checksum;
- request pathname mutation after authority pinning cannot alter the bytes executed;
- cycle gates bind exact mission/runtime/base-graph snapshots;
- cycle 2 gates the exact successor bytes produced by cycle 1;
- completed results create only proposal-level `tests` relations;
- failed actions remain failed and carry self-contained failure provenance;
- report mutation after verification is rejected before graph creation;
- mutable `research_state`/`research_ledger` evidence roles are rejected even with
  surrounding whitespace;
- target, node, edge, and output collisions fail before side effects;
- external/physical result semantics are not accepted as local automatic results.

Full CI, package smoke tests, source-distribution self-tests, lint/type checks, dependency
audit, and release-evidence workflows remain authoritative for the exact PR head.

## Scientific boundary and next layer

This proves a provenance-aware **execute → observe → update state → replan** mechanism
under finite, predeclared action authority. It does not prove autonomous scientific
truth discovery, and it still does not synthesize new execution requests.

The next layers should remain separated:

1. a Scientific Critic that consumes the immutable graph and produces evidence-bound
   proposals for favored/alternative hypotheses, counterevidence, confounders,
   robustness/falsification checks, and discriminating next evidence;
2. a bounded request synthesizer that may materialize only explicitly safe, registry-
   backed local computational actions and must still pass the existing independent
   authorization boundary;
3. separate authorization/planning for network acquisition and physical experiments.

Scientific proposals remain non-authoritative until the appropriate domain verifier
accepts the exact evidence and inference contract.
