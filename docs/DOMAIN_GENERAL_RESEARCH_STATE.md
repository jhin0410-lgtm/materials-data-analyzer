# Domain-General Research Planning State

## Purpose

The planning adapter answers **what should happen next**. The planning-state
projection answers the broader question **what research state justifies that
next action or stop**.

The state is read-only. It does not execute code, search external sources,
acquire data, fit models, control experiments, quantify expected information
gain, or upgrade scientific evidence.

## Command

```powershell
mda-research-loop show-planning-state `
  --adapter <adapter-id> `
  --repository-root .
```

The `nasa-battery` adapter additionally requires `--run` and `--registry`.

## Stable state surface

The projection records:

- research question;
- current claim boundary;
- current blocker;
- exact or currently known evidence gap;
- bounded action frontier;
- selected action, when one is ready;
- budget, constraints, and stop rules when the underlying research run exposes
  them;
- current stop state;
- explicit reopen conditions;
- checksum-bound planning evidence inherited from the domain decision.

## Information-value boundary

NASA action `score` values are deterministic policy-priority scores. They are not
expected information gain, probability of success, scientific utility, or model
improvement. The common state therefore renames them `priority_score` and emits:

```json
{
  "expected_information_gain": {
    "status": "not_quantified",
    "value": null,
    "unit": null
  }
}
```

A future information-value layer must be separately predeclared and validated
before numeric values are emitted.

## Current domain projections

### NASA Battery

The verified append-only research state supplies the research question,
constraints, stop rules, and remaining budget. The existing NASA policy remains
the only owner of NASA action ranking. The planning-state layer classifies the
returned trigger as the current blocker and distinguishes scientific/evidence,
manual-review, budget, and implementation blocks.

When the selected action is `external_data_requirement_generation`, the evidence
gap is explicitly marked as requiring definition before any source search or
acquisition.

### Materials Project

The tracked external-evidence requirement supplies the research objective. The
current blocker is the failure of the audited source universe to satisfy both:

1. source/provenance independence; and
2. compatibility with the frozen Materials Project thermodynamic target.

The frozen source-search restart criteria become explicit reopen conditions.
This does not prove that no future compatible dataset can exist.

### TM-Fe-Si

The current descriptive cross-repository case is complete at `Diagnostic`
evidence and maximum allowed use `descriptive`. The current scope therefore
stops. The state separately preserves the evidence needed to reopen a stronger
claim: exact lineage, hypothesis-relevant characterization truth/metadata, and
enough independent samples for the stated hypothesis.

## Stop-state semantics

The common statuses are:

- `continue` — a bounded action is ready or research remains active;
- `operationally_blocked` — budget or implementation currently prevents the
  selected action;
- `manual_review_gate` — semantics or a failed action requires human review;
- `terminal_for_current_scope` — current scope is complete, unsupported, or has
  no positive-value next action.

`terminal_for_current_scope` is deliberately narrower than "scientific truth is
settled forever". Reopen conditions specify what materially new evidence or new
versioned objective would justify another research cycle.

## Scientific boundary

This state is an orchestration/provenance artifact. Passing its software tests
does not establish scientific validity, optimal action selection, causal
identification, predictive generalization, or engineering readiness.

The next layer should consume this state to validate **state transitions**:
continue, request evidence, manual review, stop, and reopen. Automatic execution
must remain behind a separate bounded-action authorization gate.
