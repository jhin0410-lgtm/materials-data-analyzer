# Documentation

This directory collects project references, specifications, audits, policies, case-study templates, and archived planning records.

## Current Reference

- [Project Structure](PROJECT_STRUCTURE.md): core platform, case-study utilities, connectors, generated artifacts, and data policy overview.
- [Outputs Policy](OUTPUTS_POLICY.md): how `outputs/` and generated run artifacts should be treated.
- [Portfolio Overview](PORTFOLIO_OVERVIEW.md): portfolio-oriented summary of architecture, case studies, validation rigor, and limitations.
- [Platform Architecture](PLATFORM_ARCHITECTURE.md): v2 scaffold architecture, registries, config contract, CLI, and backward-compatibility boundary.
- [Case Study Interface](CASE_STUDY_INTERFACE.md): v2.0.4 case-study lifecycle metadata, registry, and current coverage matrix.
- [New Domain Onboarding](NEW_DOMAIN_ONBOARDING.md): metadata-only contract for adding a future dataset/domain without execution.
- [Platform Adapters](PLATFORM_ADAPTERS.md): v2.0.2 thin adapter contract, manifest-only execution boundary, and current adapter matrix.
- [Platform Execution](PLATFORM_EXECUTION.md): v2.0.3 controlled verify runtime, allowlist, side-effect guard, manifest lifecycle, and CLI exit codes.
- [Platform Reporting](PLATFORM_REPORTING.md): v2.0.5 read-only JSON/Markdown platform reports from registries and compact artifacts.
- [Platform Run Registry](PLATFORM_RUN_REGISTRY.md): v2.1 local SQLite manifest/artifact registry, lineage, reproducibility index, diagnostics tables, and CLI.
- [Platform Diagnostics](PLATFORM_DIAGNOSTICS.md): v2.1.2 registry policy diagnostics, evidence-gap analysis, registered claim decisions, and CLI.
- [Testing Guide](../TESTING.md): current test-running notes.

## Active Specifications

- [v0.9 Virtual Experiment Screening Spec](V0_9_VIRTUAL_EXPERIMENT_SCREENING_SPEC.md): simulation-mode screening design and output contract.
- [v1.1 Battery Archive Case Study Spec](V1_1_BATTERY_ARCHIVE_CASE_STUDY_SPEC.md): Battery Archive case-study ingestion plan and historical implementation guide.
- [v1.4 Smart Factory Plan](SMART_FACTORY_V1_4_PLAN.md): process-quality dataset assessment, leakage map, validation hierarchy, SECOM fallback, time-aware baselines, and trust-boundary closeout.

## Audit And Reference

- [Repository Root and Architecture Audit](REPOSITORY_ROOT_AND_ARCHITECTURE_AUDIT.md): cleanup recommendations that guided the root documentation cleanup.
- [v1.0 Release Readiness Audit](V1_0_RELEASE_READINESS_AUDIT.md): release-readiness review.
- [Battery Archive Data Audit](BATTERY_ARCHIVE_DATA_AUDIT.md): raw zip inventory and case-study feasibility review.
- [Materials Project Data Audit](MATERIALS_PROJECT_DATA_AUDIT.md): local 50-row pilot audit, schema/quality follow-up, and descriptive screening notes.
- [Materials Project v1.3 Plan](MATERIALS_PROJECT_V1_3_PLAN.md): exact acquisition, descriptors, group-aware validation, trust-boundary diagnostics, and conservative closeout.
- [Reliability v1.5 Plan](RELIABILITY_V1_5_PLAN.md): generic reliability/risk contract, Backblaze access gate, full-year readiness reassessment, fixed 7-day classification baselines, trust-boundary closeout, leakage map, and validation hierarchy.
- [Platform v2 Plan](PLATFORM_V2_PLAN.md): configuration-driven platform scaffold roadmap.
- [Platform v2.1 Plan](PLATFORM_V2_1_PLAN.md): local persistent registry roadmap.
- [Platform v2 Closeout](PLATFORM_V2_CLOSEOUT.md): v2.0.1-v2.0.5 scaffold summary, current execution boundary, and v2.1 roadmap.
- [v2.0.0 Release Notes](releases/V2_0_0.md): platform core, controlled execution, onboarding metadata, and read-only reporting release notes.
- [v1.5.0 Release Notes](releases/V1_5_0.md): Backblaze reliability validation and trust-boundary release notes.
- [Project Audit](audits/PROJECT_AUDIT.md): earlier project inventory.
- [Commit Boundary Review](audits/COMMIT_BOUNDARY_REVIEW.md): guidance on what should and should not be committed.

## Plans And Archive

- [Cleanup Plan](plans/CLEANUP_PLAN.md): cleanup policy and execution plan.
- [Cleanup Execution Log](archive/cleanup/CLEANUP_EXECUTION_LOG.md): historical cleanup execution record.
- [Staging Plan](archive/cleanup/STAGING_PLAN.md): historical commit staging plan.

## Case Study Documentation

- Repository-level templates and guidance live in [docs/case_studies](case_studies/).
- Data-backed case-study reports and source notes live in [data/case_studies](../data/case_studies/).
- [Kaggle NASA battery case study](../data/case_studies/kaggle_battery/): metadata and raw-discharge feature workflow with simulation comparison.
- [Battery Archive case study](../data/case_studies/battery_archive/): raw zip inventory, cycle-data normalization, quality metrics, threshold proxies, and reliability group summary.
- [Materials Project case study](../data/case_studies/materials_project/): query contract, schema quality audit, descriptive computed-property screening, exact-provenance validation, and trust-boundary closeout.
- [Smart Factory process-quality case study](../data/case_studies/smart_factory/): SECOM fallback provenance, readiness artifacts, time-aware classification baselines, and trust-boundary closeout.
- [Reliability / Backblaze case study](../data/case_studies/reliability/): asset-level reliability/risk contract, leakage map, Backblaze full-year normalization audit, fixed 7-day diagnostic classification baselines, and trust-boundary closeout.

## Images

Static documentation images used by the README and case-study pages live in [docs/images](images/).
