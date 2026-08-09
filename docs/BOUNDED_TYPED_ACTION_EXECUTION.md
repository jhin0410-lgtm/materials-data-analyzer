# Bounded Typed Action Execution

## Purpose

This layer is the first common orchestration component that may actually execute
a research action. It is intentionally much narrower than a general agent or
shell runner.

Execution is allowed only after the current planner, state, transition, and
authorization gates all agree on one registered typed action and the user or
caller supplies the exact typed request file explicitly.

## Command

```powershell
mda-research-loop execute-authorized-action `
  --adapter nasa-battery `
  --repository-root . `
  --run <research-run> `
  --registry <planning-registry> `
  --request <typed-action-request.json>
```

The current execution surface is deliberately limited to `nasa-battery` because
those actions already have typed request schemas, bounded package executors,
ledger integration, and independent verifiers.

## Hardcoded dispatch only

The executor supports only the existing typed NASA action families:

- `existing_battery_run_audit`;
- `target_reference_sensitivity`;
- `protocol_stratification`;
- `external_data_requirement_generation`.

There is no generic shell command runner, subprocess template, `eval`, `exec`,
dynamic Python import, arbitrary registry command invocation, or LLM-generated
executable code path.

A registry binding is still checked during authorization, but the executor does
not turn the binding string into a command. It dispatches through a hardcoded
package-function table.

## Request binding

Immediately before dispatch, the explicit request must agree with the current
authorization context on:

- action type;
- research-run directory;
- repository root;
- verified execution-registry path;
- expected execution-registry SHA-256.

The exact request file is also recorded by path, size, and SHA-256.

## Exactly one action

Before dispatch the wrapper records the current ledger action count. After the
typed package executor returns, it reloads the verified research state and
requires the action count to increase by exactly one.

The wrapper never appends an action itself. Existing typed executors own their
transactional output and ledger mutation. This prevents duplicate action records.

If an executor appends zero or more than one action, orchestration fails closed.

## Independent post-execution verification

The wrapper does not rely only on the executor's return value. It locates the
new ledger action, requires exactly one bound `action_result.json`, and invokes
the hardcoded independent verifier for that action family again.

Therefore the flow is:

```text
authorization recheck
-> explicit request binding check
-> snapshot ledger
-> one hardcoded typed executor call
-> reload ledger
-> require exactly one new matching action
-> locate ledger-bound action_result.json
-> independent verifier
-> return execution envelope
```

## External evidence requirement action

`external_data_requirement_generation` remains a no-network requirement and
candidate-screening action. Its own typed implementation may stop the bounded
NASA loop with `external_evidence_required`; the common executor does not undo or
relabel that stop.

This layer does not add live web search, automatic download, target acquisition,
or model fitting.

## Scientific boundary

A successful execution proves that one authorized typed software action ran and
its ledger-bound report reverified. It does not establish that the action added
independent scientific evidence, improved prediction, resolved causality, or
justifies a stronger evidence level.

The next orchestration layer may perform one bounded research cycle:

```text
plan -> state -> transition -> authorization
-> optional explicit one-action execution
-> verify -> rebuild state -> replan
```

It must not contain a while-loop or execute more than one action per invocation.
