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

Every result-record entry binds the exact queued `request_sha256`, expected action
type/version, one gate-selected hypothesis/claim/conclusion target, result semantics,
and limitations. The plan must cover every queued request exactly once. The runner never
invents a request or extra recording semantics.

Queue, plan, mission, runtime context, initial graph, and every queued request are read
and checksum-validated before executable authority is created. `action_class` remains
descriptive metadata only: it cannot authorize execution, alter planner selection, or
upgrade epistemic status.

## Immutable authority snapshots

After preflight, the invocation creates an authority tree beneath the otherwise-empty
output directory:

```text
<output>/_authority/
  mission.json
  runtime_context.json
  request_queue.json
  result_record_plan.json
  requests/<request-id>.json
  cycle_001/{mission.json,runtime_context.json,base_graph.json}
  cycle_002/...
```

Each copy is written from the exact byte snapshot whose SHA-256 was already validated,
and the written bytes are re-read to confirm byte-for-byte identity. The epistemic gate
receives the per-cycle snapshot paths and must return bindings to those exact paths and
checksums.

A later mutation of the caller's original mission, runtime-context, graph, queue, plan,
or request pathname therefore cannot change the bytes that authorize or execute the
current invocation. The original graph SHA reported by the run is captured at invocation
start and is never recomputed from the live caller pathname after execution.

## Full preflight before side effects

The runner rejects incompatibilities that can be known before an action commits:

- missing or wrong-type targets;
- result targets outside the exact gate-selected target set;
- result-node or generated `tests`-edge collisions;
- non-empty/colliding output or authority paths;
- queue, plan, or request checksum mismatch at authority pinning;
- runtime research-run/registry paths different from the pinned context;
- mutable orchestration state used as durable epistemic provenance.

Per-cycle mission/runtime/graph snapshots are then used consistently by the epistemic
gate and research-program rebuild. The side-effecting typed executor receives the
request bytes retained in memory from invocation preflight. It does **not** reopen the
caller's mutable request pathname for request content. That pathname remains provenance
and relative-path context only.

## Mutable orchestration state is not durable scientific provenance

NASA planning exposes `research_state` and `research_ledger` bindings whose checksums
change when an action commits. Rebinding an old evidence node to a new checksum would
silently rewrite history.

The closed-loop runner therefore fails before execution if an epistemic evidence node
uses either mutable role as durable program evidence. Node-type and role strings are
normalized first, so surrounding whitespace cannot bypass the restriction. Closed-loop
graphs must instead use immutable evidence or a deliberately frozen historical snapshot.

## Pinned execution boundary

`run_pinned_research_cycle` parses and executes the exact request byte string supplied by
the authority layer. It verifies the expected SHA-256 before parsing, rejects duplicate
JSON keys, and reuses the existing authorization, transaction, recovery, budget, ledger,
hardcoded typed-dispatch, and pinned-verifier contracts.

There is no generic command or dynamic callable execution surface. A live request-file
replacement after authority pinning cannot change which bytes the typed executor sees.

## Verifier-to-graph TOCTOU closure

Immediately before graph creation, graph ingestion:

1. reads the current action-report bytes once and hashes that exact snapshot;
2. reloads the research ledger;
3. requires the ledger SHA to equal the SHA returned by the pinned verifier;
4. requires exactly one matching action ID and execution status;
5. requires the ledger to bind the report path, SHA-256, and byte count;
6. freezes those verified report bytes inside the cycle output.

A report modified after typed verification cannot become epistemic provenance. The
successor uses the frozen verified report, and successor construction receives the
parsed base-graph value plus SHA that the gate actually evaluated rather than reopening
a mutable predecessor after execution.

The exact result-record-plan SHA, request SHA, verified-ledger SHA, action-report SHA,
action ID/status, parent graph SHA, and result node ID are retained in transition
lineage and the per-cycle manifest.

## Completed versus failed actions

For a completed local action the successor adds a completed `analysis` or `simulation`
node with the frozen verified report artifact and one proposal-level `tests` edge.

For a failed action it adds a node with `execution_status: failed`, a self-contained
base64 snapshot of the verified failure-report bytes plus SHA-256/size, and an audit
locator to the frozen copy. It adds **no `tests` edge and no completed scientific-result
artifact binding**. Deleting or replacing an external failed-report pathname therefore
does not erase the bytes that were recorded, but failure still cannot masquerade as a
completed scientific result.

## Record-only epistemic transition

The closed loop never creates `supports`, `contradicts`, `falsifies`, `domain_verified`
relations, confidence scores, or causal/mechanistic/phase/engineering conclusions. The
target's protected verified assessment is compared before and after every record-only
transition; any change fails closed.

Directional interpretation remains a separate proposal followed, where appropriate,
by the existing domain-verification boundary.

## Immutable graph evolution

Each successfully recorded attempt produces:

```text
<output>/cycle_001/
  verified_action_report.json
  epistemic_graph.json
  record_only_transition_manifest.json
```

The parent graph is not rewritten. The next cycle copies the exact successor bytes into
a new `_authority/cycle_NNN/base_graph.json` and gates that snapshot. It does not return
to the invocation's original graph or re-read a mutable predecessor as scientific
authority.

## Execution boundary

Automatic recording accepts only local `analysis + authorized_local_analysis` or
`simulation + authorized_local_simulation` results. Descriptive local action classes are
limited to existing-data reanalysis, computational experiment, sensitivity analysis,
simulation, and replication.

Actual execution still has to pass the existing planner, registry, budget,
pinned-request authorization, ledger transaction, hardcoded typed dispatch, and pinned
result verifier. The runner cannot execute arbitrary commands, initiate network evidence
acquisition, or execute a physical laboratory experiment. A local action that only
writes an external-data requirement remains planning computation, not authorization to
search or download.

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

`--context` is mandatory. One invocation is hard-bounded to at most 32 cycles.

## Validation expectations

Focused regressions prove the exact-request checksum contract, immutable gate snapshots,
caller request-path mutation immunity, cycle-N successor-to-cycle-N+1 gate binding,
completed-vs-failed semantics, report-mutation rejection, whitespace-normalized mutable
provenance rejection, pre-side-effect collision checks, and rejection of external or
physical result semantics.

Full CI, package smoke tests, source-distribution self-tests, lint/type checks, dependency
audit, and release-evidence workflows remain authoritative for the exact PR head.

## Scientific boundary and next layer

This proves a provenance-aware **execute → observe → update state → replan** mechanism
under finite, predeclared action authority. It does not prove autonomous scientific
truth discovery and does not synthesize new execution requests.

The next layers remain deliberately separate:

1. a Scientific Critic that generates evidence-bound alternative hypotheses,
   counterevidence, confounder, robustness/falsification, and next-evidence proposals;
2. a bounded request synthesizer that can materialize only explicitly safe,
   registry-backed local computational actions and must still pass independent
   authorization;
3. separate authorization/planning for network acquisition and physical experiments.

Scientific proposals remain non-authoritative until the appropriate domain verifier
accepts the exact evidence and inference contract.
