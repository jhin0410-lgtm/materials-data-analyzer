# Processed Artifact Index

`data/processed/` contains tracked compact scientific evidence and selected
case-study tables. Large raw sources, local API responses, row-level predictions,
full structures, detailed NASA imports, and generated run directories remain
local by default.

This index provides family-level navigation. It does not relabel historical
artifacts as current results and does not authorize deletion.

Machine-readable prefix rules are stored in `artifact_catalog.csv`.

## Family Map

| Family | Filename prefix | Scope |
|---|---|---|
| Battery Archive | `battery_archive_` | source inventory, schema mapping, load, quality, series, and reliability-group summaries |
| Battery PGIR and mechanism readiness | `battery_v2_3` | representation coverage, mechanism requirements, identifiability, evaluator execution, and stability summaries |
| Battery forecasting and external evidence | `battery_v2_6` | generalization forecast, failure diagnostics, comparability, cohort admission, provider binding, and evidence-line closeout |
| Kaggle NASA Battery | `kaggle_battery_`, `kaggle_nasa_` | cycle summaries, quality tables, discharge-derived features, analysis-ready tables, and simulation comparison |
| Materials physics | `materials_physics_` | feature definitions, source metadata, coverage, predictive comparison, decision, and report summary |
| Materials Project | `materials_project_` | acquisition, descriptor, screening, applicability, structure, validation, and operator summaries |
| Materials v2.2 closeout | `materials_v2_2_` | capability, evidence, claim, context, uncertainty, and closeout summaries |
| Reliability | `reliability_` | acquisition, readiness, temporal, leakage, classification, trust, and closeout summaries |
| Smart Factory | `smart_factory_` | schema, readiness, missingness, classification, stability, trust, and closeout summaries |
| Platform v2.4 | `v2_4_` | external-source, PGIR reuse, diffusion benchmark, trust, and cross-domain summaries |
| External-source compatibility | `external_source_` | compact compatibility-audit summary |
| Retrieval reproducibility | `retrieval_reproducibility_` | compact exact-byte and metadata evidence summary |

## Interpretation Rules

### Tracked does not mean raw

Most files are compact inventories, summaries, decisions, or claim boundaries.
The corresponding row-level inputs and detailed outputs may be ignored local
artifacts.

### Version labels identify evidence stages

Names such as `v2_3_5` or `v2_6_14` identify a bounded feature or evidence stage.
A higher label does not automatically supersede every earlier artifact. Later
closeouts may depend on exact earlier paths and checksums.

### Negative results are durable evidence

Files recording `Unsupported`, `Inconclusive`, `Diagnostic`, `not_ready`, or
blocked decisions are not cleanup failures. They preserve the tested hypothesis,
validation scope, and reason a stronger claim was rejected.

### Compact evidence is not model deployment material

Tracked summaries do not contain a deployable production model, machine-control
approval, externally validated RUL predictor, or causal mechanism proof unless a
specific document explicitly establishes that narrower claim.

## Local-only Boundaries

The following are intentionally not cataloged as tracked processed artifacts:

```text
data/processed/nasa_pcoe_battery_import/
outputs/
data/raw/
```

The NASA import directory is ignored because it contains large regenerated
row-level artifacts and provenance inputs. It remains important local evidence
for the completed NASA audit and must not be treated as a disposable cache.

## Deletion Policy

Every family rule in `artifact_catalog.csv` currently uses:

```text
retain_pending_reference_audit
```

Before deleting or relocating a tracked processed artifact:

1. search code, tests, docs, manifests, workflows, and release contracts for its
   exact path;
2. identify the producing command and source inputs;
3. determine whether another file is an exact replacement or only a related
   summary;
4. preserve negative and inconclusive scientific conclusions;
5. update checksums, links, tests, and migration documentation in the same
   reviewed change.

Exact duplicate bytes do not by themselves prove that one path is unnecessary.
Two paths may be separate public or release contracts.

## Adding a New Tracked Artifact

A new direct child file in `data/processed/` must:

- match exactly one prefix rule in `artifact_catalog.csv`;
- have a documented producer and source boundary;
- be compact enough for Git review;
- avoid credentials, private paths, raw API bodies, and proprietary data;
- state or inherit a scientific evidence boundary;
- keep row-level or large regenerated data local unless a specific redistribution
  and provenance review authorizes tracking.

When a genuinely new family is added, add one catalog rule and update this index
rather than inventing an ambiguous filename prefix.

## Related Documentation

- [`README.md`](README.md): detailed processed-data policy and family-specific
  artifact descriptions;
- [`../../docs/REPOSITORY_NAVIGATION.md`](../../docs/REPOSITORY_NAVIGATION.md):
  repository-wide entry points and ownership;
- [`../../docs/WORKSPACE_HYGIENE.md`](../../docs/WORKSPACE_HYGIENE.md): local
  cleanup and canonical-evidence preservation;
- [`../../docs/OUTPUTS_POLICY.md`](../../docs/OUTPUTS_POLICY.md): generated output
  retention and Git policy.
