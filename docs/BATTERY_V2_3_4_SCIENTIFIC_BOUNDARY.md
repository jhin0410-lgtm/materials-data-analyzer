# Battery v2.3.4 Scientific Boundary

Status: `bounded_descriptive_evidence_only`

Allowed conclusions are limited to deterministic trajectory consistency,
coverage, data-quality gaps, non-monotonic changes, abrupt-change candidates,
low-change intervals, and descriptive acceleration/deceleration candidates in
the observed cycle-index domain.

The following remain unsupported: degradation-mechanism identification,
physical knee-point confirmation, lithium plating, SEI growth, internal short,
activation energy, diffusion coefficient, resistance-growth parameters,
physical-time degradation rate, SOH/RUL or lifetime prediction, extrapolation,
causal temperature effects, and production battery decisions.

v2.3.4 executes an `Evaluator`, not a `Propagator`, parameter estimator,
calibrator, or predictive model. It reads no network source, trains no model,
fits no parameter, and invents no uncertainty. The v2.2 decisions and the
v2.3.3 `descriptive_evaluator_only` mechanism-selection boundary are preserved.

v2.3.5 does not revise this boundary. It recovers source-supported timestamp,
temperature, duration, measured-signal summary, group-protocol, and impedance
availability metadata and audits predeclared evaluator sensitivity. Its
scientific boundary is documented separately in
[Battery v2.3.5 Scientific Boundary](BATTERY_V2_3_5_SCIENTIFIC_BOUNDARY.md).
