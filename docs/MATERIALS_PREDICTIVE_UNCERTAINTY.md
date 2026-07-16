# Materials Predictive Uncertainty

Status: `v2.2.5_complete`

v2.2.5 adds a bounded prediction-interval diagnostic for the known-structure
comparison. The interval calculation is split-conformal style: residual
widths are selected from an internal calibration partition drawn from the
training partition only.

## Policy

- test labels are not used to choose interval width
- intervals are evaluated on the held-out test partition
- uncertainty is reported as empirical coverage and interval width
- unavailable uncertainty is recorded explicitly rather than replaced with a
  fake confidence value

## Interpretation

The intervals are predictive residual diagnostics for fixed baseline models.
They are not:

- DFT uncertainty
- thermodynamic uncertainty
- MP calculation uncertainty
- calibrated synthesis probability
- a phase-stability guarantee

The mean empirical coverage in the compact v2.2.5 summary is approximately
0.899 across evaluated feature-set, split, and model combinations, but this is
an internal validation diagnostic for the current cohort only.

## v2.2.6 Closeout

The closeout records prediction intervals as `prediction_interval_evaluated`
with target unit `eV/atom`. Source uncertainty remains `unavailable`, numerical
tolerance remains a validation device, and no DFT or physical ground-truth
uncertainty interval is claimed.
