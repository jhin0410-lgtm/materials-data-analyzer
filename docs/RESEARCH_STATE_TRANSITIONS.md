# Research State Transitions

## Purpose

The domain-general planning state explains the current research question,
blocker, evidence gap, and stop/reopen conditions. This layer maps that state to
a bounded **control transition** without executing anything.

The transition contract deliberately separates:

- planning from execution;
- a missing-evidence requirement from acquiring evidence;
- a stop from a permanent scientific conclusion;
- evidence submitted for reopening from evidence that actually satisfies the
  reopen condition.

## Current transition command

```powershell
mda-research-loop decide-transition `
  --adapter <adapter-id> `
  --repository-root .
```

The `nasa-battery` adapter also requires its existing `--run` and `--registry`.

The possible current transition types are:

- `action_pending_authorization` — a bounded action is selected, but this layer
  does not authorize or execute it;
- `evidence_requirement_pending_authorization` — the next bounded action is to
  define missing evidence before any search or acquisition;
- `manual_review_required` — semantics, failure state, or an incomplete active
  planning state prevents safe automatic continuation;
- `blocked` — budget or implementation prevents continuation;
- `stop_current_scope` — the present versioned scope has no justified next
  action.

Every transition emits `automatic_execution_authorized=false` and
`automatic_reopen_authorized=false`.

## Reopen review

A terminal state can expose explicit reopen conditions. New evidence may be
submitted against one frozen condition using:

```powershell
mda-research-loop prepare-reopen-review `
  --adapter <adapter-id> `
  --repository-root . `
  --condition-index 0 `
  --evidence <path-to-file>
```

The command records the selected condition plus the exact evidence-file path,
size, and SHA-256 checksum. It then returns:

- `manual_semantic_review_required`;
- `condition_satisfaction_established=false`;
- `scientific_comparability_established=false`;
- `automatic_reopen_authorized=false`;
- `automatic_execution_authorized=false`.

This is intentional. A checksum proves file identity; it does not prove that the
file is relevant, authoritative, independent, comparable, scientifically valid,
or sufficient to satisfy the condition.

## Why reopening is fail-closed

A system that automatically reopens a failed or completed hypothesis whenever a
new file appears invites favorable-source selection and repeated searching until
a desired result is found. The reopen boundary therefore requires a frozen
condition first and human/typed scientific review second.

For the current Materials Project case, for example, a new database file is not
enough. It must address the already frozen source-independence and thermodynamic
semantic blocker. The transition layer does not decide that from file presence.

For TM-Fe-Si, additional measurements do not automatically promote the current
Diagnostic/descriptive case into predictive, causal, or engineering evidence.

## Scientific boundary

This transition layer validates software control flow and provenance binding. It
does not establish scientific validity, expected information gain, source
comparability, predictive improvement, causal identification, or engineering
readiness.

The next layer may authorize execution only for an already registered typed
action whose version, availability, budget, execution registry, request schema,
and independent verifier can all be checked. Arbitrary command execution remains
out of scope.
