# Outputs Policy

`outputs/` is the analyzer-generated run artifact folder.

It is used by CLI commands such as:

```powershell
python src/process_data.py --mode eda --input data/sample/experiment_process.csv --run-name demo_eda
```

Typical run structure:

```text
outputs/{run_name}/processed/
outputs/{run_name}/figures/
outputs/{run_name}/reports/
```

## Git Policy

`outputs/` should generally not be committed to Git.

Reasons:

- Output folders are regenerable from CLI commands.
- They can grow quickly as demo, smoke, and case-study runs accumulate.
- They may contain local run artifacts that are useful during analysis but not durable source material.
- Committing full run folders can make the repository noisy and harder to review.

The preferred policy is:

- Keep `outputs/` local.
- Commit source code, scripts, tests, and documentation.
- Commit small curated summary files only when they are intentionally part of a documented case study.
- Store durable case-study summaries in `data/processed/` and narrative reports in `data/case_studies/` or `docs/`.
- Do not commit raw datasets, raw archives, full API responses, credentials, temporary outputs, or caches.
- Treat compact inventories and summaries as optional tracked artifacts only when they are reproducible and documented.
- Treat large generated tables as local-only by default unless they are explicitly needed for case-study reproducibility.
- When a tracked processed CSV is refreshed, record the generation command or script and basic row/count validation in the related case-study notes or change summary.

## Kaggle Battery Representative Runs

The Kaggle NASA battery case study references these representative local simulation runs:

```text
kaggle_battery_metadata_only_retention_simulation
kaggle_battery_feature_enriched_retention_simulation
kaggle_battery_metadata_only_group_retention_simulation
kaggle_battery_feature_enriched_group_retention_simulation
kaggle_battery_feature_enriched_no_count_group_retention_simulation
```

These run folders are useful for local traceability, but the default policy is still to avoid committing the full `outputs/` run folders.

Instead, commit curated case-study artifacts such as:

```text
data/processed/kaggle_battery_simulation_comparison.csv
data/case_studies/kaggle_battery/simulation_comparison.md
data/case_studies/kaggle_battery/case_study.md
```

## Restoring Outputs

If outputs are needed again, prefer regenerating them from documented commands rather than committing run folders.

Recommended restoration approach:

1. Keep the input data policy clear: raw data stays local; processed case-study summaries may be committed when small and documented.
2. Re-run the CLI commands or case-study scripts.
3. Compare regenerated reports or summary CSVs against the curated case-study documentation.

Example:

```powershell
python scripts/compare_simulation_runs.py --output data/processed/kaggle_battery_simulation_comparison.csv --report data/case_studies/kaggle_battery/simulation_comparison.md
```

## Local README Note

`outputs/README.md` may exist locally as an in-folder reminder. Because `outputs/` is ignored by Git, that file may not be tracked. This `docs/OUTPUTS_POLICY.md` file is the durable repository-level policy document.
