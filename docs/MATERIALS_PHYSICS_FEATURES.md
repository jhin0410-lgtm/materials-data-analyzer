# Materials Physics Feature Builders

Status: `implemented_bounded`.

v2.2 adds explicit composition-based feature builders for the Materials Project
case study. These builders compute registered descriptors from parsed
composition fractions and documented element-property metadata. They do not use
the target, train/test split membership, future information, network access, or
arbitrary equation execution.

## Registered Builders

The registered v2.2 feature builders are:

- `materials.atomic_radius_weighted_mean`
- `materials.atomic_radius_weighted_variance`
- `materials.atomic_radius_mismatch`
- `materials.electronegativity_weighted_mean`
- `materials.electronegativity_weighted_variance`
- `materials.electronegativity_mismatch`
- `materials.configurational_mixing_entropy`
- `materials.valence_electron_concentration`
- `materials.number_of_elements` as a control composition feature

Metadata fields include:

- `feature_property_coverage`
- `unsupported_element_count`
- `composition_normalization_residual`

## Definitions

All formulas use normalized atomic fractions `c_i`.

- Weighted mean: `sum(c_i * p_i)`
- Weighted variance: `sum(c_i * (p_i - p_mean)^2)`
- Atomic-radius mismatch:
  `sqrt(sum(c_i * (1 - r_i / r_mean)^2))`
- Electronegativity mismatch:
  `sqrt(sum(c_i * (chi_i - chi_mean)^2))`
- Ideal configurational mixing entropy:
  `-R * sum(c_i * ln(c_i))`, with
  `R = 8.31446261815324 J/mol/K`
- Valence electron concentration:
  `sum(c_i * VEC_i)`

The configurational entropy feature is an ideal composition descriptor only. It
is not the full thermodynamic entropy of a compound.

## Property Source

Element properties are sourced from the existing `pymatgen` dependency through
`pymatgen.core.Element`:

- `Element.atomic_radius`
- `Element.X` for Pauling electronegativity
- `Element.group` with a documented group-based VEC convention

The property-source metadata snapshot records the pymatgen version, supported
observed elements, definitions, units, limitations, and a deterministic checksum.

No missing element-property value is imputed, zero-filled, or silently
renormalized. If a required property is unavailable for any element in a
composition, the row is marked unavailable for the registered feature set.

## CLI

```powershell
python -m src.cli list-materials-feature-builders
python -m src.cli inspect-materials-feature-builder materials.atomic_radius_mismatch
python -m src.cli build-materials-physics-features configs/examples/materials_physics_feature_build.json
python -m src.cli validate-materials-feature-artifact outputs/materials_physics_v2_2/materials_physics_v2_2_feature_matrix.csv
```

## Current Execution

The local v2.2 build generated all 838 Materials v1.3 rows with complete
property coverage over 67 observed elements.

v2.2.2 can represent formula parsing output as an optional
`MaterialCompositionEntity` and generated feature values as quantity metadata.
This is a metadata foundation only; it does not change the v2.2.1 numerical
features or the `performance_degraded` conclusion.

v2.2.3 audits the 838-row Materials Project scope and adds a
`CrystalStructureEntity` adapter and selected structure metadata operators.
These do not create a structure-aware predictive comparison and do not change
the existing feature-use conclusion.

Allowed claim:

- `physics_informed_feature_available`

After matched predictive validation, the feature-use evidence also records:

- `physics_informed_feature_used`

Prohibited claims remain:

- physics-constrained model
- hybrid physics ML
- DFT replacement
- new materials discovery
- causal mechanism
- SHAP or feature-importance explanation
