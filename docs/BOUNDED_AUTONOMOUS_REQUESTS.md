# Bounded Autonomous Request Authorship

## Purpose

This layer delegates **request authorship**, not scientific authority and not raw
execution authority.

The existing research mission remains:

```text
typed_computational_actions = explicit_request
```

A separate human-authored delegation policy may permit the software to compile one
exact typed request for a planner-selected local action. The compiled request must then
pass an independent verifier and the existing typed executor/ledger transaction before
it can have any side effect.

```text
verified planning state
→ planner-selected action
→ checksum-bound delegation policy
→ bounded request compiler
→ independent request verifier
→ existing pinned typed executor
→ verified action report
→ record-only epistemic transition
→ re-gate / replan
```

No `operator_acknowledgement` is generated. The delegation policy is not represented as
a human acknowledgement and cannot be used as one.

## Delegation policy

The delegation policy is deliberately separate from the research mission. It must bind
the exact mission path and SHA-256 and must set all of these capabilities to `false`:

- `network_access`
- `physical_experiment_execution`
- `generic_command_execution`

It also contains:

- a stable policy ID;
- one planning adapter ID;
- an exact allowlist of action type + version pairs;
- a global per-request cost ceiling;
- a per-action cost ceiling.

Changing the mission bytes invalidates the delegation. Changing the policy bytes after
request compilation invalidates independent verification.

## Independent authorization layers

A machine-authored request is accepted only when **all** of these contracts agree:

1. the current mission still requires explicit typed requests;
2. the current planner selects exactly one executable action;
3. the current planning/budget authorization is
   `ready_for_explicit_execution_request`;
4. the action is in the compiler's hardcoded local-safe allowlist;
5. the independent verifier has the same separately maintained safe contract;
6. the runtime action registry marks the action `available`;
7. registry version, category, cost, installed-command binding, and verifier checks
   match the hardcoded contract;
8. the planner-selected registry ID/path/SHA matches the runtime registry;
9. the delegation policy authorizes the exact action/version and cost;
10. every action-specific path is supplied explicitly rather than inferred;
11. the research ledger is unchanged since request compilation;
12. the deterministic action ID is not already present in the ledger;
13. request and manifest bytes remain checksum-identical to the compiled snapshots.

The compiler cannot turn a `planned` registry entry into an executable action simply
because matching executor code happens to exist.

## Current NASA baseline

With the repository's current baseline NASA planning registry, the exact overlap of:

- planner/runtime registry availability;
- matching versioned hardcoded typed executor;
- bounded local-safe compiler contract;

is currently:

```text
audit_existing_battery_run @ 1.0
```

The codebase also contains typed implementations for target-reference sensitivity,
protocol stratification, and external-data-requirement generation, but their baseline
planning-registry entries are not simultaneously `available` with the same executable
version. They therefore **fail closed** under the request compiler.

This distinction is intentional:

```text
executor exists  !=  registry authorizes execution
registry available  !=  bounded compiler permits machine authorship
```

Both must be true and the contracts must match exactly.

## Action-specific inputs are never guessed

Some typed actions require paths not contained in the generic planner selection.
Examples include:

- audit: `analysis_run`
- target/reference sensitivity: `analysis_run`
- protocol stratification: `import_run`, `analysis_run`

If a required binding is not supplied, compilation returns an input-binding-required
error. The software does not infer a nearby directory, newest output, filename pattern,
or row-order relationship.

This avoids creating provenance by convention rather than by evidence.

## Hard-denied classes

The bounded compiler does not author requests for actions such as:

- fixed battery intelligence/model evaluation;
- official NASA archive import/data intake;
- human-reviewed audit closeout;
- hierarchical/state-space modeling;
- feature-family ablation;
- selective-prediction/abstention;
- source-cohort leave-one-out analysis.

Some of these may be scientifically useful. They are excluded because this first
delegated-authorship layer is intentionally narrower than the full research action
registry.

The compiler also cannot authorize:

- network downloads or searches;
- physical measurements or laboratory operations;
- generic shell/subprocess/eval/exec actions;
- model fitting merely because an action is locally callable;
- scientific support, contradiction, falsification, causality, phase identity, or
  engineering readiness.

## Compiled artifacts

One successful compile writes an immutable new directory containing:

```text
execution_request.json
policy_request_manifest.json
```

The manifest binds:

- delegation policy path/SHA;
- mission path/SHA;
- research-run ledger SHA;
- registry ID/path/SHA;
- planner-selected action fingerprint;
- exact request path/SHA/byte count;
- explicit action-specific input bindings;
- autonomy-boundary assertions.

The compiler reports `compiled_bounded_local_request_not_executed`. Compilation itself
performs no research action.

## Independent verifier

`verify_policy_authorized_request()` does not trust compiler-returned booleans. It
re-reads and revalidates the mission, policy, manifest, request, current planner,
runtime registry, budget state, and research ledger.

Successful verification means only:

```text
authorized_for_existing_typed_executor
```

It does **not** mean:

```text
scientifically supported
experiment successful
model validated
engineering ready
```

The exact verified request bytes must still be passed to the existing pinned typed
execution boundary. After execution, the policy-authorized closed loop records the
verified outcome without directional scientific inference.

## NIST and TEM/SAED boundary

This request-authorship layer does not change the scientific status of other
workstreams.

For the representative NIST AM-Bench case, missing Stage-1 design cells remain missing
physical evidence. No compiler-generated request may synthesize or interpolate those
traces.

For TEM/SAED external validation, missing independent calibrated evidence remains an
external-evidence requirement. The system may plan the requirement, but it cannot turn
that requirement into a local measurement, download, or U-Net retraining action.

## Safety invariant

The intended invariant is:

```text
machine may author a narrowly delegated local typed request
≠ machine may expand its own authority
≠ machine may manufacture scientific evidence
≠ successful execution establishes scientific truth
```

Any later widening of this layer requires an explicit versioned contract change,
independent verifier update, regression coverage, and review of the newly introduced
side-effect and scientific-claim surface.
