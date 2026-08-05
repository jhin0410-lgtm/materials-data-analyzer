# NASA Research Action Registry

The versioned registry at
`configs/research/nasa_research_action_registry.v1.json` defines the bounded
action space for the first autonomous-research benchmark. It is a contract and
inventory, not a planner and not an executor.

## Purpose

The registry prevents a future research planner from treating every appealing
analysis idea as already implemented. Every action is explicitly classified as:

- `available`: bound to an existing installed command or repository script whose
  path is checked against the current checkout;
- `planned`: scientifically motivated but intentionally non-executable until a
  separate implementation, verifier, and regression suite exist.

A planned action cannot contain an execution binding. An available action cannot
refer to an undeclared installed command, a missing source script, an absolute
source path, or a path that escapes the repository.

## Current inventory

### Available

| Action | Binding | Scope |
|---|---|---|
| `import_official_nasa_archive` | `mda-nasa-battery-import` | Offline canonical NASA MAT/ZIP import with receipt and checksum checks |
| `run_fixed_battery_intelligence` | `mda-battery-intelligence` | Fixed exact-horizon baselines, Ridge, UQ, OOD, diagnostics, and closeout |
| `audit_existing_battery_run` | `mda-battery-result-audit` | Target/reference, error-concentration, influence, and source-review triage |
| `close_reviewed_nasa_audit` | `scripts/close_nasa_pcoe_audit.ps1` | Finalize an already reviewed 34-battery evidence package |

### Planned

- `target_reference_sensitivity`;
- `feature_family_ablation`;
- `protocol_stratification`;
- `source_cohort_leave_one_out`;
- `hierarchical_state_space_baseline`;
- `selective_prediction_abstention`;
- `external_data_requirement_generation`.

These names describe future bounded research actions. They do not claim that the
corresponding model, analysis, or evidence exists today.

## Inspecting the registry

From a source checkout:

```powershell
mda-research-loop validate-actions `
  --registry configs/research/nasa_research_action_registry.v1.json `
  --repository-root .
```

List concise action summaries:

```powershell
mda-research-loop list-actions `
  --registry configs/research/nasa_research_action_registry.v1.json `
  --repository-root .
```

Inspect one complete action contract:

```powershell
mda-research-loop describe-action `
  --registry configs/research/nasa_research_action_registry.v1.json `
  --repository-root . `
  --action-type run_fixed_battery_intelligence
```

The validated output reports a deterministic registry SHA-256 so a research
ledger can later bind action selection to an exact action-space version.

## Action contract

Each action declares:

- stable `action_type` and version;
- availability and category;
- scientific purpose;
- target blockers;
- preconditions;
- required inputs;
- expected output markers;
- integer cost units;
- a constrained execution binding or explicit `null`;
- independent verifier checks;
- allowed outcomes, including negative and inconclusive outcomes;
- prohibited effects and claims.

The registry contains no shell command string, argument interpolation, arbitrary
Python, or code-generation instruction. A later executor must translate an
available binding into typed arguments through a separately reviewed adapter.

## Scientific boundary

Registry validation proves only that the action contract is structurally valid
and that currently available bindings refer to declared repository entry points
or existing source scripts. It does not prove that:

- action preconditions are satisfied for a particular run;
- the declared expected outputs are scientifically correct;
- a planned action should be implemented;
- an available action will improve a model;
- a planner selected the right action;
- an output supports external validation or engineering use.

The current NASA predictive conclusion remains `Unsupported`. The registry
preserves that outcome explicitly and does not authorize a more favorable model,
target, cohort, or claim.

## Next implementation boundary

The next stage is not unrestricted LLM planning. It is a typed NASA action
adapter and verifier layer that can:

1. bind one available registry action to explicit input paths and parameters;
2. check preconditions before execution;
3. execute only the registered tool;
4. verify required outputs and manifest checksums;
5. record the action result in the immutable research ledger;
6. reject planned actions and any unregistered action.

Only after that deterministic path is validated should a planner be allowed to
rank and select actions.
