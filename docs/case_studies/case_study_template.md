# Case Study Template

> Status: Template only. Replace placeholder text after a real, public or properly anonymized dataset is available.

## Dataset Description

Describe what each row represents, such as a sample, experiment run, process lot, quality inspection record, reliability test entry, or time-series measurement.

Clarify whether the dataset is real, public, anonymized, internal-only, or demo/synthetic. Do not present demo/synthetic data as real experimental or production data.

## Data Source

- Source:
- Collection period:
- Measurement or process context:
- Public/anonymized status:
- Notes on removed or masked fields:

## Analysis Objective

State the practical review goal without overclaiming the result.

Examples:

- summarize missing values and basic statistics before deeper review
- compare observed target values by material or process condition
- inspect correlations that may be worth engineering follow-up
- screen process logs for simple SPC or 3-sigma review candidates

## Input Columns

| Column | Type | Unit | Description | Required |
| --- | --- | --- | --- | --- |
| `sample_id` | categorical | - | Stable sample or run identifier | Recommended |
| `material` | categorical | - | Material or condition group | Recommended |
| `process_temperature_c` | numeric | degC | Example process condition | Optional |
| `process_time_min` | numeric | min | Example process condition | Optional |
| `measurement_date` | datetime-like | - | Measurement or run date | Optional |
| `target_metric` | numeric | define unit | Main response variable for review | Recommended |

Add or remove rows to match the real dataset. Keep engineering units explicit where possible.

## Commands Used

```bash
python src/process_data.py --mode eda --input <path-to-real-or-anonymized-csv> --run-name <case-study-name>
```

```bash
python src/process_data.py --mode process --input <path-to-real-or-anonymized-csv> --target <target_column> --goal maximize --run-name <case-study-name>
```

Only include commands that were actually run for the case study.

## Generated Outputs

List generated files from `outputs/<run_name>/`, such as:

- cleaned CSV:
- summary tables:
- figures:
- Markdown report:

If representative images are copied into `docs/images/` or this case study folder, state that they are derived from the documented dataset and whether the source data is real, anonymized, or demo/synthetic.

## Engineering Interpretation

Summarize observations cautiously. Distinguish between:

- descriptive statistics from the CSV
- correlations or group differences that need follow-up
- engineering conclusions that require domain review, experimental context, or additional measurements

Avoid claiming process optimization, causation, root cause, or validated performance improvement unless those claims are supported by the dataset and study design.

## Limitations

Document constraints such as:

- dataset size and sampling bias
- missing values or inconsistent columns
- lack of measurement uncertainty or calibration metadata
- demo/synthetic data limitations, if applicable
- whether specification limits were available for SPC or capability-style review
- why results should be treated as analysis support rather than automatic engineering decisions