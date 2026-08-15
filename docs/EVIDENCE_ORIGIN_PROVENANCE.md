# Evidence-origin provenance and authenticated critic APIs

This layer separates **provenance identity** from **scientific authority**.

## Exact evidence-origin classification

`authenticate_evidence_origin_binding(...)` binds three exact byte strings:

1. evidence artifact bytes;
2. an origin declaration;
3. an origin-verification decision.

A successful result authenticates only the recorded classification and its exact SHA-256 identities. It does **not** authenticate that a physical experiment actually occurred, the verifier's credentials, instrument calibration, result validity, source independence, empirical scientific authority, execution permission, or positive closeout.

## Program evidence bridge

`authenticate_program_evidence_origin_binding(...)` additionally requires an exact `{workstream_id, role, sha256}` binding to occur once in the caller-supplied research-program state and requires the same SHA-256 to identify the exact evidence bytes used by the origin-classification primitive.

The bridge establishes membership in the **caller-supplied** program state only; it does not independently re-authenticate how that program state was produced and reports that trust boundary explicitly. Disabled or runtime-context-blocked workstreams with `planning_state: null` contribute no evidence and are ignored. Malformed non-null planning states fail closed.

The bridge still does not grant empirical authority.

## Authenticated Scientific Critic

`build_authenticated_scientific_critic_report(...)` accepts a bundle root, independently re-authenticates the bundle, pins the exact graph SHA before and after base-critic evaluation, and may add a directional critic advisory. It does not accept caller-supplied consumer reports.

Authenticated support does not establish support independence or calibrated confidence. Authenticated contradiction/falsification may add a **manual, plan-only** reframe advisory, but cannot replace a stronger base-critic stop recommendation or automatically stop/execute anything.

Both `empirical_derived` and `empirical_direct` remain disabled at the critic adapter. The existence of an origin-classification record or program-evidence bridge is not sufficient by itself to reopen those scopes. A future transition contract must first snapshot resolvable origin-authenticated evidence into the bundle and independently re-authenticate it; physical-source/credential policy may still be required after that.

## Public imports

```python
from materials_data_analyzer.research_loop import (
    authenticate_evidence_origin_binding,
    authenticate_program_evidence_origin_binding,
    build_authenticated_scientific_critic_report,
)
```
