# Case Studies

This folder contains real-data demonstrations for `materials_data_analyzer`.

Case studies are not core analyzer modes. They show how the core platform can be applied to public or properly licensed engineering tabular datasets after source-specific loading, quality review, and analysis-ready table preparation.

## Current Case Studies

### `kaggle_battery/`

Representative real-data case study using the Kaggle NASA battery dataset.

This folder documents:

- Data source and raw-data policy
- Metadata-based discharge cycle summary generation
- Full audit versus analysis-ready filtering
- Raw discharge CSV feature extraction
- Random split versus `battery_id` group split validation
- Simulation comparison results
- Portfolio-style case-study interpretation and limitations

Key files:

```text
data/case_studies/kaggle_battery/README.md
data/case_studies/kaggle_battery/source.md
data/case_studies/kaggle_battery/case_study.md
data/case_studies/kaggle_battery/simulation_comparison.md
```

### `battery_archive/`

Representative real-data case study using Battery Archive cycle-level data.

This folder documents:

- Raw zip inventory without extracting raw archives
- Filename metadata enrichment
- Cycle CSV schema audit and normalization
- Quality flags and conservative capacity-derived metrics
- 80% / 70% threshold crossing proxies and observed-censoring interpretation
- Compact reliability group summary
- Source notes, methodology, and narrative case-study report

Key files:

```text
data/case_studies/battery_archive/README.md
data/case_studies/battery_archive/source.md
data/case_studies/battery_archive/methodology.md
data/case_studies/battery_archive/case_study.md
```

### `materials_project/`

Representative pilot case study using a local Materials Project-derived
computed-property table and a v1.3 exact-provenance validation dataset.

This folder documents:

- Reconstructed query/provenance contract
- Seven-column schema contract and quality audit
- Deterministic descriptive property screening
- Energy-above-hull minimization as a stability-proxy ranking example
- Tied top candidates without arbitrary tie-breaking
- Exact-provenance 838-row validation workflow
- Composition-only descriptors, identifiability audit, and group-aware
  validation
- Applicability-domain diagnostics, error-structure summaries, and
  conservative claim-boundary closeout

Key files:

```text
data/case_studies/materials_project/README.md
data/case_studies/materials_project/source.md
data/case_studies/materials_project/screening_methodology.md
data/case_studies/materials_project/case_study.md
docs/MATERIALS_PROJECT_V1_3_PLAN.md
```

### `smart_factory/`

Representative process-quality case study using UCI SECOM as the operational
fallback after the Bosch access gate was blocked. This is a trust-boundary
case study, not a production Smart Factory model.

This folder documents:

- Process-quality field and policy contract
- Leakage map for post-outcome, future-window, group/time split, and hidden
  proxy risks
- Dataset candidate assessment and SECOM fallback provenance
- Analysis-ready normalization, temporal integrity, and feature-quality audit
- Time-aware classical classification baselines
- Model eligibility, trust boundary, and closeout conclusion

Key files:

```text
data/case_studies/smart_factory/README.md
data/case_studies/smart_factory/case_study.md
data/case_studies/smart_factory/process_quality_contract_v1_4.json
data/case_studies/smart_factory/leakage_map_v1_4.csv
data/case_studies/smart_factory/classification_spec_v1_4.json
data/case_studies/smart_factory/trust_spec_v1_4.json
docs/SMART_FACTORY_V1_4_PLAN.md
```

## Other Source Notes

Other folders may contain source notes or early dataset exploration notes:

```text
data/case_studies/battery/
data/case_studies/htem/
```

Treat these as documentation or optional ingestion references unless they are promoted to full case studies.
