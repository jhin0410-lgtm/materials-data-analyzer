# Battery Capacity-Trajectory Evaluator Summary

Status: `descriptive_evaluator_executed_with_restrictions`

Evaluator: `battery_capacity_trajectory_consistency_evaluator_v1`

This is a deterministic cycle-index descriptive audit. It is not a mechanism solver, predictive model, parameter estimator, or physical-time degradation-rate analysis.

## Coverage

- Requested trajectories: 34
- Evaluated trajectories: 33
- Eligible with warnings: 33
- Blocked trajectories: 1
- Valid capacity observations: 2495

## Aggregate Findings

- `trajectory_validity`: 0
- `missing_cycle_gap`: 28
- `duplicate_cycle_candidate`: 0
- `non_monotonic_increase_candidate`: 53
- `abrupt_capacity_drop_candidate`: 26
- `abrupt_capacity_rise_candidate`: 53
- `plateau_candidate`: 66
- `accelerated_fade_candidate`: 65
- `decelerated_fade_candidate`: 62
- `high_variability_candidate`: 13
- `terminal_low_retention_observation`: 17
- `protocol_context_change_candidate`: 0

## Threshold And Uncertainty Boundary

Thresholds are fixed algorithmic detection rules. They are not measurement uncertainty, confidence intervals, learned change points, or fitted physical parameters.

## Interpretation Boundary

Findings are descriptive candidates in the observed cycle-index domain. They do not confirm a degradation mechanism, knee point, lifetime, SOH/RUL, causal effect, or production decision.
