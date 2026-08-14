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

One invocation consumes a finite checksum-bound execution request queue and a finite
`result_record_plan` (`schema_version: 1.1`). Every record binds the exact queued
`request_sha256`, expected action type/version, one gate-selected epistemic target,
result semantics, and limitations. The plan covers every queued request exactly once;
the runner never invents a request or extra recording semantics.

Queue, plan, mission, runtime context, initial graph, and every queued request are read
and checksum-validated before executable authority is created. `action_class` remains
descriptive metadata only: it cannot authorize execution, alter planner selection, or
upgrade epistemic status.

## Immutable authority snapshots

After preflight, the invocation creates:

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

Each copy is written from the exact previously validated bytes and re-read to prove
byte-for-byte identity. The epistemic gate receives the per-cycle snapshot paths and
must bind those exact paths and checksums.

Later mutation of the caller's original mission, runtime-context, graph, queue, plan, or
request pathname cannot change the bytes authorizing or executing the current
invocation. The initial graph SHA reported by the run is captured at invocation start
and is never recomputed from the caller pathname after execution.

## Preflight and mutable provenance

Before side effects, the runner rejects missing/wrong-type targets, off-target result
records, node/edge collisions, non-empty output authority, checksum mismatches,
runtime run/registry mismatches, and mutable orchestration state used as durable
epistemic provenance.

`research_state` and `research_ledger` evidence roles are rejected because their hashes
change when actions commit. Node-type and role strings are normalized before this check,
so whitespace cannot bypass it. Historical scientific provenance must instead use an
immutable evidence object or deliberately frozen snapshot.

## Pinned execution boundary

`run_pinned_research_cycle` executes the exact request bytes retained in memory during
preflight. It verifies their expected SHA-256 before parsing, rejects duplicate JSON
keys, and reuses the existing authorization, transaction/recovery, budget, ledger,
hardcoded typed-dispatch, and pinned-verifier contracts.

The caller's request pathname remains provenance and relative-path context only; it is
not reopened as the source of executable request content. There is no generic command
or dynamic callable execution surface.

## Verifier-to-graph boundary

Immediately before graph creation, graph ingestion reads and hashes one action-report
snapshot, reloads the research ledger, requires the ledger SHA returned by the pinned
verifier, requires one matching action/status and exact report path/SHA/byte count, then
freezes those verified report bytes inside the cycle output.

The successor therefore references a frozen verified report rather than trusting a
later live read. Successor construction also receives the parsed base-graph value and
SHA that the gate actually evaluated, so a post-execution caller graph mutation cannot
replace the baseline epistemic state.

Transition lineage retains the parent graph SHA, request SHA, record-plan SHA,
verified-ledger SHA, report SHA, action ID/status, and result node ID.

## Completed versus failed actions

A completed local action produces a completed `analysis` or `simulation` node with the
frozen verified report and one proposal-level `tests` edge.

A failed action produces a node with `execution_status: failed`, a self-contained base64
snapshot of the verified failure-report bytes plus SHA-256/size, and an audit locator to
the frozen copy. It produces **no `tests` edge and no completed scientific-result
artifact binding**. Failure provenance remains tamper-evident without allowing a failed
attempt to masquerade as scientific support.

## Record-only epistemic transition

The loop never creates `supports`, `contradicts`, `falsifies`, `domain_verified`
relations, confidence scores, or causal/mechanistic/phase/engineering conclusions. The
target's protected verified assessment is compared before and after every record-only
transition; any change fails closed.

Directional interpretation remains a separate proposal and domain-verification step.

## Immutable graph evolution

Each recorded attempt produces:

```text
<output>/cycle_001/
  verified_action_report.json
  epistemic_graph.json
  record_only_transition_manifest.json
```

The parent graph is not rewritten. The next cycle copies the exact successor bytes into
`_authority/cycle_NNN/base_graph.json` and gates that new snapshot.

## Execution and scientific boundaries

Automatic recording accepts only local `analysis + authorized_local_analysis` or
`simulation + authorized_local_simulation` results. Actual execution still passes the
planner, registry, budget, independent authorization, ledger transaction, hardcoded
typed dispatch, and pinned result verifier.

The runner cannot execute arbitrary commands, initiate network acquisition, execute a
physical laboratory experiment, create directional scientific inference, or synthesize
new execution requests. A local external-data-requirement action is planning output, not
authorization to search or download.

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

## Validation

Focused regressions cover exact request checksum binding, live-path mutation immunity,
exact gate snapshots, successor-to-next-gate binding, completed/failed semantics,
report-mutation rejection, whitespace-normalized mutable-provenance rejection,
pre-side-effect collisions, and rejection of external/physical result semantics.

Full CI, package smoke tests, source-distribution self-tests, lint/type checks,
dependency audit, and release-evidence workflows are authoritative for the exact PR
head.

## Next layer

This establishes a provenance-aware **execute → observe → update state → replan** loop
under finite predeclared action authority. The next layers remain separate: a Scientific
Critic that proposes alternative hypotheses and discriminating evidence; a bounded
request synthesizer limited to explicitly safe registry-backed local computational
actions and still subject to independent authorization; and separate authorization for
network acquisition or physical experiments. Scientific proposals remain
non-authoritative until an appropriate domain verifier accepts the exact evidence and
inference contract.
