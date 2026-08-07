# Materials Project policy-development replay

## Purpose

Benchmark-v1 is closed. Its locked 167-row partition has already been exposed and
must never be reused to select or retune an acquisition policy.

This replay is a **development-only failure-analysis stage**. It uses only the 671
rows that belonged to benchmark-v1 `seed_evidence` and `acquisition_pool`, then
creates new target-blind, whole-chemical-system development partitions. The
benchmark-v1 locked-test file is not read.

The replay answers four narrower questions before any policy-v2 rule is proposed:

1. does the current uncertainty heuristic underperform simpler baselines repeatedly,
   or was benchmark-v1 an isolated outcome?;
2. how wide is the random-acquisition distribution across deterministic seeds?;
3. does acquisition ranking depend strongly on learner family?;
4. after labels are acquired, does uncertainty systematically select a different
   target distribution from fixed/random/diversity?

## Design

The verified non-locked corpus is:

```text
benchmark-v1 seed_evidence      168 rows
benchmark-v1 acquisition_pool  503 rows
---------------------------------------
development corpus             671 rows
```

For each of five predeclared replay salts, the 671 rows are repartitioned without
using `energy_above_hull`:

```text
development_seed        20%
development_pool        60%
development_validation  20%
```

Whole `chemical_system_group` values stay in exactly one partition and the required
`reduced_formula_group` disjointness is checked.

Each replay evaluates the frozen benchmark-v1 strategies:

- `fixed_catalog` once;
- `diversity` once;
- `uncertainty` once;
- `random` at seeds 3, 11, 29, 42 and 97.

The maximum acquisition cost remains 100 material labels. Pool targets stay hidden
until a group has been selected. Development-validation targets are used only for
development replay evaluation, never for action selection inside that replay.

## Run

After pulling a main revision containing this command:

```powershell
$python = (Resolve-Path ".\.venv313\Scripts\python.exe").Path

& $python `
  .\scripts\run_materials_project_policy_development_replay.py `
  --output .\outputs\materials_project_policy_development_replay_v1
```

Expected outputs:

```text
outputs/materials_project_policy_development_replay_v1/
  development_replay_manifest.json
  diagnostic_summary.json
  partition_summary.csv
  sequence_model_results.csv
  selection_history.csv
  strategy_model_summary.csv
```

## Interpretation boundary

This replay is allowed to diagnose policy failure and support a **future policy-v2
design proposal**. It is not independent policy evidence.

In particular:

- do not read or reuse benchmark-v1 locked targets;
- do not claim policy-v2 superiority from these development replays;
- do not promote a new heuristic merely because it looks favorable on these rows;
- freeze any policy-v2 score, learner assumptions, cost rule, fallback and stopping
  rule before a new independent evaluation;
- preserve a second negative result instead of continuing to tune until something
  wins.

A policy-v2 independent benchmark should use evidence not used for policy selection.
That may require a new compatible Materials Project snapshot/cohort or another
scientifically comparable source. Source compatibility must be audited before data
are combined.

## Relationship to the Virtual Research Partner

The outer Virtual Research Partner should eventually choose among actions such as
external-source acquisition, characterization requests, model updates and correct
stops. Promoting a weak acquisition heuristic into that outer loop would create a
system that consumes data without evidence that its choices are useful.

Therefore the order is intentionally:

```text
benchmark-v1 negative adaptive result
    -> non-locked development replay
    -> predeclared policy-v2 candidate
    -> new independent evaluation
    -> only then generic autonomous acquisition integration
```
