# Battery Identifiability Audit

Status: `v2.3.3_completed`

The audit separates:

- Structural identifiability: whether a mechanism or parameter could be
  uniquely distinguished even with ideal observations.
- Practical identifiability: whether the current sample size, noise,
  condition diversity, and missingness support stable estimation.
- Contextual identifiability: whether protocol, chemistry, time axis,
  geometry, and boundary context make a physical interpretation well-defined.

Actual conclusion:

- Arrhenius: `not_identifiable_from_current_data`
- Diffusion/transport: `not_identifiable_from_current_data`
- Resistance-growth mechanism: `not_identifiable_from_current_data`
- Capacity trajectory: `bounded_empirical_evaluator_candidate`
- Observation consistency: `descriptive_only`

The blocked Arrhenius and diffusion outcomes are intended scientific results,
not failed implementation. Missing evidence is recorded instead of filled with
defaults.
