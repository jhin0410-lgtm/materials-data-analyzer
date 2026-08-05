# NASA Target-Reference Sensitivity Action

## Purpose

`target_reference_sensitivity` is the first hypothesis-discrimination action
selected by the deterministic NASA next-action policy after the verified audit
reported target/reference or continuity flags.

The action asks one narrow question:

> Does the existing Ridge-versus-persistence conclusion change when the same
> absolute predictions and observed discharge capacities are expressed under
> three reference-capacity definitions fixed before execution?

It does not fit a model or search for a favorable target.

## Frozen reference definitions

The action always reports exactly these definitions:

1. `declared_reference`: the median positive finite
   `reference_capacity_ah` already declared for each battery. This remains the
   primary target definition and must be constant within tolerance.
2. `early_window_median_capacity`: the median positive finite observed
   `discharge_capacity_ah` among the first five cycle indices, requiring at
   least three observations per battery.
3. `maximum_observed_capacity`: the maximum positive finite observed
   `discharge_capacity_ah` per battery. This is an upper-envelope stress test,
   not a preferred physical reference.

The action reconstructs each model's absolute predicted capacity from the
primary declared reference, then expresses the unchanged absolute prediction
and unchanged observed capacity under each alternative reference. No target is
clipped, repaired, smoothed, or selected after inspecting metrics.

## Preconditions

- the research ledger is active;
- a completed `audit_existing_battery_run` action is checksum-bound in the
  same ledger and independently verifies;
- the analysis run contains validated cycles, validation predictions, config,
  comparability audit, scientific closeout, and run manifest;
- the request is bound to the executable action registry SHA-256;
- action and cost budgets remain available;
- research and analysis directories do not overlap.

## Installed commands

Validate the executable action contract:

```powershell
mda-research-loop validate-actions `
  --registry configs/research/nasa_target_reference_action_registry.v1.json `
  --repository-root .
```

Execute a typed request:

```powershell
mda-research-loop execute-nasa-target-reference `
  --request outputs/nasa_research_requests/target_reference_request.json
```

Re-verify the completed or failed report:

```powershell
mda-research-loop verify-nasa-target-reference `
  --report outputs/nasa_autonomous_loop/actions/NASA-TARGET-001/action_result.json
```

## Outputs

Each action writes transactionally beneath its own research-ledger action
directory:

```text
actions/<action_id>/
├── action_result.json
└── target_reference_sensitivity/
    ├── reference_definitions.json
    ├── target_reference_by_battery.csv
    ├── model_metrics_by_reference.csv
    ├── battery_metrics_by_reference.csv
    └── target_reference_sensitivity.json
```

The action report binds the request, prior audit report, immutable analysis
inputs, generated artifacts, registry hash, fixed cost, outcome, and complete
summary. The verifier recomputes every output from the original analysis tables
and confirms its research-ledger artifact binding.

## Outcomes

- `conclusion_stable_across_defensible_targets`: Ridge-versus-persistence
  ordering is unchanged for every complete predeclared reference.
- `conclusion_sensitive_to_target_reference`: the ordering changes for at
  least one predeclared reference. No alternative is promoted as primary.
- `required_reference_metadata_missing`: at least one reference cannot retain
  the complete evaluated battery and row set.
- `alternative_target_not_scientifically_defensible`: reserved for a frozen
  reference whose scientific eligibility is rejected before metric promotion.

## Scientific boundary

This action evaluates normalization robustness only. It does not establish the
physically correct capacity reference, infer degradation mechanism, correct
cycle gaps, identify protocol cohorts, improve the predictive model, establish
external validation, or change the existing NASA evidence level. A stable
negative ordering means the current Ridge failure is not explained solely by
these predeclared normalization choices; it does not prove that every possible
target definition would yield the same result.
