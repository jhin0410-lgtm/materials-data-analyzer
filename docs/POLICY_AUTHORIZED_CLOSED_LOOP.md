# Policy-Authorized Local Closed Loop

## Purpose

The autonomous research target needs more than repeated action execution. A completed
analysis must become part of the research state before the next action is selected.
That state update must not silently convert successful computation into scientific
support.

This control layer closes the following bounded loop:

```text
epistemic graph
→ epistemic gate
→ current domain planner
→ current authorization check
→ one predeclared checksum-bound typed local request
→ verified action result
→ record-only immutable graph successor
→ gate the successor graph
→ rebuild planning state
→ continue or stop
```

The implementation is intentionally asymmetric: it automates **recording** but not
**scientific interpretation**.

## Record-only transition

Each consumed execution request must have one matching entry in a finite
`result_record_plan`. The entry predeclares:

- request ID and expected action type/version;
- target hypothesis/claim/conclusion;
- result node ID and result type;
- local result origin;
- bounded action class;
- neutral result statement;
- explicit limitations.

After the existing authorized executor independently verifies the typed action report,
the closed loop binds the exact report bytes by SHA-256 and appends:

1. one completed `analysis` or `simulation` node; and
2. one `tests` edge at `proposal` assessment level.

It does **not** generate `supports`, `contradicts`, or `falsifies`. It does not create
a domain-verification decision. The target's verified assessment is checked before
and after the record transition and the transition fails closed if that assessment
changes.

Directional scientific interpretation remains a separate operation through the
existing epistemic-transition proposal and domain-verifier contract.

## Execution boundary

The current closed-loop policy accepts only result records with these local semantics:

- `analysis` + `authorized_local_analysis`;
- `simulation` + `authorized_local_simulation`.

Allowed action classes are bounded computational/data operations:

- `existing_data_reanalysis`
- `computational_experiment`
- `sensitivity_analysis`
- `simulation`
- `replication`

This does not authorize arbitrary code, network evidence acquisition, or laboratory
equipment. The actual action still has to pass the existing planner, action registry,
budget, request-byte, ledger transaction, typed-dispatch, and pinned-result-verifier
checks on every cycle.

A local action that merely writes an external-data requirement is still a local
planning computation. It does not authorize the subsequent network search or
download.

## Finite authority

The runner requires two finite predeclared inputs:

1. the existing checksum-bound execution request queue;
2. a result-record plan that binds every queued request exactly once.

The runner never invents another request or another record semantic. When the queue
is exhausted while the planner still wants work, it stops with
`predeclared_request_required`.

The invocation is hard bounded to at most 32 cycles.

## Runtime-context binding

Before every possible execution, the epistemic gate reconstructs the mission program
state and binds the exact runtime-context file. The closed loop independently checks
that:

- the context bytes still match the gate SHA-256;
- the context path still matches;
- the selected workstream's research-run path matches execution;
- the selected workstream's action-registry path matches execution.

This prevents a gate decision made for one run/registry from being reused against a
different execution context.

## Immutable graph evolution

Each successful action produces a new directory:

```text
<output>/cycle_001/
  epistemic_graph.json
  record_only_transition_manifest.json
```

The parent graph is never rewritten. The successor graph records lineage including:

- parent graph SHA-256;
- request SHA-256;
- action ID;
- verified action-report SHA-256;
- result node ID.

The next cycle gates the successor graph, not the original graph.

## CLI

The existing mission-level command exposes the closed loop:

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

`--context` is mandatory for this subcommand even though it remains optional for
other `mda-research-program` operations.

## Scientific boundary

This feature demonstrates a provenance-aware **execute → observe → update state →
replan** loop. It does not demonstrate autonomous scientific truth discovery.

In particular:

- action success is not evidence of a hypothesis;
- a recorded simulation is not empirical evidence;
- a `tests` relation is not support or contradiction;
- no confidence score is invented;
- no causal/mechanistic/phase/engineering conclusion is promoted;
- physical experiments remain external unless a future lab-control capability has a
  separate safety, calibration, authorization, and provenance contract.

The next scientific layer should consume recorded results and produce a bounded
critic/inference **proposal**, preserving alternative hypotheses and counterevidence,
with domain verification remaining separate.
