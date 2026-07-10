# Materials Project Data Audit

Scope: v1.2 Materials Project Property Screening Case Study initial data and
implementation audit only. No API call was made, no source code was changed, no
CSV was modified, and no README/CHANGELOG/repository structure changes were
made.

## Executive Summary

- Current checked branch during this audit: `main`.
- User-provided expected branch: `feature/v1.2-materials-project`.
- Local processed artifact exists:
  `data/processed/materials_project_fe_si.csv`.
- The local CSV is ignored via `.git/info/exclude` and is not tracked by Git.
- The current CSV has 50 rows and 7 columns.
- The file name suggests an Fe-Si pilot, but the actual formulas are not only
  binary Fe-Si. All rows contain Fe and Si, while all rows also contain at least
  one additional element.
- The connector is a small working API probe when `MP_API_KEY` and `mp-api` are
  available. Tests do not call the real API.
- Recommended immediate next step: rebuild v1.2 around a query contract and
  provenance manifest before adding analysis/modeling.

## Files Inspected

- `src/connectors/materials_project_connector.py`
- `tests/test_materials_project_connector.py`
- `scripts/ingest_data.py`
- `data/processed/materials_project_fe_si.csv`
- `data/processed/README.md`
- `data/case_studies/materials_project/source.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/OUTPUTS_POLICY.md`
- `README.md`
- `src/dataset_registry.py`
- `src/schema_mapping.py`
- `src/data_validation.py`
- `configs/data_sources.example.yaml`
- Git tracked/ignored Materials Project-related paths

Sensitive config values were not printed or copied. Only file names and
non-secret configuration keys were inspected.

## 1. Current Implementation Audit

### Connector Status

`src/connectors/materials_project_connector.py` is more than a placeholder, but
it is still a small probe connector rather than a production ingestion layer.

Current behavior:

- Connector class: `MaterialsProjectConnector`
- Default query elements: `["Fe", "Si"]`
- API key source: environment variable `MP_API_KEY`
- API package: `mp_api.client.MPRester`
- Query endpoint used in code: `mpr.materials.summary.search(...)`
- Query fields:
  - `material_id`
  - `formula_pretty`
  - `band_gap`
  - `formation_energy_per_atom`
  - `energy_above_hull`
  - `density`
  - `volume`
- Query options:
  - `elements=self.elements`
  - `fields=MP_FIELDS`
  - `num_chunks=1`
  - `chunk_size=query_limit`
- `limit` default from ingestion CLI: 50
- `full=True` currently sets `query_limit = max(limit, 50)`; it does not
  implement true pagination over all matching records.
- Raw output path:
  `data/raw/materials_project/mp_fe_si_raw.json`
- Processed output path:
  `data/processed/materials_project_fe_si.csv`

### Output DataFrame Schema

`build_materials_project_dataframe(...)` maps returned documents to:

| Output column | Source field |
| --- | --- |
| `material_id` | `material_id` |
| `formula` | `formula_pretty` |
| `band_gap_ev` | `band_gap` |
| `formation_energy_ev_atom` | `formation_energy_per_atom` |
| `energy_above_hull_ev_atom` | `energy_above_hull` |
| `density_g_cm3` | `density` |
| `volume_a3` | `volume` |

### Error And Credential Handling

- Missing `MP_API_KEY` raises a `RuntimeError`.
- Missing `mp-api` raises a `RuntimeError` with installation guidance.
- API keys are read only from the environment.
- No API key is stored in the connector, tests, or source notes.
- No retry/backoff behavior is implemented.
- No explicit API schema version or retrieval timestamp is written.

### Test Coverage

`tests/test_materials_project_connector.py` covers:

- Missing `MP_API_KEY` behavior.
- Fake document conversion to the processed DataFrame schema.

It does not cover:

- Real Materials Project API smoke.
- Pagination.
- Retry/error handling.
- API schema drift.
- Provenance manifest creation.
- Data quality checks on retrieved CSVs.

### Connector vs Actual API

The connector can perform a real API call if credentials and `mp-api` are
installed. This audit did not call the API. The current implementation should be
treated as a probe connector, not a hardened ingestion workflow.

## 2. Local Dataset Audit

Local processed file:

```text
data/processed/materials_project_fe_si.csv
```

File status:

- Exists: yes
- Size: 5,414 bytes
- Git tracked: no
- Ignored by: `.git/info/exclude`
- Row count: 50
- Column count: 7
- Duplicate rows: 0
- Duplicate `material_id`: 0
- Unique materials: 50
- Path-like string cells: 0
- Credential-like string cells: 0

### Columns And Dtypes

| Column | Inferred dtype | Null count | Null percent |
| --- | --- | ---: | ---: |
| `material_id` | `str` | 0 | 0.0 |
| `formula` | `str` | 0 | 0.0 |
| `band_gap_ev` | `float64` | 0 | 0.0 |
| `formation_energy_ev_atom` | `float64` | 0 | 0.0 |
| `energy_above_hull_ev_atom` | `float64` | 0 | 0.0 |
| `density_g_cm3` | `float64` | 0 | 0.0 |
| `volume_a3` | `float64` | 0 | 0.0 |

### Numeric Ranges

| Column | Non-null | Unique | Min | Median | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| `band_gap_ev` | 50 | 27 | 0.0 | 0.23195 | 3.4775 |
| `formation_energy_ev_atom` | 50 | 50 | -3.22721 | -2.46284 | 2.67125 |
| `energy_above_hull_ev_atom` | 50 | 44 | 0.0 | 0.05704 | 5.53862 |
| `density_g_cm3` | 50 | 50 | 2.14571 | 2.92928 | 10.42051 |
| `volume_a3` | 50 | 50 | 42.67003 | 316.96137 | 2110.21932 |

Additional numeric checks:

- `energy_above_hull_ev_atom == 0`: 7 rows
- `energy_above_hull_ev_atom <= 0.05`: 20 rows
- `energy_above_hull_ev_atom <= 0.10`: 40 rows
- `band_gap_ev == 0`: 24 rows
- `band_gap_ev > 0`: 26 rows

### Categorical Summary

`material_id`:

- Non-null: 50
- Unique: 50
- No duplicate material IDs.

`formula`:

- Non-null: 50
- Unique formulas: 35
- Duplicate formula rows: 15
- Formulas with multiple structures in this sample:
  - `LiFeSiO4`: 8
  - `LiFe(SiO3)2`: 4
  - `Li2FeSi3O8`: 3
  - `Li2Fe(SiO3)2`: 2
  - `CeFeSi2`: 2
  - `Mg6FeSiO8`: 2

No constant or near-constant columns were detected in the 50-row sample.

## 3. Dataset Scope Check

The local CSV should not be described as a binary Fe-Si dataset.

Observed facts:

- All 50 formulas contain Fe and Si.
- All 50 formulas also include at least one additional element.
- Inferred chemical systems include examples such as:
  - `Fe-Li-O-Si`
  - `Fe-O-Si`
  - `Ce-Fe-Si`
  - `Fe-Si-Ti`
  - `Fe-Mg-O-Si`
  - `B-Fe-Li-O-Si`
  - `C-Fe-Na-O-Si`
- The local CSV has no `chemical_system` column, so this was inferred from
  formula strings only.
- The local CSV has no crystal system, space group, structure, deprecated,
  theoretical/experimental, API version, or retrieval timestamp columns.
- Same formula can appear multiple times, likely reflecting multiple
  structures/polymorphs or distinct Materials Project entries.
- Same `material_id` is not duplicated.

Stability/metastability can only be approximated from
`energy_above_hull_ev_atom`; there is no explicit stability label.

## 4. Property And Feature Inventory

### Identifiers

- `material_id`: identifier only. Do not use as a predictive feature.
- `formula`: identifier/composition label. Useful for grouping and audit, but
  high leakage/categorical risk if used directly.

### Provenance

No provenance fields are present in the processed CSV. Missing:

- retrieval timestamp
- API version
- query specification
- returned field list
- license/terms confirmation
- Materials Project database version

### Composition Features

Current processed CSV has no numeric composition features such as elemental
fractions, number of elements, or reduced formula groups. `formula` is present
but not yet featurized.

### Structure Features

No structure features are present. Missing:

- crystal system
- space group
- lattice parameters
- number of sites
- dimensionality

`volume_a3` is present, but without number of sites it may not be comparable
across formulas.

### Thermodynamic Properties

- `formation_energy_ev_atom`
- `energy_above_hull_ev_atom`

These are strong candidate analysis targets or descriptors, but they can be
directly related to stability labels and must be handled carefully.

### Electronic Properties

- `band_gap_ev`

Candidate target for electronic property screening.

### Mechanical Properties

None present.

### Magnetic Properties

None present.

### Categorical Metadata

Only `formula` is present. No explicit chemical system, crystal system, or space
group columns.

### Unusable Or Ambiguous Columns

- `material_id`: identifier only.
- `formula`: grouping/feature-engineering source, but not safe as a raw
  categorical feature without careful validation.
- `volume_a3`: usable for descriptive analysis, but ambiguous as a predictive
  feature without normalization by cell size or sites.

## 5. Target Candidate Inventory

Only columns that actually exist in the local CSV are listed here.

| Target candidate | Non-null | Unique | Range | Screening value | Leakage risk | Recommendation |
| --- | ---: | ---: | --- | --- | --- | --- |
| `band_gap_ev` | 50 | 27 | 0.0 to 3.4775 | Candidate for electronic property screening | Moderate; avoid formula/material_id leakage | Best pilot target if sample size is accepted |
| `formation_energy_ev_atom` | 50 | 50 | -3.22721 to 2.67125 | Thermodynamic trend analysis | High if paired with hull/stability-derived features | Use carefully; not with `energy_above_hull_ev_atom` as feature for stability-like tasks |
| `energy_above_hull_ev_atom` | 50 | 44 | 0.0 to 5.53862 | Stability proxy screening | High; direct stability proxy | Good descriptive target, but avoid calling it validated stability prediction |
| `density_g_cm3` | 50 | 50 | 2.14571 to 10.42051 | Density comparison | Moderate; structure/composition dependent | Descriptive screening only |
| `volume_a3` | 50 | 50 | 42.67003 to 2110.21932 | Structure-size comparison | High ambiguity without sites | Do not use as main target until normalized |

Not available in this CSV:

- `bulk_modulus`
- `shear_modulus`
- magnetization
- crystal system
- space group
- composition fractions

## 6. Leakage And Scientific Validity Audit

### Safe Features

In the current CSV, there are very few clearly safe features for prediction.
For a band-gap pilot, possible numeric descriptors might include:

- `density_g_cm3`
- maybe `formation_energy_ev_atom`
- maybe `energy_above_hull_ev_atom`

These are not universally safe; they are computed Materials Project properties
and may reflect shared calculation pipelines.

### Conditional Features

- `formation_energy_ev_atom`: conditional. Useful descriptor for some
  property-screening analyses, but likely too close to thermodynamic stability
  targets.
- `energy_above_hull_ev_atom`: conditional. Safe only when it is not the target
  and not being used to predict a stability class derived from itself.
- `density_g_cm3`: conditional. Requires awareness that it depends on structure.
- `volume_a3`: conditional/ambiguous. Should be normalized before serious use.
- `formula`: conditional. Use for grouping or derived composition features,
  not as a raw high-cardinality categorical input in a small dataset.

### Leakage Candidates

- `energy_above_hull_ev_atom` for any stability or stable/metastable target.
- `formation_energy_ev_atom` for stability-like targets.
- `material_id` for any predictive task.
- `formula` if random split allows same formula family in train and test.
- `volume_a3` if target or features are structure-size coupled and not
  normalized.

### Identifier Only

- `material_id`

### Unavailable For Prediction-Time Use

No real prediction-time feature contract exists yet. A future case study should
define which properties are known before screening and which are post-computed
Materials Project outputs.

## 7. Case-study Positioning

Recommended positioning:

> Materials Project property tabular screening case study.

This should be framed as analysis of computed Materials Project tabular
properties, not as:

- direct DFT simulation performed by this project
- discovery of new materials
- experimentally validated material performance
- manufacturing feasibility proof
- production decision automation

The case study complements Battery Archive by covering a different domain:

- Battery Archive: cycle-level degradation/reliability proxy workflow
- Materials Project: computed materials-property screening workflow

## 8. Candidate Screening Use Cases

### Use Case A: Band Gap Screening Pilot

- Target: `band_gap_ev`
- Candidate features: `density_g_cm3`, `formation_energy_ev_atom`,
  `energy_above_hull_ev_atom`; future derived composition features
- Categorical handling: formula should be grouped or featurized, not used raw
  in this 50-row sample
- Group-aware validation: needed by formula or composition family
- Expected sample size: 50 rows currently
- Limitation: small sample, many related formulas, computed properties only
- Virtual experiment connection: possible later as a screening demo, but not
  ready without feature contract and group validation

### Use Case B: Stability Proxy Screening

- Target: `energy_above_hull_ev_atom`
- Candidate features: composition-derived features, density, possibly band gap
- Categorical handling: formula family grouping required
- Group-aware validation: formula or composition-family split
- Expected sample size: 50 rows
- Limitation: `energy_above_hull_ev_atom` is directly the stability proxy; avoid
  circular labels/features
- Virtual experiment connection: possible for ranking candidates by low hull
  energy, but should not be described as stability proof

### Use Case C: Density Or Volume Comparison

- Target: `density_g_cm3` or normalized structure-size metric
- Candidate features: composition-derived features
- Categorical handling: chemical system and formula grouping required
- Group-aware validation: formula family split
- Expected sample size: 50 rows
- Limitation: `volume_a3` is not normalized by sites and may not be comparable
- Virtual experiment connection: limited until structural descriptors are added

### Use Case D: Fe/Si-Containing Composition Trend Analysis

- Target: any available property
- Candidate features: derived composition fractions and formula-family groups
- Categorical handling: required
- Group-aware validation: required
- Expected sample size: 50 rows
- Limitation: local data is Fe/Si-containing, not binary Fe-Si
- Virtual experiment connection: feasible after a composition feature table is
  created

Mechanical property screening is not supported by the current CSV because no
mechanical property columns are present.

## 9. Grouping And Validation Strategy

Random split alone can overstate performance because related formulas and
polymorphs can appear in both train and test sets.

Potential grouping keys:

- `formula`
- reduced formula or formula family
- inferred chemical system
- composition-family cluster from derived elemental fractions
- future `space_group` or `crystal_system`
- `material_id` should not be used as a feature; it may be used only for
  row-level uniqueness checks

Recommended validation comparisons for future modeling:

1. Random split as a baseline only.
2. Formula group split to test generalization across repeated formulas.
3. Composition-family group split after composition features are created.

No model should be run in this audit phase.

## 10. Data Quality Risks

Observed or likely risks from the current local CSV:

- Small sample size: 50 rows.
- No missing values in current columns, but the schema is narrow.
- Same formula appears multiple times.
- Many formulas are multi-element compounds, not binary Fe-Si.
- No explicit provenance timestamp or API version.
- No explicit Materials Project database version.
- No experimental/theoretical marker in the processed CSV.
- No crystal system or space group.
- No units metadata beyond column names.
- `energy_above_hull_ev_atom` has large outliers up to 5.53862 eV/atom.
- `band_gap_ev` has 24 zero values and 26 positive values.
- Query selection bias: default query is element containment, not a clean
  chemical-system boundary.
- API schema drift is possible because `mp-api` return schemas can change.

## 11. Reproducibility And Artifact Policy

Current local artifact policy:

- `data/processed/materials_project_fe_si.csv` is ignored via
  `.git/info/exclude`.
- `data/raw/materials_project/mp_fe_si_raw.json` is ignored by `data/raw/**`.
- `configs/` is ignored via `.git/info/exclude`.
- `configs/data_sources.example.yaml` exists locally and references environment
  variable names only; no secret values were copied into this audit.

Recommendation:

- Do not commit the current CSV yet.
- Treat it as a local API-derived artifact until provenance is recorded.
- Track compact, sanitized reproducibility artifacts instead:
  - query manifest
  - returned field list
  - retrieval timestamp
  - row/column summary
  - data-quality summary
  - compact case-study summary
- Never include API keys or credentials in artifacts.

## 12. Proposed v1.2 Output Contract

Proposed files and tracking policy:

| File | Purpose | Tracking recommendation |
| --- | --- | --- |
| `data/processed/materials_project_query_manifest.json` | Query parameters, fields, retrieval timestamp, package/API notes | tracked compact artifact |
| `data/processed/materials_project_property_inventory.csv` | Column inventory, nulls, dtypes, ranges | tracked compact artifact |
| `data/processed/materials_project_quality_summary.csv` | Data quality and scope summary | tracked compact artifact |
| `data/processed/materials_project_analysis_ready.csv` | Main property table after normalization/feature prep | local generated artifact until policy is decided |
| `data/processed/materials_project_screening_summary.csv` | Compact screening result summary | tracked compact artifact if small |
| `data/case_studies/materials_project/README.md` | Case-study navigation | tracked documentation |
| `data/case_studies/materials_project/case_study.md` | Narrative report | tracked documentation |
| `data/case_studies/materials_project/source.md` | Source, terms, provenance notes | tracked documentation |

The existing `materials_project_fe_si.csv` overlaps with a future analysis-ready
table, but it lacks provenance. Do not add a duplicate output until the query
contract is defined.

## 13. Connector vs Loader Responsibility

Recommended boundaries:

- Connector:
  - Materials Project API access
  - credential lookup from environment only
  - raw document retrieval
  - raw/local output paths
- Loader:
  - returned table validation
  - schema normalization
  - provenance checks
  - Materials Project-specific data quality summaries
- Preprocessing/features:
  - composition parsing
  - elemental fractions
  - formula-family grouping
  - optional structural feature preparation if structure fields are retrieved
- Analyzer:
  - generic EDA, reliability/process-style summaries, simulation/screening
  - no Materials Project-specific logic in analyzer core
- Script:
  - reproducible workflow orchestration
  - query manifest writing
  - report artifact creation

This follows the structure freeze used during Battery Archive v1.1.

## 14. Proposed Implementation Phases

### v1.2.1 Query Contract, Provenance, Connector Hardening

- Goal: define and save query manifest before data use.
- Expected files:
  - `src/connectors/materials_project_connector.py`
  - `scripts/ingest_data.py` or new Materials Project workflow script
  - `data/processed/materials_project_query_manifest.json`
- Outputs:
  - manifest with elements/fields/limit/timestamp/package notes
  - no credentials
- Tests:
  - manifest creation with fake inputs
  - missing API key remains safe
  - no credential serialization
- Stop condition:
  - API terms or credentials unclear

### v1.2.2 Schema Normalization And Data-quality Summary

- Goal: validate processed CSV and create compact data-quality artifacts.
- Expected files:
  - new loader or utility under `src/loaders/`
  - workflow script under `scripts/`
- Outputs:
  - `materials_project_property_inventory.csv`
  - `materials_project_quality_summary.csv`
- Tests:
  - local fake DataFrame quality summary
  - duplicate material ID detection
  - missing provenance detection
- Stop condition:
  - local CSV provenance remains unclear

### v1.2.3 Materials-property Analysis-ready Table

- Goal: create a documented analysis-ready property table.
- Expected files:
  - Materials Project loader/feature helper
  - case-study docs
- Outputs:
  - `materials_project_analysis_ready.csv`
- Tests:
  - formula parsing
  - Fe/Si-containing vs binary Fe-Si scope flags
  - no overwrite of local source artifact
- Stop condition:
  - sample too small or target not viable

### v1.2.4 Property Screening And Validation Comparison

- Goal: run only well-scoped screening after feature/target contract exists.
- Expected files:
  - script for screening workflow
  - compact summary artifact
- Outputs:
  - `materials_project_screening_summary.csv`
  - optional analyzer outputs under `outputs/`
- Tests:
  - group-aware split configuration if modeling is used
  - leakage exclusions
- Stop condition:
  - no safe target/feature set

### v1.2.5 Case-study Documentation And Release Closeout

- Goal: document source, methodology, limitations, and results.
- Expected files:
  - `data/case_studies/materials_project/README.md`
  - `data/case_studies/materials_project/case_study.md`
  - updated source notes
- Outputs:
  - compact report and artifact list
- Tests:
  - Markdown section checks
  - link checks
- Stop condition:
  - source/terms/citation unresolved

## 15. Stop Conditions

Implementation should pause for user confirmation if:

- API credential is required and unavailable.
- Materials Project API terms/citation requirements are not confirmed.
- Local CSV provenance remains unclear.
- Dataset has too few rows for the intended screening use case.
- No target candidate is viable.
- Units or field meanings are unclear.
- Query filter is too broad or too biased for the desired case-study claim.
- Dataset must be re-downloaded.
- Existing local CSV must be deleted or replaced.
- A feature would require adding Materials Project-specific logic to analyzer
  core.

## 16. Recommended Immediate Next Step

Recommended path:

> Start with v1.2.1: query contract, provenance, and connector hardening.

Reasoning:

- The current local CSV is usable for audit, but lacks retrieval timestamp,
  API/package provenance, explicit query manifest, and version notes.
- The file name is misleading if interpreted as binary Fe-Si.
- A case study based on the existing CSV alone would be fragile.
- Re-querying may be necessary later, but first the project should define the
  manifest and artifact contract.

Fallback if API access is unavailable:

> Proceed as a small local Fe/Si-containing pilot only, clearly marking the CSV
> as a local ignored artifact with incomplete provenance.

## 17. Non-goals For This Audit

This audit did not:

- call the Materials Project API
- download data
- modify source code
- modify CSV files
- perform feature engineering
- train a model
- run simulation
- update README or CHANGELOG
- restructure the repository
- commit or push changes
- modify Battery Archive outputs
- integrate NLR or other data sources

## Validation Results

- Full pytest command:
  `powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1`
- Result: 140 passed.
- Local Materials Project processed artifact:
  `data/processed/materials_project_fe_si.csv` exists.
- Local raw Materials Project artifact:
  `data/raw/materials_project/mp_fe_si_raw.json` exists.
- Audit row/column count: 50 rows, 7 columns.
- Recommended pilot target: `band_gap_ev`, if group-aware validation and
  leakage controls are added later.
- Recommended immediate next phase: v1.2.1 query contract, provenance, and
  connector hardening.
- Generated file: `docs/MATERIALS_PROJECT_DATA_AUDIT.md`.

Final `git status --short` after this audit is expected to show only this new
documentation file:

```text
?? docs/MATERIALS_PROJECT_DATA_AUDIT.md
```
