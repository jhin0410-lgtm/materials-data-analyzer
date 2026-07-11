# Smart Factory Process Quality Case Study

Status: planned / contract stage.

This folder contains the v1.4 Smart Factory process-quality contract artifacts.
It does not contain raw manufacturing data, trained models, or completed Smart
Factory analysis outputs.

## Current Artifacts

- [Process-quality contract](process_quality_contract_v1_4.json): field,
  policy, validation, SPC, capability, provenance, privacy, and stop-condition
  contract.
- [Leakage map](leakage_map_v1_4.csv): post-outcome, future-window,
  group-split, time-split, and hidden-proxy leakage risks.
- [v1.4 plan](../../../docs/SMART_FACTORY_V1_4_PLAN.md): dataset candidate
  comparison, conditional-primary/fallback status, validation hierarchy, and
  roadmap.
- [Acquisition spec](acquisition_spec_v1_4.json): v1.4.2 access gate,
  fallback, checksum, raw-local, and credential policy.
- [Acquisition manifest](acquisition_manifest_v1_4.json): Bosch gate result,
  SECOM fallback provenance, raw-file hashes, row/feature counts, and target
  mapping.

## v1.4.2 Acquisition Gate Result

Bosch Production Line Performance remains `conditional_primary_candidate`.
Kaggle CLI was present locally, but Kaggle credentials were not available, so
Bosch was recorded as `blocked_pending_user_action` with unresolved terms and
no download attempt.

The operational fallback is UCI SECOM. Raw SECOM files are local-only under
`data/raw/smart_factory/secom/`; compact tracked artifacts are:

- `data/case_studies/smart_factory/acquisition_spec_v1_4.json`
- `data/case_studies/smart_factory/acquisition_manifest_v1_4.json`
- `data/processed/smart_factory_v1_4_schema_inventory.csv`
- `data/processed/smart_factory_v1_4_readiness_summary.csv`

## v1.4.3 Normalization and Audit Result

SECOM row alignment is based only on original row position. The analysis-ready
table preserves `sample_index`, raw timestamp string, parsed timestamp,
source-order index, chronological rank, raw target, mapped failure target, and
all 590 process features.

Local-only output:

- `data/processed/smart_factory_v1_4_secom_analysis_ready.csv`

Compact tracked audit candidates:

- `data/case_studies/smart_factory/normalization_spec_v1_4.json`
- `data/processed/smart_factory_v1_4_feature_quality_inventory.csv`
- `data/processed/smart_factory_v1_4_integrity_summary.csv`
- `data/processed/smart_factory_v1_4_missingness_summary.csv`
- `data/processed/smart_factory_v1_4_temporal_summary.csv`
- `data/processed/smart_factory_v1_4_split_feasibility.csv`
- `data/processed/smart_factory_v1_4_spc_feasibility.csv`
- `data/processed/smart_factory_v1_4_analysis_ready_summary.csv`

## Scope

The v1.4.1-v1.4.3 work is limited to dataset assessment, contract design,
leakage mapping, access-gate provenance, SECOM fallback acquisition,
analysis-ready normalization, and compact quality audits. Model training,
dashboards, and production-control claims are out of scope.
