# Bounded Multi-Cycle Research

## Purpose

The autonomous research target requires second-, third-, and later-stage analyses. Repeating actions must not weaken the existing scientific or execution boundaries.

`mda-research-multicycle` therefore performs a finite sequence of already predeclared typed requests. It does not create a request, generate code, select an arbitrary command, access the network on its own, or upgrade a scientific claim.

Each iteration is:

```text
current verified planning state
-> one-action probe without a request
-> current authorization and selected action
-> match against next checksum-bound predeclared request
-> existing one-step research cycle
-> existing authorization / registry / budget / verifier checks
-> execute at most one typed action
-> rebuild planning state
-> classify stop / review / blocker / next action
-> repeat only if another matching predeclared request exists
```

## Why requests are predeclared

The mission-level control plane may decide that another analysis is scientifically useful, but the execution layer must not silently turn that suggestion into authority.

The first multi-cycle policy therefore keeps the existing explicit-request contract. A finite queue says which exact request files may be consumed if and only if the planner independently selects the matching action at that cycle.

If the planner selects a different action, execution stops rather than repurposing a request.

## Request queue contract

Example:

```json
{
  "schema_version": "1.0",
  "queue_id": "nasa-followup-sequence-v1",
  "adapter_id": "nasa-battery",
  "requests": [
    {
      "request_id": "protocol-stratification-1",
      "path": "requests/protocol_stratification.json",
      "sha256": "<exact request file SHA-256>",
      "expected_action_type": "protocol_stratification",
      "expected_action_version": "1.0"
    },
    {
      "request_id": "target-reference-1",
      "path": "requests/target_reference_sensitivity.json",
      "sha256": "<exact request file SHA-256>",
      "expected_action_type": "target_reference_sensitivity",
      "expected_action_version": "1.0"
    }
  ]
}
```

All request files must resolve inside the configured request root. Their bytes are hashed before any research cycle begins. Queue JSON duplicate keys are rejected.

## Run

```powershell
mda-research-multicycle `
  --adapter nasa-battery `
  --repository-root . `
  --run outputs/nasa_autonomous_loop_... `
  --registry configs/research/nasa_research_action_registry.v1.json `
  --request-queue path/to/queue.json `
  --max-cycles 8
```

If `--request-queue` is omitted, the command may inspect the current state. When a selected action requires execution, it stops at `predeclared_request_required` instead of generating a request.

## Stop rules

The multi-cycle runner stops when any of the following occurs:

- current scope is scientifically closed;
- manual semantic or failed-action review is required;
- the planner is operationally blocked;
- authorization is denied;
- the finite request queue is exhausted;
- the next queued request does not match the planner-selected action;
- one execution fails to complete under the existing one-step contract;
- the bounded planning-state fingerprint does not change after execution;
- a previously observed post-execution fingerprint repeats;
- the configured cycle limit is reached.

The library hard-caps a single invocation at 32 cycles even if a larger value is requested.

## No-progress protection

A research agent can otherwise loop forever by repeatedly executing a technically valid action that no longer changes the scientific state.

The runner therefore fingerprints the bounded planning fields after each completed action:

- current blocker;
- evidence gap;
- selected action;
- stop state;
- budget;
- evidence bindings.

If a completed action returns the same state or a previously observed post-action state, automatic repetition stops at `stopped_no_verified_state_progress`.

This fingerprint is a loop-control mechanism, not a measure of scientific information gain.

## Relationship to the epistemic graph

The multi-cycle runner answers:

> Can the next already-authorized type of computational/data action be executed safely, and should the bounded loop continue?

The epistemic graph answers:

> What does the verified result support, contradict, or falsify, and what remains unresolved?

A later integration step can use graph status to construct the next research-plan proposal. The current multi-cycle runner does not manufacture `domain_verified` graph edges from action success.

## Scientific boundary

A sequence of successful actions is not evidence that the preferred hypothesis is true. CI success is not scientific validation. Repeated simulations are not repeated physical experiments.

Every positive scientific claim must still satisfy its domain-specific evidence and closeout policy. Negative results, contradictions, failed actions, and stopped scopes remain part of the research history.
