# Exact Acquisition-Record Provenance Binding

`acquisition_record_binding` authenticates a deliberately narrow provenance statement:

> These exact evidence bytes are the bytes whose SHA-256 is recorded at an explicitly declared location in these exact acquisition-manifest bytes, and selected manifest values equal the exact values declared by the provenance declaration.

It does **not** authenticate the external world behind those records.

## API

```python
from materials_data_analyzer.research_loop.acquisition_record_binding import (
    authenticate_acquisition_record_binding,
)

report = authenticate_acquisition_record_binding(
    evidence_bytes=raw_bytes,
    acquisition_manifest_bytes=manifest_bytes,
    acquisition_declaration_bytes=declaration_bytes,
)
```

All three inputs are authenticated as exact bytes. JSON parsing rejects duplicate keys.

## Declaration contract

The declaration binds:

- an `acquisition_id`;
- the exact evidence SHA-256;
- the exact acquisition-manifest SHA-256;
- a semantic evidence role;
- a restricted RFC 6901 JSON pointer at which the manifest must record the exact evidence SHA-256;
- a set of exact manifest claim bindings;
- explicit non-empty limitations.

Every manifest claim binding has an exact claim name, JSON pointer, and scalar expected value. Claim names and pointers must be unique.

The minimum recorded-provenance claim names are:

- `source_system` — text;
- `source_version` — text;
- `retrieval_endpoint` — text;
- `retrieval_status` — text;
- `network_performed` — boolean.

The comparison is type-strict. For example, JSON `true` cannot be substituted by integer `1` even though Python normally compares them as equal.

Additional scalar claims can bind fields such as preflight status or row count. Floats, arrays, and objects are intentionally excluded from the generic claim-value contract to avoid ambiguous numeric/container semantics at this trust boundary.

### Claim names do not create semantic authority

The declaration chooses both a claim name and the JSON pointer it refers to. Therefore a claim named `source_system` is **not by itself proof that the selected pointer is the repository's canonical source-system field**. At this primitive layer it means only that the declaration labeled that exact manifest value as its `source_system` claim.

A later predeclared trust policy must pin the allowed claim names **together with their allowed JSON pointers and values** before these fields can participate in a source-qualification decision. This primitive deliberately does not infer semantic trust from a free-form claim name.

## Recorded acquisition provenance, not provider identity

A successful report means that the exact manifest **records** the authenticated values and binds the exact evidence bytes. For example, a successful report may say:

- recorded source-system claim: `Materials Project`;
- recorded source-version claim: `2026.08.01`;
- recorded endpoint claim: `materials.summary.search`;
- recorded retrieval-status claim: `success`;
- recorded network-performed claim: `true`.

Those statements are about the exact values selected by the acquisition declaration. They are not equivalent to proving that Materials Project authored the manifest, that a TLS connection terminated at a Materials Project-controlled service, or that the historical retrieval actually occurred.

The report therefore explicitly keeps these false:

- `historical_acquisition_event_authenticated`;
- `acquisition_manifest_authorship_authenticated`;
- `source_identity_or_credential_authenticated`;
- `transport_peer_identity_authenticated_by_this_contract`;
- `physical_origin_truth_authenticated`;
- `scientific_result_validity_authenticated`;
- `support_independence_established`;
- `empirical_authority_granted`;
- `scientific_status_changed`;
- `execution_authorized`;
- `positive_closeout_granted`.

## Why this layer exists

Existing acquisition code already records useful provenance such as raw/table hashes, database versions, exact query parameters, package versions, timestamps, and execution status. Existing external-source screening code also records source and independence claims.

However, those source labels and independence flags are locally recorded metadata; they are not a cryptographically authenticated institutional identity. Treating them as one would create an authority escalation.

This primitive therefore strengthens the **integrity of the recorded acquisition chain** without pretending it supplies an external trust root.

## Relationship to evidence-origin packs

The evidence-origin pack answers a different question: whether exact evidence bytes, origin-declaration bytes, and origin-verification-decision bytes form the expected origin-classification provenance chain.

The acquisition-record binding answers whether the same exact evidence bytes are bound to selected exact acquisition-manifest records.

A later qualification layer may require both reports to refer to the same evidence SHA-256. Even then, empirical scientific authority remains closed unless a separate predeclared trust contract supplies the missing external trust prerequisites.

## Next trust step

The next layer should be a predeclared local source-trust policy whose exact policy identity is pinned by already-trusted program state rather than chosen ad hoc together with the evidence. Such a policy must constrain allowed claim **name + JSON pointer + value** triples, not just source labels. It can then authenticate **which local acquisition records the research program is allowed to rely on**.

That still must not be described as cryptographic authentication of the external institution/provider unless a genuinely external credential or signature mechanism is introduced.
