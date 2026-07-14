# Scientific Constraints

Status: `development_stage` for v2.1.4.

Scientific constraints are metadata contracts for units, dimensions,
assumptions, applicability, and conservative consistency checks. They are not
physics solvers, symbolic math, dataset readers, feature-selection engines, or
model-training hooks.

## Contract Boundary

Each constraint declares:

- `constraint_id`, domain, category, description, and status
- display-only `equation_display`
- registered `evaluator_id`
- required/optional variables and expected units
- assumptions, validity conditions, invalidity conditions, and tolerance policy
- evaluation role, feature role, model role, and claim impact

`equation_display` is never parsed or executed. Only code-registered evaluator
IDs in `src/platform_core/scientific_evaluators.py` can run.

## Categories

The scaffold supports metadata for:

- domain constraints
- conservation constraints
- dimensional constraints
- monotonic constraints
- constitutive relations
- empirical engineering laws
- thermodynamic constraints
- kinetic constraints
- geometric/structural constraints
- measurement constraints
- physics-inspired feature candidates
- hybrid residual model contracts

Executable roles remain limited to `metadata_only`, `unit_check`,
`range_check`, and `consistency_check`. v2.1.4 adds bounded execution through
registered evaluator IDs and explicit scalar/small-list inputs.

## Units

`src/platform_core/units.py` provides a small unit registry with compatible
dimension checks and simple conversions such as:

- `degC` to `K`
- `nm` to `angstrom`
- `percent` to `fraction`

Unsupported units produce unavailable/unsupported metadata status rather than
silent conversion.

## XRD Example

The first explicit scientific example is X-ray diffraction:

- Bragg geometry: `n lambda = 2 d sin(theta)`
- Scherrer preconditions: `D = K lambda / (beta cos(theta))`

The execution layer can derive Bragg d-spacing and Scherrer crystallite-size
estimates from explicit metadata. It does not identify phases, calculate DFT
structures, infer particle size, or prove crystallite mechanisms. Scherrer
output remains a conditional crystallite-size estimate and requires
instrumental broadening and strain limitations to be documented.

## CLI

```powershell
python -m src.cli list-scientific-constraints
python -m src.cli inspect-scientific-constraint xrd.scherrer.preconditions
python -m src.cli list-unit-definitions
python -m src.cli convert-unit --value 25 --from degC --to K
python -m src.cli validate-scientific-input configs/examples/scientific_constraints_xrd_bragg_scherrer.json
python -m src.cli preview-scientific-check configs/examples/xrd_bragg_consistent_check.json
python -m src.cli execute-scientific-check configs/examples/xrd_scherrer_uncorrected_check.json --persist
```

Exports are local-only:

```powershell
python -m src.cli export-scientific-registry --output outputs/platform_science/scientific_registry.json --overwrite
```

## Non-Goals

v2.1.4 still does not add:

- symbolic equation execution
- arbitrary Python callables from config
- DFT, FEM, CFD, PINN, GNN, or physics simulation
- physics-constrained model training
- raw data reads
- raw/full-dataset scientific recomputation
- production decision rules
