# Bounded Research Cycle

## Purpose

The research-cycle layer composes the previously independent orchestration gates
into one single-step workflow:

```text
plan
-> project planning state
-> classify transition
-> verify typed-action authorization
-> optionally execute one explicit typed request
-> independently verify the action report
-> rebuild planning state
-> replan once
-> return
```

It is deliberately not an autonomous `while` loop. One invocation can execute at
most one action.

## Command

A read-only cycle that stops before execution when a request is needed:

```powershell
mda-research-loop run-research-cycle `
  --adapter nasa-battery `
  --repository-root . `
  --run <research-run> `
  --registry <planning-registry>
```

To execute the currently selected typed action, the exact typed request must be
supplied explicitly:

```powershell
mda-research-loop run-research-cycle `
  --adapter nasa-battery `
  --repository-root . `
  --run <research-run> `
  --registry <planning-registry> `
  --request <typed-action-request.json>
```

Materials Project and TM-Fe-Si currently stop at their existing scientific
boundaries and therefore execute nothing.

## Cycle statuses

The current cycle statuses are:

- `stopped_current_scope` — the current versioned scope has no justified next
  action;
- `manual_review_required` — a semantic or failed-action gate prevents safe
  continuation;
- `blocked` — budget or implementation prevents the next action;
- `authorization_denied` — a planned action exists but its current execution
  contract or budget is not authorizable;
- `explicit_request_required` — the action is authorizable, but the caller did
  not supply the required typed request;
- `one_action_executed` — exactly one explicit typed action ran, reverified, and
  the system replanned once afterward.

## No automatic request generation

The cycle never fabricates an action request from a planning recommendation.
Request schemas contain scientific and provenance fields that must remain
explicitly bound to the intended action and evidence. Therefore:

```text
automatic_request_generation_available = false
```

If authorization succeeds but no request is supplied, the cycle stops at
`explicit_request_required`.

## Maximum one action

The lower execution layer already enforces at most one new ledger action per
invocation. The cycle adds a second boundary: after that one action it rebuilds
planning state and computes the next transition, but it does not execute the new
recommendation.

Even when the after-state immediately contains another
`action_pending_authorization`, that action belongs to the next invocation.

The envelope therefore records:

```text
maximum_actions_executed_per_cycle = 1
automatic_looping_available = false
```

## Stop and unused requests

A caller may accidentally provide a request while the current research state is
terminal, blocked, or in manual review. The cycle does not consume the request.
It returns the controlling state and records `request_unused=true`.

This prevents a stale request from bypassing a newly established stop or review
boundary.

## Replanning after execution

After one successful typed execution, the cycle rebuilds the planning state from
the now-updated ledger and computes the next transition once. This makes the
single invocation auditable as:

```text
before state + transition + authorization
-> one execution envelope
-> after state + transition
```

There is no recursive call and no internal loop.

## Network, model, and evidence boundaries

The cycle orchestrator itself does not initiate network search, model fitting, or
scientific evidence promotion. Individual typed actions retain their own stricter
contracts and verifiers.

The cycle records:

```text
network_access_initiated_by_cycle_orchestrator = false
model_fit_initiated_by_cycle_orchestrator = false
scientific_evidence_upgraded_by_cycle_orchestrator = false
```

These fields describe the orchestration layer only; they do not override the
scientific or side-effect declarations of a typed action.

## Scientific boundary

A complete software cycle does not establish that the selected action was
scientifically optimal, that new evidence is independent or comparable, or that
a predictive, causal, or engineering claim is valid.

The next validation step should apply this same planning/state/transition model
to an independent materials domain. NIST AM-Bench 2018-02 is the preferred next
case because the tracked process-design audit exposes a real, interpretable
blocker: ten traces occupy only three coupled power-speed conditions, blocking
predictive and causal modeling, while the existing minimum design-augmentation
workflow already defines a bounded Diagnostic next experiment without inferring
missing responses or approving machine settings.
