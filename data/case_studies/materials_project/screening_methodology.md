# Materials Project Descriptive Screening Methodology

## Dataset Scope

This pilot uses a local 50-row Materials Project-derived table whose formulas
contain both Fe and Si. The rows are multinary Fe/Si-containing materials; the
dataset is not a binary-only Fe-Si dataset.

The input table for v1.2.3 is:

```text
data/processed/materials_project_normalized.csv
```

The original local source CSV and normalized CSV remain local generated
artifacts. They are not recommended for Git tracking.

## Source Property Type

The source values are Materials Project calculated properties. They are not
direct lab measurements, process measurements, or manufacturing results.

The current query provenance is `reconstructed`. The exact historical retrieval
timestamp, Materials Project API version, and database version are still
unknown.

## Screening Specification

The credential-free screening configuration is:

```text
data/case_studies/materials_project/screening_spec.json
```

The default v1.2.3 pilot uses:

- Filter: `quality_status in ["valid"]`
- Objective: minimize `energy_above_hull_ev_atom`
- Tie policy: `min_rank`
- Missing-value policy: `exclude_from_ranking`
- Top-N summary: 10 candidates

The objective is intentionally narrow. It ranks already available Materials
Project energy-above-hull values as a descriptive stability-proxy screen. It
does not predict new values.

## Scoring And Ranking

For a minimize objective, lower property values receive higher objective scores.
Scores are min-max scaled within the current observed table. Raw property values
and per-objective ranks are preserved in the output.

The composite score is the weighted average of objective scores. In the default
single-objective pilot, the composite score is identical to the
`energy_above_hull_ev_atom` objective score.

Rows that fail filters or have missing objective values are retained in the full
results output but are not assigned a valid overall rank.

## Missing And Tie Handling

Missing objective values are excluded from ranking and are marked with
`screening_status = missing_objective`. Ties use the `min_rank` policy, meaning
tied rows share the same best rank and later ranks may skip numbers.

## Outputs

Full row-level output:

```text
data/processed/materials_project_screening_results.csv
```

Compact top-N output:

```text
data/processed/materials_project_screening_summary.csv
```

The full results file preserves all input rows. Filters do not silently delete
rows; pass/fail state is recorded in `passes_filters` and `filter_status`.

## Interpretation Limits

The v1.2.3 screening output is a descriptive comparison of already available
computed properties. It is not:

- a regression model
- a train/test validated predictor
- a virtual experiment prediction
- proof of synthesizability
- proof of experimental performance
- evidence that this repository discovered new materials

The pilot has only 50 rows, no composition descriptors, no structural descriptor
expansion, and reconstructed provenance. Broader exact-provenance querying and
feature design would be needed before any modeling or generalization claim.

## Reproduction Command

```text
python scripts/run_materials_project_screening.py --input data/processed/materials_project_normalized.csv --screening-spec data/case_studies/materials_project/screening_spec.json --results-output data/processed/materials_project_screening_results.csv --summary-output data/processed/materials_project_screening_summary.csv
```

The command does not call the Materials Project API and does not train a model.

## Tracking Policy

Recommended tracked artifacts:

- `data/case_studies/materials_project/screening_spec.json`
- `data/case_studies/materials_project/screening_methodology.md`
- compact `data/processed/materials_project_screening_summary.csv`, if desired

Recommended local-only artifacts:

- `data/processed/materials_project_fe_si.csv`
- `data/processed/materials_project_normalized.csv`
- `data/processed/materials_project_screening_results.csv`
