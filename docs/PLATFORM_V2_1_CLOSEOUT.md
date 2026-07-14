# Platform v2.1 Closeout

Status: `release_ready`.

v2.1 extends the v2 platform scaffold with a local registry, diagnostics,
scientific constraint metadata, bounded scientific execution, and v2.1.5 trust
boundaries for scientific claims and feature eligibility.

Release audit result: v2.1.0 is ready for merge, tagging, and GitHub Release
publication after the final CI gate.

## Completed Scope

- v2.1.1: local SQLite run/artifact registry, lineage, reproducibility, and
  registry export.
- v2.1.2: registry diagnostics, evidence gaps, claim evaluation, and report
  diagnostics.
- v2.1.3: unit registry, scientific constraint registry, domain-knowledge
  packs, applicability checks, and metadata-only scientific registry export.
- v2.1.4: bounded scientific execution for registered scalar/small-list checks,
  scientific findings, claims, unit conversions, and local outputs.
- v2.1.5: scientific trust boundary, constraint-role classification, feature
  candidate registry, schema v4 persistence, and closeout documentation.

## Current Boundaries

The platform can record consistency evidence and bounded estimates. It cannot
claim independent validation, production validation, phase identification,
physics-constrained modeling, hybrid physics/ML modeling, DFT/FEM/CFD,
survival/RUL physical modeling, or production scientific decisions.

## Local Outputs

Registry databases, scientific execution reports, trust exports, and platform
reports are generated under ignored `outputs/` paths. Tracked artifacts are
schemas, deterministic snapshots, tests, and documentation.

## Release-Readiness Checklist

- Registry migrations cover schema versions 1 to 4.
- Scientific execution and trust persistence are idempotent.
- Feature candidates remain metadata-only.
- Report generation reads stored trust summaries only.
- No raw data, model training, network calls, arbitrary imports, or arbitrary
  equation parsing are introduced.
- Existing v1.x and v2.x tests remain compatible.

## v2.2 Roadmap

Recommended v2.2 work:

- selected bounded feature builders with leakage tests
- feature-builder manifests and output contracts
- optional model-input evidence linking
- richer scientific report sections from stored evidence only
- no SHAP or physics-aware model claims unless eligibility evidence exists
