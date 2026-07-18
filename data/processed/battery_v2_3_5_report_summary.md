# Battery v2.3.5 Source Metadata and Stability Summary

- Immediate source: `patrickfleith/nasa-battery-dataset` local package
- Exact cell lineage: 34/34
- Analysis-ready source-key matches: 2495
- Parsed cycle timestamps: 2495
- Physical discharge durations: 2495
- Protocol documents: 9 covering 34 cells
- Impedance rows: 1956 across 34 cells; complete numeric Re/Rct pairs: 1947
- Source uncertainty rows: 0
- Stability decision: `descriptive_evaluator_stable_with_policy_restrictions`

## Event Stability

| Finding | Status | Events | Trajectories | Median policy support |
|---|---|---:|---:|---:|
| missing_cycle_gap | stable_across_policies | 27 | 13 | 1.000 |
| non_monotonic_increase_candidate | stable_across_policies | 39 | 23 | 1.000 |
| non_monotonic_increase_candidate | stable_with_restrictions | 11 | 7 | 0.889 |
| non_monotonic_increase_candidate | policy_sensitive | 7 | 3 | 0.222 |
| non_monotonic_increase_candidate | insufficient_support | 28 | 18 | 0.111 |
| abrupt_capacity_drop_candidate | stable_across_policies | 18 | 13 | 1.000 |
| abrupt_capacity_drop_candidate | stable_with_restrictions | 7 | 4 | 0.889 |
| abrupt_capacity_drop_candidate | policy_sensitive | 2 | 2 | 0.222 |
| abrupt_capacity_drop_candidate | insufficient_support | 9 | 7 | 0.111 |
| abrupt_capacity_rise_candidate | stable_across_policies | 39 | 23 | 1.000 |
| abrupt_capacity_rise_candidate | stable_with_restrictions | 11 | 7 | 0.889 |
| abrupt_capacity_rise_candidate | policy_sensitive | 7 | 3 | 0.222 |
| abrupt_capacity_rise_candidate | insufficient_support | 28 | 18 | 0.111 |
| plateau_candidate | stable_across_policies | 15 | 8 | 1.000 |
| plateau_candidate | stable_with_restrictions | 28 | 13 | 0.778 |
| plateau_candidate | policy_sensitive | 25 | 14 | 0.222 |
| plateau_candidate | insufficient_support | 50 | 18 | 0.111 |
| accelerated_fade_candidate | stable_across_policies | 30 | 23 | 1.000 |
| accelerated_fade_candidate | stable_with_restrictions | 15 | 12 | 0.889 |
| accelerated_fade_candidate | policy_sensitive | 5 | 5 | 0.222 |
| accelerated_fade_candidate | insufficient_support | 7 | 7 | 0.111 |
| decelerated_fade_candidate | stable_across_policies | 25 | 23 | 1.000 |
| decelerated_fade_candidate | stable_with_restrictions | 13 | 9 | 0.889 |
| decelerated_fade_candidate | policy_sensitive | 4 | 4 | 0.222 |
| decelerated_fade_candidate | insufficient_support | 8 | 8 | 0.111 |
| high_variability_candidate | stable_across_policies | 7 | 7 | 1.000 |
| high_variability_candidate | stable_with_restrictions | 6 | 6 | 0.889 |
| terminal_low_retention_observation | stable_across_policies | 11 | 11 | 1.000 |
| terminal_low_retention_observation | stable_with_restrictions | 6 | 6 | 0.889 |
| terminal_low_retention_observation | insufficient_support | 1 | 1 | 0.111 |

Thresholds and reference/window/gap variants were predeclared. Results are descriptive candidates, not physical mechanisms. The evaluator still does not fit a mechanism, predict lifetime, or treat source uncertainty as zero.
