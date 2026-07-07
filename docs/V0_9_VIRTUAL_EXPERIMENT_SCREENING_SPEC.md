# v0.9 Virtual Experiment Screening Spec

Spec date: 2026-07-07

Scope: design document only. No code, data, outputs, README, raw files, processed CSVs, or existing reports were modified for this spec.

## v0.9 Goal

Clarify `materials_data_analyzer` simulation mode as a **candidate condition screening workflow**, not just a regression prediction helper.

The project identity remains:

```text
Tabular Engineering Data Analysis & Virtual Experiment Screening Platform
```

The target v0.9 workflow is:

```text
training CSV
-> target/features 지정
-> model validation
-> candidate/scenario condition 입력 또는 생성
-> predicted target 계산
-> ranking
-> OOD/domain warning
-> Markdown virtual experiment report
```

v0.9 should keep the current CLI-first design and avoid overstating results. The output language should use terms such as candidate screening, virtual experiment screening, and data-driven surrogate screening. It should not describe results as automatic optimization, confirmed best conditions, physics simulation, or real experiment replacement.

## Current Simulation Capability Audit

Files reviewed:

```text
src/process_data.py
src/analyzers/simulation.py
src/reports.py
src/results.py
tests/test_simulation.py
README.md
docs/PROJECT_STRUCTURE.md
```

### CLI Entry Points

`src/process_data.py` currently exposes simulation-related CLI options:

- `--mode simulation`
- `--target`
- `--features`
- `--scenario-input`
- `--goal` with `maximize` or `minimize`
- `--design-method` with `random` or `grid`
- `--design-samples`
- `--grid-levels`
- `--group-column`
- `--run-name`

### Modeling and Validation

Current simulation mode supports:

- Target/features-based numeric regression.
- Target and feature column validation.
- Numeric feature validation.
- Separate target/features validation so the target cannot also be used as a feature.
- Missing target/feature row removal for model training.
- `RandomForestRegressor(n_estimators=100, random_state=42)` as the default surrogate model.
- `LinearRegression()` factory support internally, though the CLI currently uses random forest by default.
- Train/test split for datasets with at least 10 complete rows.
- Small dataset fallback where train/test split is skipped.
- Group-aware train/test split with `GroupShuffleSplit` when `--group-column` is supplied.
- Group-aware cross-validation with `GroupKFold` when group count is sufficient.
- Random K-fold cross-validation when no group column is supplied.
- Train/test metrics: R2, MAE, RMSE.
- Cross-validation metrics: fold, validation type, R2, MAE, RMSE, note.
- Overfitting diagnostics using R2 gap and RMSE ratio with cautious language such as possible overfitting signal.
- Train/test prediction rows with `actual`, `predicted`, and `residual`.
- Group column preservation in prediction output when group-aware validation is used.

### Feature and Sensitivity Summaries

Current simulation mode generates:

- `feature_ranges.csv`
- `feature_summary.csv`
- `feature_importance.csv`
- `sensitivity_summary.csv`

Feature summary supports:

- Random forest feature importances when available.
- Linear model coefficients when available.
- Sensitivity-style correlation between candidate feature values and predicted target values.

### Scenario and Candidate Handling

Current simulation mode supports two candidate sources:

1. Scenario CSV input through `--scenario-input`.
2. Generated candidate design when `--scenario-input` is omitted.

Current scenario handling:

- Loads scenario CSV.
- Applies standard column-name cleanup.
- Validates required feature columns exist.
- Validates scenario feature columns are numeric.
- Keeps `scenario_id` when present.
- Creates `scenario_id` from row order when missing.
- Adds `design_source = scenario_input`.

Current generated design handling:

- Uses observed training feature ranges from `feature_ranges.csv`.
- Supports random design with `--design-method random`.
- Supports grid design with `--design-method grid`.
- Uses `--design-samples` for random design.
- Uses `--grid-levels` for grid design.
- Limits grid design to `MAX_GRID_DESIGN_ROWS = 10_000`.
- Generates `scenario_id` values such as `virtual_0001`.
- Adds `design_source = generated_random` or `generated_grid`.

### Prediction, Ranking, and Outputs

Current simulation mode predicts candidate rows and ranks them by predicted target:

- Prediction column: `predicted_{target_column}`
- Ranking column: `screening_rank`
- Ranking direction: descending for `maximize`, ascending for `minimize`
- Missing candidate feature rows are excluded from prediction and counted.

Current saved files include:

```text
simulation_training_data.csv
simulation_predictions.csv
model_metrics.csv
train_test_metrics.csv
overfitting_diagnostics.csv
cross_validation_metrics.csv
feature_ranges.csv
feature_summary.csv
feature_importance.csv
sensitivity_summary.csv
virtual_experiment_design.csv
virtual_experiment_predictions.csv
scenario_predictions.csv
scenario_ranking.csv
simulation_report.md
```

Current visualization/report support includes:

- Actual vs predicted figures.
- Residual figures.
- Feature importance figures.
- Scenario/candidate prediction figures.
- 1D feature-response figures from candidate predictions.
- Markdown simulation report with Important Notes, Model Validation, Virtual Experiment Screening, top 5 ranking, and limitations-oriented language.

### Test Coverage

`tests/test_simulation.py` currently covers:

- Missing target validation.
- Non-numeric feature validation.
- Target-in-features validation.
- Scenario CSV missing feature validation.
- Random design generation inside observed ranges.
- Grid design generation.
- Scenario prediction and ranking.
- Maximize/minimize ranking direction.
- Sensitivity summary columns.
- Feature summary ordering.
- Train/test metrics generation.
- Overfitting diagnostic language.
- Cross-validation split adjustment.
- Group split separation by `battery_id`.
- Random split fallback when no group column is provided.
- Group CV skip when group count is too small.
- Residual consistency.
- End-to-end virtual output creation without scenario input.

## Current Gaps

The current implementation already has a functional virtual experiment foundation. v0.9 should polish clarity, naming, and screening reliability rather than add heavy modeling.

Current gaps:

- Candidate screening outputs are still partly named as `scenario_*`, even when generated virtual experiment candidates are used.
- There is no explicit `candidate_predictions.csv` or `candidate_ranking.csv` naming layer.
- Candidate ID language is still centered on `scenario_id`; v0.9 should define a standard `candidate_id` concept while keeping backward compatibility with `scenario_id`.
- Candidate condition schema validation is minimal: missing and non-numeric feature checks exist, but optional ID/note/group columns are not standardized.
- OOD warnings are not yet saved as a first-class table.
- Feature min/max range checks are used for generated designs, but external scenario candidates are not flagged when outside training ranges.
- Constraint violation output is not yet explicit.
- Missing candidate feature rows are excluded and counted, but invalid candidate rows do not yet produce a detailed warning table.
- Ranking does not show warning counts or warning severity per candidate.
- Ranking tie behavior is implicit through sort order, not documented or standardized.
- The Markdown report title is still `Simulation Report`, even though the analysis type says `data-driven virtual experiment screening`.
- The virtual experiment report is not yet clearly separated as a candidate screening report with sections for warnings and recommended next experiments.
- Sample candidate CSV guidance is weak.
- README quickstart currently shows simulation examples, but not a dedicated candidate condition screening example with a candidate CSV schema.

## Proposed v0.9 User Workflow

Primary scenario/candidate CSV workflow:

```powershell
python src/process_data.py --mode simulation `
  --input data/sample/experiment_process.csv `
  --target yield_percent `
  --features process_temp_c process_time_min pressure_mpa thickness_um `
  --scenario-input data/sample/candidate_conditions.csv `
  --goal maximize `
  --run-name sample_virtual_experiment
```

Generated candidate workflow:

```powershell
python src/process_data.py --mode simulation `
  --input data/sample/experiment_process.csv `
  --target yield_percent `
  --features process_temp_c process_time_min pressure_mpa thickness_um `
  --design-method random `
  --design-samples 100 `
  --goal maximize `
  --run-name sample_virtual_experiment_random
```

Grid workflow for small feature sets:

```powershell
python src/process_data.py --mode simulation `
  --input data/sample/experiment_process.csv `
  --target yield_percent `
  --features process_temp_c pressure_mpa `
  --design-method grid `
  --grid-levels 5 `
  --goal maximize `
  --run-name sample_virtual_experiment_grid
```

Group-aware validation workflow:

```powershell
python src/process_data.py --mode simulation `
  --input data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv `
  --target capacity_retention_percent `
  --features cycle_index ambient_temperature_c temperature_mean_c current_mean_a voltage_mean_v `
  --group-column battery_id `
  --goal maximize `
  --run-name battery_group_virtual_screening
```

## Candidate Condition Input Design

v0.9 should define candidate CSVs as condition tables, not result tables.

Recommended candidate CSV schema:

| Column | Required | Description |
| --- | --- | --- |
| `candidate_id` | Recommended | Stable candidate condition identifier. |
| feature columns | Required | Must match `--features` after column-name cleanup and must be numeric. |
| `note` | Optional | User note such as process recipe source, hypothesis, or operator comment. |
| `condition_label` | Optional | Grouping label such as baseline, high_temp, low_pressure, trial_set_a. |
| `group` or domain-specific group column | Optional | Optional grouping label for reporting only; not required for model validation. |

Backward compatibility:

- If a CSV has `scenario_id`, v0.9 should keep accepting it.
- Internally, v0.9 can create a standardized `candidate_id` column from `candidate_id`, `scenario_id`, or row order.
- Existing `scenario_predictions.csv` and `scenario_ranking.csv` outputs should not be removed abruptly; add candidate-named outputs first.

Validation expectations:

- Required feature columns must exist.
- Feature columns must be numeric.
- Candidate rows with missing feature values should be retained in warning tables, but excluded from model prediction.
- Extra columns should be preserved when useful for traceability.

## Generated Candidate Design

Current random/grid design should remain simple and transparent.

Recommended v0.9 generated design behavior:

- Continue using training feature min/max ranges from complete modeling rows.
- Random design:
  - Generate `--design-samples` rows.
  - Sample each feature uniformly between observed train min and max.
  - Save candidate source as `generated_random`.
- Grid design:
  - Generate evenly spaced values per feature.
  - Use `--grid-levels`.
  - Keep max-row protection to prevent accidental huge grids.
  - Save candidate source as `generated_grid`.

Recommended saved table:

```text
outputs/{run_name}/processed/candidate_conditions.csv
```

This can be an alias/copy of the current `virtual_experiment_design.csv` with v0.9-standard column names:

- `candidate_id`
- `candidate_source`
- feature columns
- optional metadata columns

Current generated output `virtual_experiment_design.csv` can remain for compatibility.

## Screening Outputs

v0.9 should make candidate screening outputs explicit and easier to compare across runs.

Recommended new/standardized files:

```text
candidate_conditions.csv
candidate_predictions.csv
candidate_ranking.csv
candidate_domain_warnings.csv
virtual_experiment_summary.csv
virtual_experiment_report.md
```

Backward-compatible files to keep during v0.9:

```text
virtual_experiment_design.csv
virtual_experiment_predictions.csv
scenario_predictions.csv
scenario_ranking.csv
simulation_report.md
```

Recommended output responsibilities:

| File | Purpose |
| --- | --- |
| `candidate_conditions.csv` | Candidate table used for screening, whether loaded from CSV or generated. |
| `candidate_predictions.csv` | One row per valid predicted candidate, preserving candidate metadata. |
| `candidate_ranking.csv` | Ranked candidates based on goal and predicted target. |
| `candidate_domain_warnings.csv` | Long-format warning table for OOD/domain/invalid candidate issues. |
| `virtual_experiment_summary.csv` | One-row or compact summary of run settings, model validation, candidate counts, warning counts, and top candidate IDs. |
| `virtual_experiment_report.md` | Screening-focused Markdown report. |

## OOD / Domain Warning Design

v0.9 should start with transparent min/max warning logic. Do not add uncertainty models, conformal prediction, Bayesian optimization, or hidden scoring.

Training range source:

- Use complete modeling rows after target/features cleanup.
- Use the same feature ranges saved in `feature_ranges.csv`.

Candidate warning rule:

- For each candidate and each feature:
  - If candidate value is missing: `missing_candidate_value`.
  - If candidate value is below `train_min`: `below_training_range`.
  - If candidate value is above `train_max`: `above_training_range`.
  - Else: no OOD warning.

Recommended warning columns:

```text
candidate_id
feature
train_min
train_max
candidate_value
warning_type
severity
message
```

Recommended severity:

| Condition | Severity |
| --- | --- |
| Missing required feature value | `error` |
| Outside training min/max by any amount | `warning` |
| Inside range | no row in warnings table |

Optional future extension:

- Add distance ratio from nearest range boundary.
- Add low/medium/high severity thresholds.

Do not add these in initial v0.9 unless the basic warning table is stable.

## Constraint Checking Design

v0.9 constraint checking should remain simple.

Recommended checks:

- Required feature exists.
- Required feature is numeric.
- Required feature value is not missing for prediction.
- Feature value is within training min/max range, or warning is emitted.
- Optional lower/upper bounds can be supported later through a lightweight config or simple table, but should not become a full rule engine.
- `goal` must remain `maximize` or `minimize`.

Potential optional columns for future candidate CSV:

```text
lsl_{feature}
usl_{feature}
```

However, v0.9 should avoid complicated per-row constraint DSLs.

Recommended constraint warning columns can reuse `candidate_domain_warnings.csv`:

```text
candidate_id
feature
rule
candidate_value
allowed_min
allowed_max
warning_type
severity
message
```

## Ranking Design

Current ranking by predicted target should remain the primary ranking mechanism.

Recommended v0.9 ranking behavior:

- `goal=maximize`: higher predicted target gets lower `screening_rank`.
- `goal=minimize`: lower predicted target gets lower `screening_rank`.
- Preserve `candidate_id`.
- Preserve source metadata columns such as `condition_label` and `note`.
- Add warning summary columns:
  - `warning_count`
  - `has_warning`
  - `max_warning_severity`
  - `prediction_eligible`

Tie handling:

- Use stable sort by predicted target first.
- Break ties by `candidate_id` ascending for deterministic output.
- Do not claim tied candidates are meaningfully different.

Warning handling:

- Do not automatically remove warning candidates from the ranking unless feature values are missing and prediction is impossible.
- Include candidates with OOD warnings in ranking, but clearly mark them.
- In the report, separate:
  - top ranked candidates with no warnings
  - top ranked candidates with warnings
  - excluded candidates

Recommended interpretation:

- Ranking is a candidate screening aid.
- The top row is not a confirmed optimum or validated process condition.

## Report Design

v0.9 should introduce a clearer virtual experiment screening report while keeping existing simulation report compatibility.

Recommended Markdown report sections:

1. Input dataset summary
   - Source file
   - Row count used for modeling
   - Target column
   - Feature columns
   - Candidate source

2. Model validation
   - Model type
   - Train/test metrics
   - Cross-validation metrics
   - Overfitting diagnostics
   - Group-aware validation note when applicable

3. Feature importance
   - Feature summary table
   - Clear note that feature importance is not causal interpretation

4. Candidate screening results
   - Candidate count
   - Valid prediction count
   - Excluded candidate count
   - Warning count
   - Goal direction

5. Top candidate table
   - Top 5 or top 10 ranked candidates
   - Predicted target
   - Warning flags
   - Candidate notes/labels where available

6. Domain/OOD warnings
   - Warning table summary
   - Features most frequently out of training range
   - Candidates excluded due to missing feature values

7. Limitations
   - Data-driven surrogate screening only
   - Not physics simulation
   - Not automatic optimization
   - Not real experiment replacement
   - Sensitive to training data quality and feature coverage

8. Recommended next experiments
   - Review warning-free high-ranked candidates first
   - Compare candidates against domain constraints
   - Use validation experiments before process decisions
   - Expand training data in weak or out-of-range regions

## Implementation Phases

### v0.9.1 Candidate Input Validation and Standardized Prediction Outputs

Goals:

- Introduce standardized `candidate_id`.
- Accept `candidate_id` and preserve `scenario_id` compatibility.
- Add `candidate_conditions.csv`.
- Add `candidate_predictions.csv`.
- Add `candidate_ranking.csv`.
- Keep existing `scenario_predictions.csv`, `scenario_ranking.csv`, and `virtual_experiment_*` files for compatibility.

Suggested tests:

- Candidate CSV missing feature test.
- Candidate CSV non-numeric feature test.
- Candidate ID creation from `candidate_id`, `scenario_id`, or row order.
- Existing scenario behavior unchanged test.

### v0.9.2 OOD / Domain Warning

Goals:

- Add min/max training range checks for candidate rows.
- Save `candidate_domain_warnings.csv`.
- Add per-candidate warning summary columns.
- Keep warning logic simple and transparent.

Suggested tests:

- Candidate below training min emits warning.
- Candidate above training max emits warning.
- Candidate inside training range emits no warning.
- Missing feature value emits error-level warning and is excluded from prediction.

### v0.9.3 Candidate Ranking and Virtual Experiment Report

Goals:

- Add warning-aware ranking output.
- Add deterministic tie handling.
- Add `virtual_experiment_summary.csv`.
- Add `virtual_experiment_report.md` or update report naming while preserving `simulation_report.md`.

Suggested tests:

- Maximize ranking order.
- Minimize ranking order.
- Tie ranking deterministic by candidate ID.
- Ranking includes warning columns.
- Report includes candidate screening, OOD warnings, limitations, and recommended next experiments.

### v0.9.4 Sample Candidate CSV and README Quickstart

Goals:

- Add `data/sample/candidate_conditions.csv`.
- Add a short README quickstart example for candidate screening.
- Keep sample data synthetic/demo only.
- Add one CLI smoke test or documentation check if useful.

Suggested tests:

- Sample candidate CSV can run end-to-end.
- Existing simulation sample commands still work.

## Testing Plan

Add focused tests in `tests/test_simulation.py` or a new `tests/test_virtual_experiment_screening.py`.

Recommended tests:

- Candidate CSV missing feature test.
- Candidate CSV non-numeric feature test.
- Candidate ID normalization test.
- Candidate CSV extra metadata preservation test.
- Ranking maximize test.
- Ranking minimize test.
- Ranking tie handling test.
- OOD warning below training range test.
- OOD warning above training range test.
- Missing candidate value warning and exclusion test.
- Domain warning CSV generation test.
- Candidate warning summary columns in ranking test.
- Virtual experiment summary CSV generation test.
- Markdown report includes candidate screening section.
- Markdown report includes OOD/domain warning section.
- Existing simulation behavior unchanged test.
- Existing scenario output compatibility test.
- Group-aware validation remains unchanged test.

## Non-goals

v0.9 should not implement:

- AutoML
- Bayesian optimization
- Deep learning
- LSTM, Autoencoder, or neural forecasting
- Production decision automation
- Streamlit app
- FastAPI/cloud deployment
- Battery-specific forecasting
- Physics simulation
- Real experiment replacement
- Automatic process condition approval
- Complex uncertainty modeling
- Full rule-engine constraint system

## Command Results

### `python -m pytest`

Result from this design pass:

```text
89 passed in 28.90s
```

### `git status --short`

Status after creating this spec:

```text
?? docs/V0_9_VIRTUAL_EXPERIMENT_SCREENING_SPEC.md
```
