# Materials Project acquisition suite

## Purpose

Run the four predeclared Stage 4 acquisition strategies on the already locked
Materials Project retrospective benchmark with one command.

The suite is orchestration only. It does not change the benchmark partition,
strategy definitions, 100-label budget, model inventory, or scientific claim
boundary.

Execution order is fixed:

```text
fixed_catalog sequence -> locked evaluation
random sequence        -> locked evaluation
diversity sequence     -> locked evaluation
uncertainty sequence   -> locked evaluation
strategy comparison
```

Each strategy sequence must complete before its evaluator can read the locked
partition. Later strategies do not consume earlier locked metrics; the four
strategies are already predeclared in the versioned acquisition contract.

## Run on the verified local real-data benchmark

From the repository root after pulling a main revision that contains this command:

```powershell
$python = (Resolve-Path ".\.venv313\Scripts\python.exe").Path

& $python `
  .\scripts\run_materials_project_acquisition_loop.py `
  suite `
  --output-root .\outputs\materials_project_acquisition_suite_v1
```

The existing locked benchmark is expected at:

```text
outputs/materials_project_retrospective_benchmark_v1
```

The suite writes:

```text
outputs/materials_project_acquisition_suite_v1/
  sequences/
    fixed_catalog/
    random/
    diversity/
    uncertainty/
  evaluations/
    fixed_catalog/
    random/
    diversity/
    uncertainty/
  strategy_comparison.json
```

Use `--overwrite` only to replace recognized outputs from a previous run. Do not
change benchmark-v1 strategy definitions after inspecting `strategy_comparison.json`.

## Primary scientific comparison

The predeclared primary model is `ridge_raw`. For each strategy, inspect:

- seed-only locked MAE;
- final-sequence locked MAE;
- relative MAE improvement;
- R2 and Spearman changes;
- acquired label cost;
- acquisition history and selected chemical-system groups.

The four strategies use the same maximum label budget, so the comparison asks
whether adaptive evidence selection was more useful than fixed/random acquisition
under the same retrospective evidence budget.

A favorable result is **Diagnostic**, not proof of autonomous discovery. It applies
to this computed Materials Project target and benchmark instance only. A weak or
negative result must be preserved rather than repaired by tuning the four strategies
against the locked test.

## Next decision

After the real suite result is reviewed:

- if adaptive acquisition clearly outperforms fixed/random at comparable cost,
  test the policy class on an independent benchmark before promotion;
- if performance is similar or worse, diagnose why using planner-visible evidence
  or a new benchmark version designed before another locked evaluation;
- in either case, proceed toward requirement-conditioned external source discovery
  only after preserving the benchmark-v1 result.
