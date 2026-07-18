# Platform v2.4 Roadmap

Status: `v2.4.1_completed_feature_stage`

## v2.4.1

- Versioned external source-system, dataset, snapshot, distribution,
  retrieval, documentation, and provenance contracts.
- Compatibility mappings for current Materials Project and NASA-derived
  Battery source records without rewriting released artifacts.
- Future NIST OAR, NVD, and NREL source declarations with no integration claim.
- Actual PGIR declaration and conformance reuse over 838 local Materials
  structure entities.
- Cross-domain reuse verdict with physical-operator reuse explicitly false.
- Read-only platform report sections from tracked compact summaries.

## v2.4.2

- Add source documentation and terms-resolution workflows that remain
  dataset-specific.
- Introduce explicit source-record lineage links in the local run registry.
- Test one additional external dataset contract without broad generic clients.
- Preserve current Battery official-snapshot and Materials named-snapshot gaps
  unless new evidence resolves them.

## v2.4.3

- Add compatibility-adapter validation across multiple historical manifest
  versions.
- Add retrieval reproducibility comparisons using metadata and checksums only.
- Avoid automatic acquisition and cross-source dataset merging.

## v2.4.4

- Evaluate whether a separately justified scientific operator can be reused
  across two domains. Representation-framework reuse alone is insufficient.

## v2.4.5

- Close the v2.4 provenance and cross-domain governance release boundary.
- Require independent evidence before any independent- or production-
  validation status can be considered.

## Non-Goals

No automatic network access, universal source client, source trust score,
mechanism fitting, GNN/PINN, DFT calculation, model retraining, autonomous
scientific recommendation, or production decision is part of this roadmap.
