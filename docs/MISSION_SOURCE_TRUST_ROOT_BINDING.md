# Mission-Root Acquisition Source-Trust Binding

`mission_source_trust_root_binding` connects three exact provenance layers without upgrading them into scientific authority:

1. an externally supplied expected mission SHA-256;
2. exact mission bytes containing a first-class source-trust policy pin;
3. an exact acquisition record qualified by the pinned local policy.

The supplied expected mission SHA is the explicit trust-root assumption. This contract verifies agreement with that root; it does **not** authenticate who supplied the root or why it should be trusted.

## Required chain

`qualify_acquisition_record_under_supplied_mission_root(...)` requires:

- exact mission bytes whose SHA-256 equals a canonical lowercase `expected_mission_sha256`;
- mission schema `1.1` with exactly one requested first-class `(policy_id, sha256)` pin;
- research-program schema `1.1` and program-policy version `1.0`;
- a program `mission_binding` containing exactly `path` and `sha256`, with the SHA equal to the exact mission bytes;
- the program's normalized mission and projected pin list to agree exactly with the validated mission;
- exact source-trust policy bytes whose SHA equals the selected mission pin;
- successful independent `qualify_acquisition_record_under_pinned_policy()` reauthentication of the exact acquisition record;
- the downstream qualification's internal `source_trust_policy_id` and policy SHA to equal the authenticated mission pin.

The last cross-check is important: a mission pin cannot name policy `A` while the exact pinned policy bytes internally identify themselves as policy `B`.

All exact byte inputs fail closed at this API boundary rather than leaking generic Python type errors.

## Successful result

Success may state that:

- the supplied expected mission SHA matched the exact mission bytes;
- the mission policy pin is authenticated **under that supplied root**;
- the research-program projection agrees with those exact mission bytes;
- the policy's internal identity agrees with the authenticated mission pin;
- the exact acquisition record satisfies exactly one local source-trust rule under that pin.

This yields a bounded statement such as:

`local_record_reliance_qualified_under_supplied_mission_root=true`

It is stronger than an unrooted local pin because the pin's control-plane provenance is now explicitly anchored to a caller-supplied mission root.

## Deliberate non-authority boundary

Success does **not** authenticate:

- provenance, authorship, repository identity, or institutional authority of the supplied expected mission SHA;
- the complete historical provenance of the research-program state;
- external provider or institution identity;
- provider credentials;
- transport-peer identity;
- whether the recorded historical acquisition event actually occurred as claimed;
- physical experiment or measurement truth;
- scientific-result validity;
- source, cohort, or replication independence;
- calibrated confidence;
- empirical scientific authority;
- scientific-status mutation;
- execution, network, or physical-experiment authority;
- positive scientific closeout.

Accordingly this bridge does **not** reopen `empirical_derived` or `empirical_direct` Scientific Critic authority. Those require separate provenance and authority contracts beyond local acquisition-record reliance.
