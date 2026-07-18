# Battery Capacity-Trajectory Consistency Evaluator

Status: `v2.3.4_completed_with_restrictions`

`battery_capacity_trajectory_consistency_evaluator_v1` is the first selected
Battery PGIR evaluator executed against the actual local trajectory artifacts.
It evaluated all 34 requested trajectories and 2,495 operational states. Of
those trajectories, 33 met the configured minimum of five valid capacity
observations with representation warnings; one four-observation trajectory was
blocked without relaxing the rule.

The evaluator uses measured discharge capacity in Ah, an ordered cycle-index
axis, source-to-Observation-to-State-to-Trajectory lineage, and the upstream
`first_n_median` reference capacity computed from the first five positive
discharge capacities before the analysis-ready quality filter. It never uses a
post-hoc maximum or selects a baseline after inspecting trajectory outcomes.

For each eligible trajectory it computes dimensionless capacity retention,
gap-aware adjacent differences, a robust difference scale, and fixed-window
descriptive findings. Row-level trajectory results and findings remain under
ignored `outputs/battery_trajectory_evaluator_v2_3/`; tracked artifacts contain
aggregate counts only.

Actual aggregate findings:

- 28 missing-cycle gaps across 13 trajectories
- 53 non-monotonic increase candidates across 26 trajectories
- 26 abrupt-drop candidates across 15 trajectories
- 53 abrupt-rise candidates across 26 trajectories
- 66 merged plateau candidates across 18 trajectories
- 65 accelerated-fade candidates across 31 trajectories
- 62 decelerated-fade candidates across 29 trajectories
- 17 terminal low-retention observations

These are algorithmic candidates in the observed cycle-index domain. They are
not degradation-mechanism labels, physical-time rates, learned change points,
predictions, or parameter estimates.

Reproduction using existing local PGIR artifacts:

```powershell
python -m src.cli preview-battery-capacity-evaluation configs/examples/battery_capacity_trajectory_evaluator.json
python -m src.cli run-battery-capacity-evaluator configs/examples/battery_capacity_trajectory_evaluator.json
python -m src.cli export-battery-capacity-evaluator-summary --config configs/examples/battery_capacity_trajectory_evaluator.json
```

The preview is side-effect free. The run requires the local v2.3.2 State and
Trajectory JSONL artifacts but performs no network access, training, solver
execution, fitting, or extrapolation.
