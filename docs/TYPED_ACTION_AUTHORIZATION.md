# Typed Action Authorization Gate

## Purpose

Planning selects a scientifically motivated next action. Transition logic decides
whether the current state can continue. Neither is enough to execute code.

The authorization gate independently revalidates the exact typed execution
contract before an explicit execution request can be accepted.

## Command

```powershell
mda-research-loop assess-action-authorization `
  --adapter nasa-battery `
  --repository-root . `
  --run <research-run> `
  --registry <planning-registry>
```

Current Materials Project and TM-Fe-Si adapters stop before this gate and therefore
return `not_authorizable_current_state`.

## Required checks

For an authorizable planner-selected action, the gate requires all of the
following to match the tracked repository state:

- action type;
- action version;
- `availability=available`;
- cost units;
- execution-registry ID;
- execution-registry canonical SHA-256;
- execution-registry path contained inside the repository root;
- an executable `installed_command` or `source_script` binding;
- non-empty independent verifier checks;
- at least one remaining action in the research budget;
- enough remaining cost units for the selected action.

A registry ID, SHA, version, availability, or cost drift is treated as a contract
failure, not silently updated to the newer value.

## Successful status

The strongest result is:

```text
ready_for_explicit_execution_request
```

This means the selected typed action and its execution contract are internally
consistent with the current tracked repository and budget. It does **not** mean
the action has run.

The result still records:

```text
explicit_execution_request_required = true
automatic_execution_authorized = false
action_executed = false
network_access_performed = false
model_fit_performed = false
scientific_evidence_upgraded = false
```

## Why this gate exists

A planner recommendation is not an execution capability. Without an independent
authorization gate, changes to an action registry, implementation path, cost,
availability, or verifier could make an old planning decision execute under a
new contract.

The gate prevents that time-of-check/time-of-use class of drift by reloading the
execution registry and comparing the exact binding immediately before any future
execution layer is allowed to proceed.

## Scientific boundary

Passing authorization proves software-contract consistency only. It does not
prove that the action will improve a model, reduce scientific uncertainty,
produce independent evidence, establish causal validity, or justify a stronger
scientific claim.

The next execution layer must dispatch only a hardcoded supported typed action,
accept one explicit request file, execute at most one action per invocation, run
that action's independent verifier, and reject arbitrary shell commands, Python
snippets, or LLM-generated executable code.
