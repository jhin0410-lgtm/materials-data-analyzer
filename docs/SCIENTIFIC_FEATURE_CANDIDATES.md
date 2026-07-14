# Scientific Feature Candidates

Status: `release_ready` for v2.1.5.

The scientific feature registry stores metadata for possible physics-aware
features. It does not calculate feature values, create feature tables, train
models, or prove predictive usefulness.

## Eligibility Criteria

A candidate feature must have:

- deterministic definition
- required variables and units
- applicability requirements
- prediction-time availability policy
- leakage-risk status
- assumptions and validity conditions
- expected claim boundary
- reproducible registered metadata
- no arbitrary equation execution

Statuses include `eligible_bounded`, `eligible_with_metadata_requirement`,
`diagnostic_only`, `unavailable_missing_variable`, `unavailable_missing_unit`,
`blocked_leakage_risk`, `blocked_invalid_assumption`,
`blocked_unstable_definition`, and `blocked_claim_overreach`.

## Initial Candidate Matrix

Materials candidates:

- composition-weighted mean
- composition-weighted variance
- atomic-radius mismatch
- electronegativity mismatch
- configurational mixing entropy

Battery candidates:

- capacity retention
- Coulombic-efficiency deviation
- resistance-growth rate
- temperature-exposure summary

XRD candidates:

- Bragg d-spacing
- Scherrer crystallite size

Manufacturing and reliability candidates:

- process-window distance
- mass-balance residual candidate
- cumulative exposure
- degradation slope

## Boundary

`feature_candidate` means the definition is available for future pipeline work.
It does not mean:

- the feature was generated
- the feature entered a model
- the feature improved validation
- the feature is physically complete
- the feature supports production decisions

v2.2 may add bounded builders for selected candidates after each builder has a
contract, leakage test, unit test, and claim boundary.
