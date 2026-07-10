# Documentation

This directory collects project references, specifications, audits, policies, case-study templates, and archived planning records.

## Current Reference

- [Project Structure](PROJECT_STRUCTURE.md): core platform, case-study utilities, connectors, generated artifacts, and data policy overview.
- [Outputs Policy](OUTPUTS_POLICY.md): how `outputs/` and generated run artifacts should be treated.
- [Testing Guide](../TESTING.md): current test-running notes.

## Active Specifications

- [v0.9 Virtual Experiment Screening Spec](V0_9_VIRTUAL_EXPERIMENT_SCREENING_SPEC.md): simulation-mode screening design and output contract.
- [v1.1 Battery Archive Case Study Spec](V1_1_BATTERY_ARCHIVE_CASE_STUDY_SPEC.md): Battery Archive case-study ingestion plan and historical implementation guide.

## Audit And Reference

- [Repository Root and Architecture Audit](REPOSITORY_ROOT_AND_ARCHITECTURE_AUDIT.md): cleanup recommendations that guided the root documentation cleanup.
- [v1.0 Release Readiness Audit](V1_0_RELEASE_READINESS_AUDIT.md): release-readiness review.
- [Battery Archive Data Audit](BATTERY_ARCHIVE_DATA_AUDIT.md): raw zip inventory and case-study feasibility review.
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

## Images

Static documentation images used by the README and case-study pages live in [docs/images](images/).
