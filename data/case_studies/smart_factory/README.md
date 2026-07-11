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

## Scope

The v1.4.1 work is limited to dataset assessment, contract design, leakage
mapping, and generic readiness scaffolding. Dataset download, source-specific
loader implementation, model training, dashboards, and production-control
claims are out of scope.
