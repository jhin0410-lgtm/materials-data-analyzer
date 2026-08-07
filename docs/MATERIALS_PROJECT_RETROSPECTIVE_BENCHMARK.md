# Materials Project Retrospective Closed-Loop Benchmark

## Purpose

This is the Stage 4 evaluation boundary for the bounded autonomous research loop.
It uses the existing **real** Materials Project v1.3 analysis-ready artifact and
creates three roles without changing the scientific question:

```text
seed evidence -> costed acquisition pool -> locked test evidence
```

The benchmark is not a new materials model, active-learning result, or discovery
claim. Its first job is to prevent planner/test leakage before any action-selection
policy is evaluated.

## Why this is the next project step

The repository already has mature analyzers and real case studies across battery,
process quality, reliability, Materials Project, and process-characterization
handoffs. The current gap is therefore not another analyzer family. The gap is
whether a Virtual Research Partner can choose useful next evidence under a budget
while respecting provenance, leakage, stop rules, and claim boundaries.

NASA now serves as the negative-result/correct-stop case and remains stopped at
`external_evidence_required`. NIST AM-Bench remains constrained by missing
physical design evidence. Materials Project provides an existing exact-provenance
real dataset suitable for locking the Stage 4 evaluation boundary without another
API acquisition.

## Source contract

Default local input:

```text
data/processed/materials_project_v1_3_analysis_ready.csv
```

This file is intentionally ignored by Git and is not copied into the repository.
The locked benchmark config expects the already documented v1.3 artifact:

- rows: `838`;
- target: `energy_above_hull` in eV/atom;
- primary features: `60`, resolved only from
  `materials_project_v1_3_descriptor_inventory.csv` where
  `primary_feature=true`;
- partition group: `chemical_system_group`;
- additionally required disjoint group: `reduced_formula_group`.

The target is a Materials Project calculated property. It is not experimental
stability, synthesizability, a new DFT calculation, or causal process evidence.

## Partition policy

Versioned contract:

```text
configs/research/materials_project_retrospective_benchmark.v1.json
```

Requested row fractions:

- seed evidence: 20%;
- acquisition pool: 60%;
- locked test: 20%.

These are benchmark engineering allocations, not physical or statistical laws.
Whole `chemical_system_group` values are assigned together, so actual row
fractions may differ because group sizes are unequal. The manifest records the
actual counts and fractions.

Assignment is deterministic and **target blind**. It uses only group membership,
group size, the requested fractions, and a versioned salt. Changing target values
must not change partition membership.

Both `chemical_system_group` and `reduced_formula_group` are required to remain
disjoint across seed, acquisition, and locked-test partitions. If this cannot be
satisfied, construction fails instead of weakening the split.

## Visibility boundary

Generated local output:

```text
outputs/materials_project_retrospective_benchmark_v1/
  benchmark_manifest.json
  planner/
    seed_evidence.csv
    acquisition_catalog.csv
  oracle/
    acquisition_labels.csv
    partition_membership.csv
  locked/
    locked_test.csv
```

Planner-visible data:

- `seed_evidence.csv`: identifier, grouping columns, primary features, and target;
- `acquisition_catalog.csv`: identifier, grouping columns, and primary features;
  **no target**.

Planner-invisible data:

- `oracle/acquisition_labels.csv`: labels that a future costed acquisition action
  may reveal only for explicitly acquired rows;
- `oracle/partition_membership.csv`: full partition bookkeeping;
- `locked/locked_test.csv`: final evaluation features and targets.

A future planner must never read `oracle/` or `locked/` directly.

## Build

From the repository root:

```powershell
$python = (Resolve-Path ".\.venv313\Scripts\python.exe").Path

& $python `
  .\scripts\build_materials_project_retrospective_benchmark.py `
  build
```

The command does not use the network, train a model, tune a model, run active
learning, or overwrite an existing non-empty benchmark output by default.

## Independent verification

```powershell
& $python `
  .\scripts\build_materials_project_retrospective_benchmark.py `
  verify
```

Verification does not merely trust the manifest. It reloads the local source,
tracked descriptor inventory, and versioned config; recomputes the target-blind
whole-group assignment; checks source/config/inventory SHA-256 bindings; verifies
all output SHA-256 values; and reconstructs the expected planner/oracle/locked
CSV content.

## Software validation versus scientific validation

Synthetic fixtures in unit tests validate software properties only:

- target values cannot influence membership;
- group leakage is rejected;
- target leakage into the acquisition catalog is rejected;
- duplicate identifiers are rejected;
- target-as-feature leakage is rejected;
- output tampering is detected.

Those fixtures provide **no** scientific evidence about Materials Project model
performance or research efficiency. The real 838-row local artifact must be used
for the benchmark execution.

## What this stage does not yet prove

This foundation does not yet show that an autonomous planner is better than a
random, fixed, or human-designed sequence. It does not yet implement costed label
acquisition, action ranking, model retraining, calibration, abstention, or
sample-efficiency comparison.

Those belong to the next Stage 4 increment and must reuse this locked partition.
Changing the partition after seeing planner performance would invalidate the
comparison unless a new benchmark version is declared before evaluation.

## Next implementation boundary

The next increment may add:

1. a bounded action that reveals selected acquisition labels from the oracle;
2. deterministic sequence runners for agent, random, fixed-pipeline, and
   documented human-designed baselines;
3. a locked evaluator that reads `locked/` only after the sequence terminates;
4. metrics for prediction/ranking, action count, labels acquired, cost,
   invalid actions, unsupported claims, and correct stop behavior.

Stage 5 positive active-discovery/sample-efficiency claims must wait until that
retrospective evaluation machinery is independently verified. Weak existing
Materials Project group-generalization results must not be relabeled as a
successful discovery benchmark.
