# Platform v2.5 Roadmap

Status: `v2.5.1_external_source_compatibility_feature_stage_complete`

## Release Boundary

`v2.4.0` remains the current public release. v2.5.1 is a completed feature
stage on its feature branch; it is not a public release, tag, or release-note
scope.

## v2.5.1 Compatibility Evidence

The bounded audit supports two explicit historical adapters:

- Materials v2.2.4: `compatible_with_restrictions`
- Battery v2.3.5: `partial`

The software-compatibility verdict is `supported`. Provenance portability
remains `diagnostic`. Named dataset snapshot identity, API client version, the
original NASA snapshot, retrieval timestamp, license or terms, measurement
uncertainty, and calibration metadata remain unresolved where the tracked
source evidence does not provide them.

The audit performs no network access, credential access, source mutation,
artifact migration, or model execution. It replays only allowlisted tracked
compact evidence through explicit versioned adapters.

## Claim Boundary

Compatibility demonstrates deterministic software interpretation of the two
tested artifact versions. It does not establish source truth, scientific
validity, cross-domain comparability, mechanism validation, independent
validation, or production validation.

## Next Stage

The next bounded stage is a metadata- and checksum-based retrieval
reproducibility audit. Physical-operator portability remains lower priority
until two genuinely comparable domain contexts and their required evidence
are available.

## Non-Goals

v2.5.1 does not add a general migration framework, automatic network
acquisition, NIST/NREL/NVD integration, heterogeneous data merging, model or
solver execution, GNN or PINN execution, or a user interface.
