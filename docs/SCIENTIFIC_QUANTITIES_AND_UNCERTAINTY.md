# Scientific Quantities and Uncertainty

Status: `scaffold_stage`

v2.2.2 adds structured quantity and uncertainty records. A quantity preserves
the original value/unit, canonical value/unit, dimension, conversion history,
provenance references, and optional uncertainty metadata.

## Unit Policy

The existing builtin unit registry remains the default source of truth. A unit
backend abstraction now wraps it, and Pint is documented as an optional backend
only when installed. No new dependency is required in this step.

## Uncertainty Semantics

Uncertainty is represented by explicit kinds such as absolute uncertainty,
standard uncertainty, confidence interval, prediction interval, epistemic,
aleatoric, or unavailable. A generic confidence score is not treated as a
scientific uncertainty interval.

Classification scores without calibration evidence are not reported as
calibrated confidence or operational probability.

## Bragg Pilot

The Bragg uncertainty pilot computes d-spacing and first-order independent
uncertainty when wavelength and angle uncertainties are supplied. It normalizes
angle uncertainty to radians, checks singular domains, and returns unavailable
uncertainty when required uncertainty metadata is missing.

## Scherrer Boundary

The Scherrer pilot records uncertainty eligibility and missing-budget findings.
It does not force a misleading numeric interval when instrumental broadening,
correlation, strain broadening, or shape-factor ambiguity dominates. It does not
claim particle size or grain size.
