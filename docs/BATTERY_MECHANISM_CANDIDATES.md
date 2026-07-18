# Battery Mechanism Candidates

Status: `v2.3.3_completed`

The v2.3.3 registry defines metadata-only mechanism candidates:

- `arrhenius_temperature_dependence`
- `diffusion_transport`
- `capacity_fade_trajectory`
- `resistance_growth_trajectory`
- `temperature_capacity_coupling`
- `cycle_duration_capacity_coupling`
- `charge_discharge_efficiency_relation`
- `empirical_monotonic_degradation`
- `change_point_or_regime_transition`
- `observation_consistency_only`

Each candidate records required PGIR concepts, required observations or
context, missing-state risks, protocol comparability requirements, uncertainty
requirements, and prohibited interpretations.

The candidate registry is a requirement contract. It is not a mechanism
execution registry and it stores no callable, model, equation solver, raw
cycle payload, or credential.
