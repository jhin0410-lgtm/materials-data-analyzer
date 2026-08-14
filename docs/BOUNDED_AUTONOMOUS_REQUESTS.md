# Bounded Autonomous Request Authorship

## Purpose

This layer delegates **request authorship**, not scientific authority and not raw
execution authority. The research mission remains:

```text
typed_computational_actions = explicit_request
```

A separate human-authored, checksum-bound delegation policy may let software author one
exact request for the action that the existing planner currently selects. The request
still has to pass an independent verifier and the existing pinned typed executor.

```text
verified planning state
→ planner-selected action
→ selected versioned execution registry
→ checksum-bound delegation policy
→ request compiler
→ independent verifier
→ existing pinned typed executor
→ verified action report
→ record-only epistemic transition
→ re-gate / replan
```

No `operator_acknowledgement` is synthesized.

## Planning registry and execution registry are different authorities

NASA planning uses a baseline planning registry to define the research agenda. For some
planned actions the planner may select a separately audited, versioned **execution
registry**. The compiler therefore binds both independently:

- planning-registry path, registry ID, normalized registry SHA-256, and raw-file SHA-256;
- planner-selected execution-registry path, ID, normalized registry SHA-256, and raw-file
  SHA-256.

The request's `registry` field is always the selected **execution registry**, because
that is the registry the existing executor independently re-authorizes. The compiler
never assumes that the planning registry and execution registry are the same file.

The deterministic action ID is bound to both registry byte snapshots, the mission,
delegation policy, research ledger, exact planner selection, action/version, and explicit
typed inputs.

## Delegation policy

The delegation policy binds the exact mission path/SHA and an exact action/version/cost
allowlist. It must keep all of these false:

- `network_access`
- `physical_experiment_execution`
- `generic_command_execution`

Changing mission or policy bytes invalidates the compiled authority chain.

## Independent authorization requirements

A machine-authored request is acceptable only when all of these independently agree:

1. mission still requires an explicit typed request;
2. planner/budget authorization is `ready_for_explicit_execution_request`;
3. selected action/version is in a hardcoded bounded-safe contract;
4. compiler and independent verifier maintain separate copies of that safe contract;
5. planner-selected execution registry is currently `available`;
6. execution registry version, category, cost, **exact binding**, required-input names,
   and verifier checks match the hardcoded contract;
7. planner selection and existing authorization agree on execution-registry ID/path/SHA;
8. delegation policy authorizes the exact action/version/cost;
9. action-specific directories are explicitly supplied rather than guessed;
10. planning registry, execution registry, and research ledger have not drifted;
11. request/manifest bytes remain checksum-identical;
12. deterministic action ID is not already in the research ledger.

An implementation existing in the codebase is never sufficient by itself to grant
machine-authored authority.

## NASA typed actions

The bounded contract currently recognizes four typed surfaces, but recognition does not
mean the action is always executable. The **current planner must actually select it and
its execution registry must pass the existing authorization boundary**.

### Audit

`audit_existing_battery_run@1.0`

The baseline planning registry is also the execution registry. The registry calls its
existing Battery Intelligence directory `run_output`; the typed executor request calls
the same explicit directory `analysis_run`. This legacy semantic alias is versioned and
recorded as:

```text
run_output → analysis_run
```

It is not inferred from directory names or recency.

### Target/reference sensitivity

`target_reference_sensitivity@1.0`

When selected, the planner binds the separately audited
`nasa_target_reference_action_registry.v1.json`. The request requires an explicit
`analysis_run`; `research_run` is already an explicit top-level executor binding.

### Protocol stratification

`protocol_stratification@1.0`

When selected, the planner binds
`nasa_protocol_stratification_action_registry.v1.json`. The request requires explicit
`import_run` and `analysis_run`; the research run is separately bound by the request.

### External-data requirement generation

`external_data_requirement_generation@1.0`

Its audited execution registry uses a repository-tracked `source_script` binding. That
does **not** expose generic script execution: the downstream executor still dispatches
only the hardcoded typed action/version. Its function is to write a minimum external
**evidence requirement** and stop; it does not perform a download, search, measurement,
or scientific evidence upgrade.

The registry's `research_state` and `unresolved_blocker_reports` are derived and verified
inside the typed action from the explicitly bound research run; the compiler does not
invent file paths for them.

## Inputs are never guessed

If a typed request requires `analysis_run` or `import_run` and it is not explicitly
bound, compilation fails with an input-binding-required error. The compiler does not
choose the newest directory, interpolate a missing relation, infer by filename, or rely
on row order.

## Hard-denied request authorship

This first delegated-authorship layer does not author requests for model evaluation,
NASA archive intake, human-reviewed closeout, hierarchical/state-space modeling,
feature-family ablation, selective prediction/abstention, or source-cohort leave-one-out
analysis. These may be useful research actions, but they are outside this narrow safety
contract.

It cannot authorize network access, physical laboratory execution, generic shell/eval/
exec behavior, model fitting merely because code is local, or scientific support,
contradiction, falsification, causality, phase identity, predictive readiness, or
engineering readiness.

## Compiled artifacts and independent verifier

A successful compile atomically creates:

```text
execution_request.json
policy_request_manifest.json
```

The manifest binds policy, mission, research ledger, planning registry, selected
execution registry, planner-selected action, request bytes, action inputs, explicit
registry/request aliases, and the fail-closed autonomy boundary.

Compilation status is:

```text
compiled_bounded_local_request_not_executed
```

`verify_policy_authorized_request()` independently rebuilds the current planner and
registry state and returns at most:

```text
authorized_for_existing_typed_executor
```

That means neither “scientifically supported” nor “experiment successful.” The exact
verified request bytes must still cross the existing pinned typed execution boundary.

## NIST and TEM/SAED boundary

This layer cannot synthesize NIST AM-Bench Stage-1 traces or turn missing design cells
into observations. Missing physical evidence remains missing physical evidence.

Likewise, missing independent calibrated TEM/SAED validation remains an external-evidence
requirement. The system may generate the requirement, but it cannot silently download a
replacement dataset, perform a measurement, or retrain a U-Net and call that independent
validation.

## Safety invariant

```text
machine may author a narrowly delegated typed request
≠ machine may expand its own authority
≠ machine may manufacture scientific evidence
≠ successful execution establishes scientific truth
```

Any later widening requires a new versioned compiler contract, independent verifier
change, regression coverage, and review of the new side-effect and scientific-claim
surface.
