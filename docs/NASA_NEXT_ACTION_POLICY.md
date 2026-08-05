# Deterministic NASA Next-Action Policy

This policy is the first action-selection baseline for the autonomous research
loop. It converts verified research state and a verified Battery audit report into
a ranked next-action recommendation.

It does not execute the selected action and it is not an LLM planner. Its purpose
is to create a transparent baseline that future statistical or language-model
planners must outperform without violating the scientific action registry.

## Command

```powershell
mda-research-loop plan-nasa-next-action `
  --run outputs/nasa_research_loop `
  --registry configs/research/nasa_research_action_registry.v1.json `
  --repository-root .
```

The command writes JSON to standard output and does not modify the research
ledger, analysis run, registry, or action budget.

## Inputs

The policy requires:

- a verified active or stopped research-loop directory;
- the exact versioned NASA action registry;
- a source checkout root used to verify available bindings;
- when an audit ledger event exists, exactly one checksum-bound
  `action_result.json` artifact that passes the independent audit-report verifier.

The policy does not accept free-text tool names or generated command strings.

## Initial selection

Before any `audit_existing_battery_run` action has been recorded, the policy
selects that available deterministic audit when both action-count and cost budgets
allow it.

Possible statuses are:

- `ready_to_execute`;
- `blocked_by_budget`.

The policy only recommends the registered action. Execution still requires a
separate typed request and the `execute-nasa-audit` command.

## Post-audit mapping

After a completed and independently verified audit, the policy applies fixed
rules:

| Verified outcome or status | Candidate | Score |
|---|---|---:|
| `partial_dimensions_inconclusive` | `external_data_requirement_generation` | 130 |
| `target_or_reference_flags_detected` | `target_reference_sensitivity` | 120 |
| `pooled_error_instability_detected` | `protocol_stratification` | 110 |
| `pooled_error_instability_detected` | `source_cohort_leave_one_out` | 100 |
| `no_audit_flag_with_complete_dimensions` | `feature_family_ablation` | 85 |
| `pooled_error_instability_detected` | `selective_prediction_abstention` | 80 |
| predictive evidence `Unsupported` | `feature_family_ablation` | 75 |
| predictive evidence `Unsupported` | `hierarchical_state_space_baseline` | 60 |

Duplicate candidates retain the higher score. Candidates are ordered by descending
score and then stable action identifier.

The ordering encodes the current scientific priority:

1. incomplete dimensions and missing evidence;
2. target/reference semantics;
3. observed protocol and source-cohort instability;
4. incremental feature value;
5. more complex latent-state modeling.

This ordering is a predeclared baseline policy, not a discovered scientific law.

## Availability and budget behavior

The selected action is classified as:

- `ready_to_execute` only when the registry marks it `available` and both action
  count and cost budgets permit it;
- `blocked_unimplemented_action` when the highest-ranked action is still
  `planned`;
- `blocked_by_budget` when either budget is exhausted;
- `no_positive_value_action` when no untried registered candidate follows from
  the verified outcomes.

The policy never substitutes a lower-scoring available action merely because the
scientifically preferred action has not yet been implemented. Doing so would make
software availability drive research reasoning.

## Failure and terminal behavior

A failed audit produces `manual_review_required`. The policy does not recommend
repeating the same audit automatically. The failure report and rollback evidence
must be reviewed or the underlying inputs must change first.

A stopped research run produces `research_stopped` with no candidate.

## Why a deterministic baseline comes before an LLM planner

A future planner may generate richer hypotheses and estimate action value from
more context. It still needs a baseline comparison. The deterministic policy
provides:

- stable, testable decisions;
- explicit triggers and scores;
- no hidden prompt dependence;
- no fabricated tool availability;
- no automatic execution of planned actions;
- reproducible failure and budget behavior.

A future planner should be evaluated against this baseline on:

- correct action or stop decisions;
- research actions required to resolve a case;
- repeated failed actions;
- unsupported claims;
- data and compute cost;
- locked-test performance and calibration.

Better prose or more varied suggestions are not sufficient evidence of a better
research policy.

## Current boundary

The policy presently reasons only after the existing Battery run audit. It does
not inspect raw literature, generate new hypotheses, calculate Bayesian expected
information gain, train an action-value model, or execute target sensitivity,
protocol stratification, source-cohort evaluation, feature ablation, state-space,
abstention, or data-requirement actions.

Those actions remain `planned` until each has a typed adapter, verifier, tests, and
scientific eligibility contract.

The closed NASA Ridge result remains `Unsupported`. A recommendation for a future
action does not change that evidence level.
