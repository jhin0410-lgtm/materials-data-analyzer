# Battery v2.3.3 Operator Selection

Status: `v2.3.3_completed`

Final decision: `descriptive_evaluator_only`

Selected bounded evaluator candidate:

```text
battery_capacity_trajectory_consistency_evaluator_v1
```

The selected role is `Evaluator`, not `Propagator`, `Estimator`,
`Calibrator`, or predictive model. It may audit observed capacity trajectory
consistency, baseline policy, cycle ordering, and representation gaps.

Rejected or blocked mechanism candidates:

- Arrhenius: missing rate-like response, controlled-condition semantics, and
  complete protocol comparability.
- Diffusion/transport: missing internal state, geometry, boundary conditions,
  transport-identifying protocol, and transient time-axis semantics.
- Resistance-growth mechanism: internal resistance/EIS measurement definition
  unavailable in the current analysis-ready source.

Allowed claims are limited to descriptive audit readiness and evidence-gap
documentation. Prohibited claims include activation energy, diffusion
coefficient, mechanism confirmation, causal temperature effect, SOH/RUL
prediction, and production decision support.
