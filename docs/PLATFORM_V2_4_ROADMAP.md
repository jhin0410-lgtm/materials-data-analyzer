# Platform v2.4 Roadmap

Status: `released_as_v2.4.0`

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

- Add the first strict executable PGIR Model Contract for one synthetic scalar
  diffusion benchmark.
- Execute registered exact and deterministic FTCS Propagators under explicit
  dimensional, initial/boundary, stability, and resource gates.
- Compare against the analytical single-mode solution and a predeclared
  coarse/medium/fine refinement audit.
- Keep physical execution bounded to this benchmark; cross-domain operator
  reuse, independent validation, and production validation remain false.

## v2.4.0 Release Boundary

v2.4.0 closes two completed feature stages:

- v2.4.1: versioned external-source governance and restricted second-domain
  PGIR representation reuse.
- v2.4.2: one bounded executable physical Model Contract with analytical and
  deterministic FTCS propagation.

The release does not claim cross-domain physical-operator reuse, independent
validation, production validation, a general PDE framework, or real-material
mechanism validation.

## Deferred Beyond v2.4.0

The following work requires a separate justified scope and is not part of this
release:

- compatibility-adapter validation across historical manifest versions
- retrieval reproducibility comparisons using metadata and checksums
- evidence-backed resolution of currently unresolved source snapshots,
  licensing, and documentation
- evaluation of one scientific operator across two genuinely comparable
  domain contexts
- independent or production validation supported by independent evidence

Automatic acquisition and heterogeneous cross-source dataset merging remain
out of scope.

## Post-Release v2.5.1 Follow-On

The first deferred item is now exercised for exactly two tracked summaries:
the Materials v2.2.4 structure-enrichment summary and Battery v2.3.5 source-
lineage summary. The audit is a read-only compatibility replay, not a general
migration system. It keeps Materials named-snapshot/client metadata unresolved
and the Battery mapping partial. Other historical versions, source retrieval,
and evidence-backed resolution of external metadata remain deferred.

## Non-Goals

No automatic network access, universal source client, source trust score,
mechanism fitting, GNN/PINN, DFT calculation, model retraining, autonomous
scientific recommendation, or production decision is part of this roadmap.
