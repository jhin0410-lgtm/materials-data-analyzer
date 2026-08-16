# Pinned Local Acquisition Source-Trust Policy

This layer evaluates an exact acquisition record under exact local policy bytes whose SHA-256 is supplied by a caller.

It is intentionally split from program-state pin provenance. The qualifier proves only that the policy bytes match the supplied SHA and that one exact local rule matches the independently re-authenticated acquisition record.

## API

```python
from materials_data_analyzer.research_loop.acquisition_source_trust_policy import (
    qualify_acquisition_record_under_pinned_policy,
)

report = qualify_acquisition_record_under_pinned_policy(
    evidence_bytes=evidence_bytes,
    acquisition_manifest_bytes=manifest_bytes,
    acquisition_declaration_bytes=declaration_bytes,
    source_trust_policy_bytes=policy_bytes,
    expected_source_trust_policy_sha256=pinned_sha256,
)
```

The function independently calls `authenticate_acquisition_record_binding()`; a caller cannot inject a precomputed acquisition report.

## Policy contract

A policy contains:

- `schema_version`;
- `policy_id`;
- one or more `rules`;
- non-empty `limitations`.

Each rule pins:

- a unique `rule_id`;
- an exact `evidence_role`;
- required acquisition-manifest claims by exact claim name, exact JSON pointer, and typed `allowed_values`.

Every rule must constrain all five base recorded-provenance claims:

- `source_system`;
- `source_version`;
- `retrieval_endpoint`;
- `retrieval_status`;
- `network_performed`.

The comparison is type-strict. Boolean `true` cannot be replaced by integer `1`.

If zero rules match, qualification fails. If more than one rule matches, qualification also fails rather than silently choosing a rule.

## What success means

A successful report may assert:

- the exact policy bytes match the supplied expected policy SHA;
- the exact acquisition record was independently re-authenticated;
- exactly one local policy rule matched the evidence role and exact recorded claim name + pointer + value constraints;
- `local_record_reliance_qualified_under_supplied_pin = true`.

This means only that the record is permitted by the supplied local policy pin.

## What success does not mean

This contract deliberately reports false for:

- provenance of the supplied expected policy pin;
- external provider/source identity;
- external source credentials;
- historical acquisition event truth;
- transport-peer identity;
- physical origin truth;
- scientific result validity;
- source/replication independence;
- empirical scientific authority;
- scientific-status mutation;
- execution authority;
- positive closeout.

A policy that allows the recorded value `Materials Project` therefore does not cryptographically prove that Materials Project authored or transmitted the bytes.

## Why the pin provenance is separate

The policy cannot establish its own authority merely by carrying its own identifier or checksum. That would be circular.

The next layer must independently prove that the exact policy SHA supplied here is itself pinned by an already trusted research-program state or mission boundary. Until that bridge exists, `expected_policy_pin_provenance_authenticated_by_this_contract` remains false.

Even after that bridge is added, empirical scientific authority and source independence remain separate questions.