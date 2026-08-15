# Self-Contained Input-Evidence Origin Pack

`input_evidence_origin_pack` turns an already specified input-evidence origin request into a relocatable, checksum-bound provenance pack.

The publisher is deliberately **not** an empirical-authority adapter. Its only job is to preserve the exact bytes needed by a later independent consumer.

## Publication API

```python
from materials_data_analyzer.research_loop.input_evidence_origin_pack import (
    publish_input_evidence_origin_pack,
)

report = publish_input_evidence_origin_pack(
    request_path="origin-request.json",
    proposal_input_evidence_bindings=proposal["input_evidence_bindings"],
    program_state=program_state,
    artifact_root="artifacts",
    output_dir="origin-pack",
)
```

The publisher calls `authenticate_input_evidence_origin_request()` itself. It does not accept a caller-supplied authentication report.

## Pack contents

A successful pack contains:

- the exact request bytes at `request.json`;
- one exact evidence byte snapshot per request item;
- the exact origin-declaration bytes for each evidence item;
- the exact origin-verification-decision bytes for each evidence item;
- `input_evidence_origin_pack_manifest.json`, binding every snapshot by relative path, SHA-256, size, role, program-evidence identity, and the origin class returned by the authenticated request chain.

Source paths are not included as authority-bearing pack data. The returned publisher report may disclose the original request path only as informational metadata with `authoritative: false`.

## Cross-checks

Before publication, the publisher additionally checks that the authenticated request report and immutable payload tuple agree on:

- `workstream_id`;
- evidence role;
- evidence SHA-256;
- exact evidence bytes;
- one of the four explicit origin classes supported by the evidence-origin contract.

This prevents an accidental report/payload positional mismatch from becoming a self-consistent-looking pack.

## Publication boundary

Publication is intentionally supported only on Windows and Linux, using an atomic no-replace directory operation. The destination must not already exist.

The implementation assumes exclusive write ownership of its private staging tree from creation through publication. Link/reparse checks and repeated byte validation are defense in depth; the pack does not claim sandboxing or resistance to a hostile process with the same OS identity and write access to that staging tree.

## Scientific authority boundary

A pack proves only that exact provenance bytes were captured after the request authenticator accepted them. It does **not** independently prove:

- that a physical experiment or measurement actually occurred;
- verifier identity or institutional credentials;
- scientific validity of the evidence result;
- source or replication independence;
- calibrated confidence;
- empirical inference authority;
- scientific-status promotion;
- execution/network/physical-experiment authorization;
- positive scientific closeout.

`empirical_derived` and `empirical_direct` therefore remain fail-closed.

## Next trust step

A later independent consumer must re-read the pack from its own bundle-relative bytes and call `authenticate_evidence_origin_binding()` again for every evidence/declaration/verifier triple. It must not trust the pack manifest's `origin_class` field by itself.
