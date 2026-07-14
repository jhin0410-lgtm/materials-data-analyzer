# XRD Physics Validation

Status: `development_stage` for v2.1.4.

The XRD checks are bounded metadata and scalar consistency checks. They are not
phase identification, structure refinement, composition inference, or material
confirmation.

## Bragg Geometry

Inputs:

- `two_theta`
- `wavelength`
- optional `diffraction_order`
- optional `supplied_d_spacing`

The execution layer converts angle and length units to canonical units,
computes `theta = two_theta / 2`, applies the default `n = 1` unless supplied,
and derives `d = n lambda / (2 sin(theta))`. If a supplied d-spacing is present,
the residual is compared to a documented tolerance and optional uncertainty.

Allowed claims are limited to Bragg geometry consistency and lattice-spacing
estimation. Phase identification, crystal structure confirmation, and material
composition confirmation are explicitly prohibited.

## Scherrer Estimate

Inputs:

- `two_theta`
- `wavelength`
- `fwhm`
- optional `shape_factor`
- optional `instrumental_broadening`

The execution layer converts FWHM to radians, checks positive beta, optionally
applies instrumental broadening correction, and computes a crystallite-size
estimate. If instrumental broadening is absent, the result is marked as an
uncorrected estimate. If corrected beta is not positive, the result is invalid.

Scherrer output is a crystallite-size estimate only. It is not particle size,
phase identification, strain separation, or a general mechanism diagnosis.
