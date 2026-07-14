# Scientific Trust Boundary

Status: `release_ready` for v2.1.5.

v2.1 scientific execution supports bounded scalar and small-list consistency
checks through registered evaluators only. A successful execution records
evidence, findings, and claim boundaries; it does not prove full scientific
correctness or independent experimental validation.

## Evidence Levels

- `metadata_registered`: constraint or feature metadata exists.
- `applicability_checked`: required variables, units, semantics, or assumptions
  were checked for the supplied input.
- `consistency_checked`: range, unit, relationship, or conservation consistency
  was evaluated.
- `bounded_quantity_estimated`: a narrow registered quantity was estimated
  under supplied assumptions.
- `feature_candidate`: a deterministic feature definition is eligible as
  metadata only.
- `model_constraint_candidate`: a possible future model constraint is recorded
  with limits.
- `independently_validated`: not granted by v2.1 execution alone.
- `production_validated`: not available in this project.

## Constraint Roles

Registered constraints are classified as `validation_only`, `diagnostic_only`,
`derived_feature_candidate`, `model_constraint_candidate`,
`post_prediction_check`, `documentation_only`, or `unavailable`. A candidate
role does not mean the constraint has been applied to a model.

Examples:

- Bragg geometry: validation, bounded d-spacing estimate, and d-spacing feature
  candidate.
- Scherrer: bounded crystallite-size estimate with strong limitations.
- Composition sum: validation and post-prediction check, not a standalone
  predictive feature.
- Battery capacity monotonicity: not a hard model constraint.
- Arrhenius metadata: unavailable unless temperature range and mechanism
  assumptions are supplied.

## Claim Boundary

Allowed with limits:

- dimension and unit consistency checks
- physically consistent input checks within registered assumptions
- bounded d-spacing or crystallite-size estimates
- metadata-only physics-aware feature candidates

Prohibited without further evidence:

- phase identification
- particle size from Scherrer alone
- physics-informed feature actually used by a model
- physics-constrained model
- hybrid physics/ML model
- degradation mechanism confirmation
- production scientific decision

## Domain Boundaries

XRD Bragg checks can estimate d-spacing from supplied wavelength/order and
two-theta metadata. They do not index peaks, identify phases, confirm crystal
structure, or infer composition.

Scherrer checks can produce a bounded crystallite-size estimate. They do not
prove particle size, grain size, morphology, phase purity, or material identity.

Materials checks can validate composition fractions and conservative calculated
property tolerances. They do not prove synthesizability, thermodynamic
stability, or DFT-equivalent correctness.

Battery checks can validate capacity, efficiency, cycle ordering, and bounded
retention-style candidates. They do not prove degradation mechanism, RUL,
Arrhenius acceleration, or monotonic capacity loss.

Manufacturing and reliability checks require explicit variable semantics.
Anonymous sensor columns and SMART attributes are not assigned physical
mechanisms by default.
