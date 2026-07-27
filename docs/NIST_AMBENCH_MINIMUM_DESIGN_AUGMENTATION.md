# NIST AM-Bench 2018-02 Minimum Design Augmentation

## Purpose

The existing NIST AM-Bench process–characterization case contains ten trace observations at only three coupled laser-power and scan-speed conditions. The process-design audit correctly blocks predictive, causal, interaction, curvature, and optimization claims.

This workflow converts that audit into the smallest staged experimental-design recommendation that would remove the most important structural limitations. It does not fit a response model or claim that the proposed machine settings are safe or achievable.

## Run

First build the verified integrated NIST case:

```powershell
python scripts/run_nist_ambench_2018_02_workflow.py `
  --output outputs/nist_ambench_2018_02
```

Then generate the augmentation plan:

```powershell
python scripts/plan_nist_ambench_2018_02_design_augmentation.py `
  --integrated-table outputs/nist_ambench_2018_02/integrated_sample_table.csv `
  --output outputs/nist_ambench_design_augmentation
```

The output directory must be absent or empty. Existing files are preserved and rejected rather than deleted or overwritten.

## Outputs

- `nist_design_augmentation_conditions.csv`
- `nist_design_augmentation_plan.json`
- `nist_design_augmentation_plan.md`
- `nist_design_augmentation_manifest.json`

The manifest binds the input and every generated output by SHA-256.

## Now — complete the observed 2 × 3 factor grid

The current observed conditions are:

- 137.9 W / 400 mm/s;
- 179.2 W / 800 mm/s;
- 179.2 W / 1200 mm/s.

The immediate recommendation is to add only the three missing observed-level crossings:

| Target actual power | Scan speed | Minimum trace replicates |
|---:|---:|---:|
| 137.9 W | 800 mm/s | 3 |
| 137.9 W | 1200 mm/s | 3 |
| 179.2 W | 400 mm/s | 3 |

This stage requires nine new trace measurements.

After successful execution and comparability review, the six unique conditions would provide:

- direct power contrasts at shared scan speeds;
- a full-rank main-effects-plus-interaction design, rank 4 of 4;
- two condition-level residual degrees of freedom for that interaction design;
- a full-rank speed-curvature design, rank 5 of 5, with one condition-level residual degree of freedom;
- no identifiable laser-power curvature because only two power levels remain.

This is the recommended next action. Stop after this stage when the objective is factor separation and interaction diagnosis within the observed levels.

## Next — add a third power level only when curvature matters

A mathematical midpoint between the two observed calibrated powers is 158.55 W. Adding that candidate power at 400, 800, and 1200 mm/s would complete a 3 × 3 grid.

This requires another three conditions and nine trace measurements at the minimum replication level.

The resulting nine-condition design would make the six-parameter two-factor quadratic response surface structurally full rank with three condition-level residual degrees of freedom.

The 158.55 W value is only a mathematical design candidate. It must not be treated as an approved machine command. Machine safety, feasible commanded settings, and achieved calibrated actual power must be confirmed before execution.

## Later — independent validation

The planner deliberately does not auto-select numeric validation conditions. Exact validation targets require machine-safe bounds and a physically meaningful objective that are not contained in the present dataset.

A minimum diagnostic interpolation check should include:

- at least two predeclared validation conditions;
- at least three independently traceable traces per condition;
- an independent run, day, or build block;
- exclusion of validation rows from fitting, feature selection, and threshold tuning;
- comparable material, system, geometry, calibration, and metrology definitions;
- achieved calibrated power rather than commanded power alone.

Two conditions are not broad predictive validation. Transfer claims require additional conditions, independent blocks, and evidence across the intended machine, material, geometry, and measurement scope.

## Required metadata

New measurements should record at minimum:

- `sample_id`;
- `run_or_build_id`;
- acquisition order;
- spatial location;
- commanded and achieved calibrated power;
- scan speed;
- material and system identity;
- geometry and spot-size context;
- measurement batch and preprocessing identity;
- exclusions and quality flags.

Run order should be randomized or explicitly blocked. Spatial and batch effects must remain visible rather than being merged into residual noise.

## Scientific boundary

The workflow reads process identities only. It does not read or recompute melt-pool responses, fit a response model, perform optimization, infer missing responses, approve machine settings, or establish causal or predictive validity.

The output is **Diagnostic** and suitable for bounded experiment planning only.
