# Independent Input-Evidence Origin Pack Consumer

`input_evidence_origin_pack_consumer` is the independent read-side boundary for the self-contained evidence-origin pack.

It deliberately does **not** trust the publisher's return value or the manifest's `origin_class` label as scientific authority. It re-reads the exact packed bytes and reconstructs the origin-classification chain itself.

## Consumer API

```python
from materials_data_analyzer.research_loop.input_evidence_origin_pack_consumer import (
    authenticate_input_evidence_origin_pack,
)

report = authenticate_input_evidence_origin_pack("origin-pack")
```

## Independent checks

The consumer owns its expected pack schema/policy constants instead of importing them from the publisher implementation. It validates:

- exact manifest key sets with duplicate-key rejection;
- the producer's fixed schema/policy and Windows/Linux publication contract;
- all explicit non-authority flags remain `false`;
- fixed `request.json` identity plus exact SHA-256 and size;
- request item identities and portable source-path syntax;
- exact three-field program-evidence identities (`workstream_id`, `role`, `sha256`);
- deterministic packed snapshot paths (`items/NNNN/...`);
- portable bundle-relative paths with Windows ADS/reserved-name rejection;
- no symlink/reparse traversal inside the pack;
- exact SHA-256 and byte size for every evidence/declaration/verifier snapshot;
- no snapshot path reuse across authority roles;
- exact request-identity set equals the manifest item-identity set;
- the evidence snapshot SHA equals the program-evidence SHA;
- `authenticate_evidence_origin_binding()` succeeds independently on every exact evidence/declaration/verifier triple;
- manifest `origin_class` equals the class recomputed from those exact bytes.

The original request source paths are syntax-validated only. They are not re-opened and are not authoritative after publication because the pack is self-contained.

## Deliberate independence from the publisher

The consumer does not import the publisher module for schema/policy authority. This reduces common-mode failure risk: a producer implementation bug that changes its own constant or accepts an alternate snapshot layout cannot silently redefine what the consumer accepts.

The consumer also rejects a self-consistent manifest that points to alternate packed filenames. Checksums alone are insufficient to claim that a directory follows the producer contract.

## What a successful report means

Success means:

> The exact packed evidence bytes, origin declaration bytes, and origin verification-decision bytes form the expected cryptographic/schema chain for the reported origin classification, and the pack's program-evidence identities are internally consistent with its exact request snapshot.

It does **not** mean:

- the physical experiment or measurement actually occurred;
- the verifier is who the file claims it is;
- the verifier has appropriate institutional credentials;
- the scientific result itself is valid;
- evidence sources are independent;
- confidence is calibrated;
- the program-state history was independently reauthenticated;
- the pack will remain immutable after the function returns;
- the filesystem is protected against a hostile same-identity concurrent writer;
- empirical scientific authority has been granted;
- scientific status may be promoted;
- execution/network/physical actions are authorized;
- positive scientific closeout is allowed.

The report therefore keeps `empirical_authority_granted=false` and all broader authority flags false.

## Consequence for `empirical_derived`

This consumer removes one provenance blocker: exact input-evidence origin-classification bytes can now be transported and independently reauthenticated.

It does **not** by itself justify enabling the Scientific Critic's `empirical_derived` scope. The current origin verifier contract authenticates the decision bytes and their declared scope, but not verifier identity/credentials or physical-origin truth. A later adapter must remain fail-closed unless those missing authority prerequisites are supplied by a separate, explicit trust contract.

`empirical_direct` is even stricter: input-evidence provenance cannot establish that a new result node itself came from a physical experiment. It requires a result-origin provenance path of its own.
