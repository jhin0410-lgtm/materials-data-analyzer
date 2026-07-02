# Case Studies

This folder is reserved for future real-data case study writeups for `materials-data-analyzer`.

No real experimental, process, factory, customer, or production data is included in this repository at this stage. The current project examples use demo/synthetic CSV files under `data/sample/` and `data/raw/` only.

## Proposed Structure

```text
docs/case_studies/
  README.md
  case_study_template.md
  <future_case_study_name>.md
```

Future case studies should be written as Markdown documents. Raw datasets should only be added when they are public, anonymized, and appropriate for GitHub. Private lab, factory, customer, or company data should not be committed.

## Recommended CSV Shape

A useful real-data CSV for this project should contain rows that represent samples, experiments, process runs, inspection lots, or time-series records. Recommended column types include:

- stable identifiers: `sample_id`, `batch_id`, `run_id`, `lot_id`
- process or experiment conditions: temperature, pressure, time, speed, composition, recipe, equipment, operator group
- measured responses: yield, defect rate, thickness, resistance, hardness, capacity, lifetime, reliability cycles
- grouping fields: material, condition group, process step, equipment ID, date or shift
- optional specification limits when SPC or capability-style review is appropriate

Column names should be descriptive, consistent, and free of leading/trailing whitespace. Demo/synthetic CSV files may mimic these patterns, but they should not be described as real experimental evidence.