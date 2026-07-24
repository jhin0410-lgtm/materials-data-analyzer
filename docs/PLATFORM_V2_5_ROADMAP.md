# Platform v2.5 Roadmap

Status: `v2.5.2_retrieval_reproducibility_feature_stage_complete`

## Release Boundary

`v2.4.0` remains the current public release. v2.5.1 and v2.5.2 are completed
feature stages; they are not public releases, tags, or release-note scope.

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

v2.5.2 implements the metadata- and checksum-based
[retrieval reproducibility audit](RETRIEVAL_REPRODUCIBILITY_AUDIT.md). Both
Materials and Battery remain `insufficient_evidence`: the repository has one
bounded evidence point for each case study, not two independent comparable
retrieval events. No missing snapshot, timestamp, client, license,
uncertainty, or calibration metadata is inferred.

Physical-operator portability remains lower priority until two genuinely
comparable domain contexts and their required evidence are available.

The subsequent Battery forecasting feature stage is documented separately in
the [Platform v2.6 roadmap](PLATFORM_V2_6_ROADMAP.md); it does not change the
v2.5 compatibility or retrieval-reproducibility conclusions.

## Non-Goals

v2.5 does not add a general migration framework, automatic network
acquisition, NIST/NREL/NVD integration, heterogeneous data merging, model or
solver execution, GNN or PINN execution, or a user interface.
