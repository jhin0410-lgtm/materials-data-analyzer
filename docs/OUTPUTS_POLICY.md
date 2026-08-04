# Outputs Policy

`outputs/` is the analyzer-generated run artifact folder.

For local disk cleanup, cache removal, NASA evidence preservation, and prohibited
broad cleanup commands, also see [Local Workspace Hygiene](WORKSPACE_HYGIENE.md).

The stable user command is:

```powershell
mda --mode eda --input data/sample/experiment_process.csv --run-name demo_eda
```

The historical source-checkout command remains supported:

```powershell
python src/process_data.py --mode eda --input data/sample/experiment_process.csv --run-name demo_eda
```

## Standard Run Structure

```text
outputs/{run_name}/
├── processed/
│   ├── cleaned_data.csv
│   └── preprocessing_audit.json
├── figures/
├── reports/
└── run_manifest.json
```

The preprocessing audit records automatic column-name, dtype, blank-value,
numeric-coercion, missing-value, and empty-row changes. The run manifest records
the input SHA-256, platform version, command options, row counts, overwrite
request, preprocessing audit path, and generated artifact paths.

## No Silent Overwrite

A non-empty run directory is rejected by default. This prevents artifacts from
separate analyses being silently mixed or replaced.

Use one of these approaches:

1. choose a new `--run-name`;
2. archive or remove the old local run deliberately;
3. pass `--overwrite` to replace the entire existing run directory.

`--overwrite` does not merge old and new results. It removes the complete old run
folder and creates a clean replacement. The request is recorded in the new run
manifest.

Case-study and release scripts may impose an even stricter new-or-empty output
policy and may not offer an overwrite option.

## Candidate Screening Outputs

Constraint-aware simulation preserves both original and final candidate views:

```text
candidate_predictions_unconstrained.csv
candidate_ranking_unconstrained.csv
candidate_constraint_audit.csv
candidate_constraint_config_snapshot.json
candidate_eligibility_summary.csv
candidate_predictions.csv
candidate_ranking.csv
```

The `_unconstrained` files preserve the original surrogate output. The final
`candidate_ranking.csv` includes only candidates that pass input validation,
training-domain checks, and any declared allowlisted constraints. Excluded
candidates remain visible in audit and prediction artifacts.

## Git Policy

`outputs/` should generally not be committed to Git.

Reasons:

- output folders are regenerable from commands and tracked inputs;
- they can grow quickly as demo, smoke, and case-study runs accumulate;
- they may contain row-level predictions or local paths;
- committing complete run folders makes review and provenance boundaries less
  clear;
- raw or proprietary source data may be reproduced inside local outputs.

The preferred policy is:

- keep `outputs/` local;
- commit source code, scripts, tests, configuration examples, and documentation;
- commit only small curated summaries intentionally required by a documented
  case study;
- store durable compact summaries in `data/processed/` and narrative closeouts in
  `data/case_studies/` or `docs/`;
- do not commit raw datasets, raw archives, full API responses, credentials,
  temporary outputs, or caches;
- treat row-level predictions and detailed provenance records as local-only by
  default;
- when a tracked processed artifact is refreshed, record the generating command,
  source identity, and basic row/count validation.

## Local Retention Classes

Ignored output is not automatically disposable. Classify each output before
removing it.

### Canonical evidence

A completed, checksum-recorded artifact required for a scientific or software
closeout. Preserve it with its SHA-256 and producing commit, and keep at least one
backup outside the checkout.

The final NASA PCoE post-remediation closed audit ZIP is canonical evidence. The
source archive, retrieval receipt, import output, detailed analysis directory,
and closed ZIP serve different provenance roles and must not be treated as
interchangeable copies.

### Reproducible working output

A detailed local run that can be regenerated from documented source bytes, an
exact commit, configuration, and command. It may be removed after verifying its
compact closeout and regeneration path.

### Temporary output

A smoke run, staging directory, cache, failed partial package, or one-time
repository inventory. It may be removed after confirming no current report or
audit references it.

Use explicit path deletion. Do not use `git clean -fdx` as a workspace-cleanup
shortcut because it removes ignored raw data, local imports, outputs, and virtual
environments.

## Representative Local Runs

The Kaggle NASA Battery case study historically references local simulation runs
such as:

```text
kaggle_battery_metadata_only_retention_simulation
kaggle_battery_feature_enriched_retention_simulation
kaggle_battery_metadata_only_group_retention_simulation
kaggle_battery_feature_enriched_group_retention_simulation
kaggle_battery_feature_enriched_no_count_group_retention_simulation
```

These local folders may support traceability, but they are not durable repository
source material. Prefer curated artifacts such as:

```text
data/processed/kaggle_battery_simulation_comparison.csv
data/case_studies/kaggle_battery/simulation_comparison.md
data/case_studies/kaggle_battery/case_study.md
```

## Restoring Outputs

When outputs are needed again:

1. confirm the correct input source and checksum;
2. install the reviewed software version or use the exact commit;
3. rerun the documented command using a new run name;
4. inspect `preprocessing_audit.json` and `run_manifest.json`;
5. compare regenerated compact outputs against tracked case-study summaries.

Example:

```powershell
python scripts/compare_simulation_runs.py `
  --output data/processed/kaggle_battery_simulation_comparison.csv `
  --report data/case_studies/kaggle_battery/simulation_comparison.md
```

`outputs/README.md` may exist locally as an in-folder reminder. Because
`outputs/` is ignored by Git, this document is the durable repository-level
policy.
