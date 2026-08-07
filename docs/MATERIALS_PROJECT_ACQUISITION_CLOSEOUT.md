# Materials Project acquisition benchmark-v1 closeout

## Why this stage exists

The locked Stage 4 acquisition suite has now been executed. Once
`strategy_comparison.json` has been inspected, benchmark-v1 is no longer an
unseen policy-selection resource. The correct next step is therefore **closeout
and failure analysis**, not retuning the four strategies against the same locked
167-row partition.

The closeout command audits the completed suite and preserves this boundary.

## Run

```powershell
$python = (Resolve-Path ".\.venv313\Scripts\python.exe").Path

& $python `
  .\scripts\audit_materials_project_acquisition_suite.py `
  --suite-root .\outputs\materials_project_acquisition_suite_v1 `
  --output .\outputs\materials_project_acquisition_closeout_v1
```

The defaults bind the command to:

- `outputs/materials_project_retrospective_benchmark_v1`;
- `configs/research/materials_project_retrospective_benchmark.v1.json`.

## What is audited

The command verifies:

- the frozen four-strategy inventory;
- one benchmark ID and one locked-test SHA across all evaluations;
- sequence manifest bindings and checksums;
- acquisition-history and training-evidence checksums;
- the declaration that the sequence did not read locked-test content;
- evaluation binding to the exact completed sequence manifest;
- locked-metrics checksums;
- the predeclared primary model and dummy-median diagnostic rows;
- equal label cost before interpreting cross-strategy performance.

It writes:

```text
outputs/materials_project_acquisition_closeout_v1/
  benchmark_closeout.json
  planner_strategy_diagnostics.csv
  locked_model_diagnostics.csv
  selected_group_overlap.csv
```

## Scientific interpretation rules

The closeout distinguishes three questions.

### 1. Did additional labels help?

If the frozen strategies use the same label cost and all improve primary locked
MAE relative to seed-only training, the result is **Diagnostic** evidence that
additional retrospective labels were useful under this benchmark.

This is not evidence that arbitrary new external data will help. Real external
sources still require chemistry, target, method, unit, provenance and source-
cohort comparability checks.

### 2. Did the adaptive uncertainty policy outperform the baselines?

`uncertainty` is compared with the predeclared fixed and random baselines at the
same label cost. If it does not beat them on the predeclared primary locked MAE,
adaptive-policy superiority is closed out as **Unsupported** for benchmark-v1.

The policy must not then be modified and re-tested on the same locked partition.

### 3. Is the predictor scientifically ready?

The acquisition benchmark is a research-efficiency experiment, not a new model-
eligibility gate. Predictive interpretation remains governed by the existing
Materials Project trust contract and independent scientific validation. A lower
MAE after adding labels does not by itself establish reliable unseen-system
prediction, synthesizability, causality, DFT replacement or production screening.

## Planner-side failure analysis

`planner_strategy_diagnostics.csv` is deliberately based on sequence-side evidence:

- acquisition step count;
- selected chemical-system groups;
- cost used;
- uncertainty fallback count;
- selection-score distribution;
- target distribution of labels **after** those labels were acquired.

`selected_group_overlap.csv` measures pairwise Jaccard overlap between the groups
chosen by each frozen strategy. These diagnostics can help characterize why the
strategies behaved differently, but they do not authorize benchmark-v1 retuning.

## Next policy-development boundary

If a policy-v2 experiment is justified, define its development data and evaluation
partition **before** inspecting its outcomes. The benchmark-v1 locked 167 rows must
not be reused for policy selection or stopping-rule design.

A defensible next design is:

1. use only planner-side / explicitly designated development evidence to diagnose
   the policy class;
2. predeclare the policy-v2 score, cost, fallback and stopping rules;
3. freeze the policy implementation;
4. evaluate once on evidence that was not used for policy selection;
5. preserve negative results and stop if the proposed adaptive policy again fails
   to beat simpler baselines.

Only after the acquisition policy has independent evidence should it be generalized
into the outer Virtual Research Partner loop for requirement-conditioned external
source acquisition or characterization requests.
