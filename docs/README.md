# Documentation

This directory collects project references, specifications, audits, policies, case-study templates, and archived planning records.

## Current Reference

- [Project Structure](PROJECT_STRUCTURE.md): core platform, case-study utilities, connectors, generated artifacts, and data policy overview.
- [Outputs Policy](OUTPUTS_POLICY.md): how `outputs/` and generated run artifacts should be treated.
- [Portfolio Overview](PORTFOLIO_OVERVIEW.md): portfolio-oriented summary of architecture, case studies, validation rigor, and limitations.
- [Platform Architecture](PLATFORM_ARCHITECTURE.md): v2 scaffold architecture, registries, config contract, CLI, and backward-compatibility boundary.
- [PGIR Architecture](PGIR_ARCHITECTURE.md): v2.3 representation governance, canonical concepts, maturity levels, operator taxonomy, and non-goals.
- [PGIR Conformance Gates](PGIR_CONFORMANCE_GATES.md): v2.3.2 representation declaration, maturity, context, transition, and capability gates.
- [PGIR Model Contract](PGIR_MODEL_CONTRACT.md): strict v2.4.2 contract for one bounded executable physical benchmark.
- [1D Diffusion Analytical Benchmark](DIFFUSION_1D_ANALYTICAL_BENCHMARK.md): exact problem, canonical FTCS result, and predeclared refinement evidence.
- [Physical Propagator Validation](PHYSICAL_PROPAGATOR_VALIDATION.md): operator, stability, lineage, maturity, and validation gates.
- [v2.4 Diffusion Scientific Boundary](V2_4_DIFFUSION_SCIENTIFIC_BOUNDARY.md): supported evidence and prohibited physical claims.
- [PGIR Current Architecture Audit](PGIR_CURRENT_ARCHITECTURE_AUDIT.md): current scientific records mapped to PGIR concepts.
- [Platform v2.3 Roadmap](PLATFORM_V2_3_ROADMAP.md): staged PGIR-to-dynamic-physics roadmap without solver or model claims in v2.3.1.
- [External Source Current Architecture Audit](EXTERNAL_SOURCE_CURRENT_ARCHITECTURE_AUDIT.md): pre-v2.4 source, snapshot, checksum, authentication, and lineage audit.
- [External Source Metadata Contract](EXTERNAL_SOURCE_METADATA_CONTRACT.md): v2.4.1 versioned source-system, dataset, snapshot, distribution, and retrieval contract.
- [External Source Provenance Levels](EXTERNAL_SOURCE_PROVENANCE_LEVELS.md): evidence-bearing status taxonomy without a global trust score.
- [Materials Structure PGIR Reuse](MATERIALS_STRUCTURE_PGIR_REUSE.md): actual 838-entity second-domain declaration and conformance audit.
- [Cross-Domain PGIR Reuse Evidence](CROSS_DOMAIN_PGIR_REUSE_EVIDENCE.md): shared framework and domain-semantic boundaries.
- [NIST, NREL, and NVD Source Boundaries](NIST_NREL_NVD_SOURCE_BOUNDARIES.md): future routing declarations with no integration claim.
- [Platform v2.4 Roadmap](PLATFORM_V2_4_ROADMAP.md): provenance and cross-domain governance roadmap.
- [Battery PGIR Mapping](BATTERY_PGIR_MAPPING.md): mapping existing battery cycle summaries to Observation, operational State, and Trajectory metadata.
- [Battery Observation, State, and Trajectory](BATTERY_OBSERVATION_STATE_TRAJECTORY.md): representation boundary for cycle observations, operational state summaries, and trajectories.
- [Battery Mechanism Readiness](BATTERY_MECHANISM_READINESS.md): requirements-only mechanism readiness audit for Arrhenius, diffusion, and empirical trajectory contexts.
- [Battery Mechanism Data Sufficiency Audit](BATTERY_MECHANISM_DATA_SUFFICIENCY_AUDIT.md): v2.3.3 actual Battery coverage for mechanism requirements.
- [Battery Mechanism Candidates](BATTERY_MECHANISM_CANDIDATES.md): metadata-only mechanism-candidate registry and prohibited interpretations.
- [Battery Identifiability Audit](BATTERY_IDENTIFIABILITY_AUDIT.md): structural, practical, and contextual identifiability results.
- [Battery Protocol and Condition Comparability](BATTERY_PROTOCOL_AND_CONDITION_COMPARABILITY.md): protocol metadata and temperature-condition limits.
- [Battery Mechanism Evidence Gaps](BATTERY_MECHANISM_EVIDENCE_GAPS.md): missing evidence and prohibited workarounds.
- [Battery v2.3.3 Operator Selection](BATTERY_V2_3_3_OPERATOR_SELECTION.md): selected descriptive evaluator and blocked mechanism claims.
- [Battery Capacity-Trajectory Evaluator](BATTERY_CAPACITY_TRAJECTORY_EVALUATOR.md): actual v2.3.4 bounded execution and aggregate findings.
- [Battery Trajectory Findings and Thresholds](BATTERY_TRAJECTORY_FINDINGS_AND_THRESHOLDS.md): fixed gap-aware detection policy and interpretation limits.
- [Battery Trajectory Evaluator Trust](BATTERY_TRAJECTORY_EVALUATOR_TRUST.md): representation, execution, interpretation, and external-validity boundaries.
- [Battery v2.3.4 Scientific Boundary](BATTERY_V2_3_4_SCIENTIFIC_BOUNDARY.md): allowed and prohibited claims after execution.
- [Battery Source-Metadata Recovery](BATTERY_SOURCE_METADATA_RECOVERY.md): v2.3.5 exact local lineage, recovered source evidence, and unresolved metadata.
- [Battery Evaluator Stability Audit](BATTERY_EVALUATOR_STABILITY_AUDIT.md): predeclared threshold, reference, window, and gap sensitivity with bounded event consolidation.
- [Battery v2.3.5 Scientific Boundary](BATTERY_V2_3_5_SCIENTIFIC_BOUNDARY.md): allowed claims and mechanism/prediction limits after the stability audit.
- [Battery v2.3 Data and Representation Audit](BATTERY_V2_3_DATA_AND_REPRESENTATION_AUDIT.md): actual processed battery coverage and tracked/local output policy for the v2.3.2 pilot.
- [Case Study Interface](CASE_STUDY_INTERFACE.md): v2.0.4 case-study lifecycle metadata, registry, and current coverage matrix.
- [New Domain Onboarding](NEW_DOMAIN_ONBOARDING.md): metadata-only contract for adding a future dataset/domain without execution.
- [Platform Adapters](PLATFORM_ADAPTERS.md): v2.0.2 thin adapter contract, manifest-only execution boundary, and current adapter matrix.
- [Platform Execution](PLATFORM_EXECUTION.md): v2.0.3 controlled verify runtime, allowlist, side-effect guard, manifest lifecycle, and CLI exit codes.
- [Platform Reporting](PLATFORM_REPORTING.md): v2.0.5 read-only JSON/Markdown platform reports from registries and compact artifacts.
- [Platform Run Registry](PLATFORM_RUN_REGISTRY.md): v2.1 local SQLite manifest/artifact registry, lineage, reproducibility index, diagnostics tables, and CLI.
- [Platform Diagnostics](PLATFORM_DIAGNOSTICS.md): v2.1.2 registry policy diagnostics, evidence-gap analysis, registered claim decisions, and CLI.
- [Scientific Constraints](SCIENTIFIC_CONSTRAINTS.md): v2.1 unit-aware scientific constraint registry, safe evaluator boundary, XRD example, and CLI.
- [Scientific Execution](SCIENTIFIC_EXECUTION.md): v2.1 bounded scalar/small-list scientific execution, finding persistence, trust closeout, and local-only outputs.
- [Scientific Entity Model](SCIENTIFIC_ENTITY_MODEL.md): v2.2.2 JSON-safe entity records, runtime/persistence separation, and initial entity types.
- [Materials Prediction Contexts](MATERIALS_PREDICTION_CONTEXTS.md): separation between composition-only pre-structure screening and known-structure post-relaxation analysis.
- [Materials Known-Structure Prediction Context](MATERIALS_KNOWN_STRUCTURE_PREDICTION_CONTEXT.md): v2.2.5 known-structure post-relaxation claim boundary and target-source separation.
- [Scientific Quantities and Uncertainty](SCIENTIFIC_QUANTITIES_AND_UNCERTAINTY.md): structured quantities, original/canonical units, and bounded uncertainty semantics.
- [Crystal Structure Entity Adapter](CRYSTAL_STRUCTURE_ENTITY_ADAPTER.md): Materials Project structure-to-entity mapping, actual v2.2.4 conversion coverage, validation boundary, quantity mapping, and uncertainty policy.
- [Scientific Operator Registry](SCIENTIFIC_OPERATOR_REGISTRY.md): v2.2.4 selected metadata-only scientific operators for entity conversion, descriptors, graph artifacts, and execution boundary.
- [Materials Structure Enrichment](MATERIALS_STRUCTURE_ENRICHMENT.md): v2.2.4 existing-ID structure acquisition, snapshot alignment, conversion coverage, and local-only policy.
- [Materials Structure Descriptors](MATERIALS_STRUCTURE_DESCRIPTORS.md): Tier-1 known-structure descriptor definitions, coverage, and invariance boundary.
- [Periodic Crystal Graph Artifacts](PERIODIC_CRYSTAL_GRAPH_ARTIFACTS.md): deterministic periodic graph artifact pilot and GNN/non-goal boundary.
- [Materials Structure Prediction Readiness](MATERIALS_STRUCTURE_PREDICTION_READINESS.md): v2.2.4 readiness and v2.2.5 limited known-structure comparison outcome.
- [Materials Known-Structure Prediction](MATERIALS_KNOWN_STRUCTURE_PREDICTION.md): v2.2.5 fixed known-structure feature-set comparison and local/tracked outputs.
- [Materials Structure Predictive Value](MATERIALS_STRUCTURE_PREDICTIVE_VALUE.md): v2.2.5 paired structure-descriptor predictive-value decision and representative-model boundary.
- [Materials Predictive Uncertainty](MATERIALS_PREDICTIVE_UNCERTAINTY.md): split-conformal residual interval diagnostics and uncertainty claim limits.
- [Platform v2.2 Closeout](PLATFORM_V2_2_CLOSEOUT.md): v2.2 scientific evidence closeout, capability matrix, claim matrix, artifact lineage, and release-readiness verdict.
- [Materials v2.2 Scientific Evidence](MATERIALS_V2_2_SCIENTIFIC_EVIDENCE.md): composition, known-structure descriptor, graph-artifact, and representative-model evidence levels.
- [Materials v2.2 Claim Boundaries](MATERIALS_V2_2_CLAIM_BOUNDARIES.md): allowed, limited, unsupported, and prohibited Materials v2.2 scientific claims.
- [Materials v2.2 Uncertainty Boundaries](MATERIALS_V2_2_UNCERTAINTY_BOUNDARIES.md): source uncertainty, numerical tolerance, prediction interval, split variation, and model-form limitations.
- [v2.2.0 Release Notes](releases/V2_2_0.md): Materials composition features, structure entities/descriptors, graph artifacts, limited known-structure evidence, and trust-boundary release notes.
- [v2.3.0 Release Notes](releases/V2_3_0.md): PGIR governance, Battery representation conformance, identifiability limits, bounded evaluator execution, source recovery, and policy-stability evidence.
- [RFC 0001 PGIR Architecture](rfcs/RFC_0001_PGIR_ARCHITECTURE.md): accepted PGIR architecture decision.
- [RFC 0002 Representation Maturity](rfcs/RFC_0002_REPRESENTATION_MATURITY.md): maturity levels and promotion rules.
- [RFC 0003 Schema Ownership and Evolution](rfcs/RFC_0003_SCHEMA_OWNERSHIP_AND_EVOLUTION.md): ownership, compatibility, and migration policy.
- [RFC 0004 Mechanism and Operator Taxonomy](rfcs/RFC_0004_MECHANISM_AND_OPERATOR_TAXONOMY.md): Evaluator, Transformer, and Propagator taxonomy.
- [RFC 0005 Domain Boundaries](rfcs/RFC_0005_DOMAIN_BOUNDARIES.md): domain-neutral core and domain-explicit context policy.
- [Schema Evolution](SCHEMA_EVOLUTION.md): deterministic migration policy for versioned scientific records.
- [Dynamic Physics and Graph Readiness](DYNAMIC_PHYSICS_AND_GRAPH_READINESS.md): state, trajectory, and graph metadata readiness without solvers or GNN execution.
- [Unit Backend Decision](UNIT_BACKEND_DECISION.md): builtin unit backend default and optional Pint adapter decision.
- [Scientific Trust Boundary](SCIENTIFIC_TRUST_BOUNDARY.md): v2.1.5 evidence levels, constraint roles, claim matrix, and domain-specific scientific boundaries.
- [Scientific Feature Candidates](SCIENTIFIC_FEATURE_CANDIDATES.md): v2.1.5 metadata-only physics-aware feature candidate registry and v2.2 builder boundary.
- [Materials Physics Features](MATERIALS_PHYSICS_FEATURES.md): v2.2 bounded Materials composition feature builders, property provenance, coverage policy, and CLI.
- [Materials Predictive-Value Validation](MATERIALS_PREDICTIVE_VALUE_VALIDATION.md): v2.2 matched baseline/physics feature-set comparison and claim boundary.
- [XRD Physics Validation](XRD_PHYSICS_VALIDATION.md): Bragg and Scherrer execution boundary, units, claim limits, and non-goals.
- [Domain Knowledge Packs](DOMAIN_KNOWLEDGE_PACKS.md): v2.1.4 metadata packs for materials, battery, manufacturing, reliability, and XRD.
- [Physics-Aware Roadmap](PHYSICS_AWARE_ROADMAP.md): staged path for future physics-aware metadata and descriptors without overclaiming.
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
- [Materials v2.2 Data Audit](MATERIALS_V2_2_DATA_AUDIT.md): existing v1.3 local artifact gate for bounded physics feature construction.
- [Materials Project Acquisition Scope Audit](MATERIALS_PROJECT_ACQUISITION_SCOPE_AUDIT.md): v2.2.3 exact 838-row lineage, Fe/Si-containing multinary scope, and structure coverage audit.
- [Materials Project Acquisition and Structure](MATERIALS_PROJECT_ACQUISITION_AND_STRUCTURE.md): v2.2.4 existing-ID structure enrichment execution, snapshot alignment, and local-only structure policy.
- [Scientific Entity Architecture Audit](SCIENTIFIC_ENTITY_ARCHITECTURE_AUDIT.md): dict/DataFrame, runtime object, serialized record, registry-row, and artifact representation audit for v2.2.2.
- [Materials Project v1.3 Plan](MATERIALS_PROJECT_V1_3_PLAN.md): exact acquisition, descriptors, group-aware validation, trust-boundary diagnostics, and conservative closeout.
- [Reliability v1.5 Plan](RELIABILITY_V1_5_PLAN.md): generic reliability/risk contract, Backblaze access gate, full-year readiness reassessment, fixed 7-day classification baselines, trust-boundary closeout, leakage map, and validation hierarchy.
- [Platform v2 Plan](PLATFORM_V2_PLAN.md): configuration-driven platform scaffold roadmap.
- [Platform v2.1 Plan](PLATFORM_V2_1_PLAN.md): local persistent registry and bounded scientific execution roadmap.
- [Platform v2.1 Closeout](PLATFORM_V2_1_CLOSEOUT.md): v2.1.1-v2.1.5 summary, current boundaries, release-readiness checklist, and v2.2 roadmap.
- [Platform v2 Closeout](PLATFORM_V2_CLOSEOUT.md): v2.0.1-v2.0.5 scaffold summary, current execution boundary, and v2.1 roadmap.
- [v2.1.0 Release Notes](releases/V2_1_0.md): persistent registry, bounded scientific execution, scientific trust boundary, and feature-eligibility release notes.
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
