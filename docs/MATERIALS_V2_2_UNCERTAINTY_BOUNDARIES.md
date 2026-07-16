# Materials v2.2 Uncertainty Boundaries

Status: `release_ready`.

v2.2 separates several uncertainty concepts that should not be merged.

## Source Uncertainty

The Materials Project records used here do not provide per-record source
uncertainty. The status is `unavailable`, not zero.

## Numerical Tolerance

Snapshot-alignment tolerances and floating-point consistency checks are
validation tools. They are not scientific uncertainty intervals.

## Predictive Uncertainty

v2.2.5 records split-conformal residual prediction-interval diagnostics for the
known-structure comparison. The interval unit is the target unit, `eV/atom`.
These intervals summarize residual behavior under the current dataset, model,
and split context only.

They do not represent:

- DFT uncertainty
- experimental uncertainty
- Materials Project source uncertainty
- physical ground-truth uncertainty
- calibrated phase-stability probability

## Split And Model-Form Limits

Fold-to-fold metric variation is distinct from prediction intervals. Simple
composition and Tier-1 structure descriptors may also miss structural chemistry
or many-body effects; v2.2 does not convert that limitation into a scalar
confidence score.
