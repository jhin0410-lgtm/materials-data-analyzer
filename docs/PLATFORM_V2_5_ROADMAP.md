# Platform v2.5 Roadmap

Status: `released_within_v2.7.0`

## Release Boundary

v2.5.1 and v2.5.2 were completed internal feature stages and are included in
the public `v2.7.0` release. A separate v2.5.0 public tag or release was not
created.

The later v2.6 Battery evidence line was completed and checksum-closed before a
v2.5 public boundary existed. After the v2.6.14 line closeout, a distinct
post-v2.6 integration scope was added and is released as v2.7.0.

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

## v2.5.2 Retrieval Reproducibility

v2.5.2 implements the metadata- and checksum-based
[retrieval reproducibility audit](RETRIEVAL_REPRODUCIBILITY_AUDIT.md). Both
Materials and Battery remain `insufficient_evidence`: the repository has one
bounded evidence point for each case study, not two independent comparable
retrieval events. No missing snapshot, timestamp, client, license, uncertainty,
or calibration metadata is inferred.

## Claim Boundary

Compatibility demonstrates deterministic software interpretation of the two
tested artifact versions. It does not establish source truth, scientific
validity, cross-domain comparability, mechanism validation, independent
validation, or production validation.

The complete public context is documented in
[`docs/releases/V2_7_0.md`](releases/V2_7_0.md).

## Non-Goals

v2.5 does not add a general migration framework, automatic network acquisition,
heterogeneous data merging, model or solver execution, GNN or PINN execution,
or a user interface.
