# Provenance-aware Comparability Engine

## Purpose

The Comparability Engine is a Science-plane gate over two externally authenticated
`EvidencePacket` objects and one explicit comparison claim. It answers only whether the
available evidence may support that declared comparison under the currently bound context.

It does **not** infer causality, generate missing calibration, fit a model, create measurements,
or authorize predictive/engineering use.

## Outcomes

- `COMPARABLE`: every required dimension is explicitly present and agrees.
- `CONDITIONALLY_COMPARABLE`: every required dimension is present, no required dimension
  conflicts, and one or more explicitly allowed normalization/transformation steps remain.
- `NOT_COMPARABLE`: at least one required dimension conflicts.
- `UNKNOWN`: no required dimension conflicts, but at least one required context is missing.

There is intentionally no scalar comparability score. A numeric score would imply an ordering
and uncertainty meaning that the current evidence does not scientifically calibrate.

## Claim completeness

The default registry covers:

1. material identity;
2. material composition/specification;
3. feedstock, lot, or batch;
4. process route;
5. thermal/post-treatment history;
6. build/sample orientation;
7. geometry;
8. surface/sample preparation;
9. sample and acquisition identity;
10. instrument/detector;
11. instrument state and calibration;
12. acquisition parameters;
13. environmental conditions;
14. preprocessing/transformation history;
15. units/reference conventions;
16. target/response semantics;
17. source/dataset/sample/acquisition/development independence;
18. protocol/reference version.

For each comparison, every registered dimension must be either `required` or explicitly
`irrelevant`. Omission is not equivalence. Missing required context remains `UNKNOWN`.

Only units/reference conventions may currently be declared transformable. Even then, the engine
accepts a conditional normalization only when the compared result kinds agree and the units are
members of the same recognized physical unit family. A declared transformation does not perform
that transformation and does not establish calibration or reference-frame equivalence.

## Evidence authentication

The public engine accepts `AuthenticatedEvidenceInput` values. Each packet is independently
validated against:

- exact artifact bytes;
- packet source-binding SHA-256 and byte sizes;
- an exact expectation object;
- an externally supplied SHA-256 trust root over that expectation object.

A packet self-hash alone is not an external trust root.

The resulting assessment binds the exact packet SHA-256 and each source-binding SHA-256/byte
identity. Persisted assessments can be replayed with `verify_comparability_assessment()`,
which recomputes the entire assessment from the authenticated packets and claim.

## Independence

Physical comparability and independent replication are separate questions. The engine preserves
source-family, dataset-parent, sample-parent, acquisition-parent, and development-family lineage.
When independent replication is required, known shared lineage blocks that claim and unknown
lineage remains unresolved.

Different filenames, DOIs, checksums, or provider labels are never sufficient evidence of
independence.

## Planner handoff

Missing required dimensions are emitted as deterministic `planner_evidence_gaps` with
`action_class=evidence_acquisition`. These are planning requirements only. They do not create
empirical evidence, scientific status, or execution authority.

## Current real negative control

The first repository-bound benchmark compares the current NIST AMBench 2018-02 IN625 melt-pool
geometry context against the reviewed Zenodo 20503603 IN625 tensile context.

The shared material label is retained as a satisfied dimension, while process route, specimen
geometry, response semantics, units, and protocol conflict for the declared direct numerical
comparison. Therefore the engine returns `NOT_COMPARABLE`; it does not transfer tensile
evidence into melt-pool validation.

## Characterization control

A lossy software/example SAED representation may support software-method behavior, but it is not
automatically comparable to raw material-aware diffraction evidence for a phase/indexing claim.
The generic engine reaches that result from material, response, protocol, and calibration
context—not from provider-name branches.

## Authority boundary

Every assessment explicitly records:

- `empirical_evidence_created=false`;
- `scientific_status_promoted=false`;
- `calibration_transfer_performed=false`;
- `missing_context_inferred=false`;
- `causal_inference_performed=false`;
- `model_fit_performed=false`;
- `predictive_use_authorized=false`;
- `engineering_use_authorized=false`.

A successful comparability assessment is necessary for some downstream comparisons; it is not by
itself sufficient for model validation, causal inference, prediction, or engineering release.
