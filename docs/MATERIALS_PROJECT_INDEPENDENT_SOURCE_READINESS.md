# Materials Project Independent Source Readiness

## Purpose

This gate answers a narrow question before any policy-v2 or confirmatory benchmark is frozen:

> Under the already-versioned Materials Project v1.3 Fe/Si query scope, does the current Materials Project database expose material identities that were not part of the original 838-row retrospective benchmark?

It is a **DevelopmentDiagnostic source inventory**, not predictive evidence and not an independent benchmark result.

## Why this exists

Benchmark-v1 has already exposed its locked 167-row result, so those target labels cannot be reused for policy selection, learner selection, stopping-rule design, or policy-v2 tuning. The non-locked development replay therefore used only the original seed and acquisition-pool rows. Its result did not justify inventing a new acquisition heuristic: `fixed_catalog` and the current frozen `uncertainty` policy remained close competitors, with strategy ordering depending on learner.

Before freezing a confirmatory policy/learner pair, the project must establish whether genuinely new Materials Project identities are available at all.

## Frozen source scope

The gate reuses `data/case_studies/materials_project/acquisition_spec_v1_3.json` for query filters:

- required elements: Fe and Si;
- 2 to 5 elements;
- `deprecated=false`;
- `include_gnome=false`;
- no `energy_above_hull`, `is_stable`, or theoretical-status target filtering.

The live request changes only the returned **fields**, restricting them to identity/scope metadata:

- `material_id`;
- `formula_pretty`;
- `chemsys`;
- `elements`;
- `nelements`;
- `deprecated`.

No target property is requested.

## Benchmark-v1 exclusion boundary

The gate does **not** open `locked/locked_test.csv`.

It reads only the already-created `oracle/partition_membership.csv`, after validating its checksum against `benchmark_manifest.json` and its benchmark-config binding. That membership file contains identifiers, disjoint grouping fields, and partition assignment, but no `energy_above_hull` target.

All 838 original `material_id` values are excluded from the current Materials Project identity response. The gate then reports the remaining new identities and their chemical-system inventory.

## Outputs

Default output directory:

`outputs/materials_project_independent_source_readiness_v1`

Files:

- `independent_source_readiness.json` — source/database/query bindings and overlap counts;
- `independent_candidate_identity.csv` — only new material identity fields, deterministically sorted by `material_id`.

The candidate CSV contains no target, model score, policy score, or ranking.

## Fail-closed checks

The audit stops if:

- benchmark membership/config checksums drift;
- benchmark membership is not exactly the original 838 unique IDs;
- membership unexpectedly contains `energy_above_hull`;
- a target/target-derived field is added to the identity query;
- the current Materials Project response contains blank/duplicate IDs;
- a returned row lacks Fe or Si;
- a returned row is outside the 2–5 element scope;
- a deprecated row is returned;
- Materials Project database version changes across the identity query;
- document serialization fails.

## What the result does not authorize

A successful inventory does **not** authorize:

- policy-v2 freeze;
- model/learner freeze;
- policy execution;
- target retrieval for the new cohort;
- independent benchmark execution;
- predictive or materials-discovery claims.

No arbitrary candidate-count threshold is applied at this stage. Candidate and group counts are measured first. If a new cohort exists, the next change must predeclare the confirmatory design—including finalist policies, learner, partition/grouping rules, endpoints, label budget, adequacy criteria, and failure interpretation—**before** independent target labels are used.

## Invocation

Set `MP_API_KEY` in the environment; do not put it on the command line or in repository files.

```powershell
$python = (Resolve-Path ".\.venv313\Scripts\python.exe").Path
& $python `
    .\scripts\inspect_materials_project_independent_source_readiness.py `
    --output ".\outputs\materials_project_independent_source_readiness_v1"
```

If rerunning intentionally after a prior completed inventory, use `--overwrite`; otherwise the output-safety layer refuses to replace an existing recognized result.
