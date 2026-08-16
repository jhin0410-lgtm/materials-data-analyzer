# Mission-Root Source-Trust Policy Authentication

`mission_source_trust_root` authenticates one first-class source-trust policy pin only after exact mission bytes match an independently supplied expected mission SHA-256.

This is a control-plane provenance contract. It does not turn a local source-trust policy into scientific or institutional authority.

## Why this layer exists

A mission and a research-program state can be made internally self-consistent by the same caller. Therefore this chain is circular and insufficient by itself:

`caller-created mission -> caller-created mission SHA -> caller-created program projection`

The authenticator breaks that circularity by requiring `expected_mission_sha256` as an explicit external trust-root input. The contract authenticates that the exact mission bytes and the relevant program projection agree with that supplied root. It does not authenticate who supplied the root or why that root should be trusted.

## Exact checks

`authenticate_mission_source_trust_policy_pin(...)`:

- requires a canonical lowercase external `expected_mission_sha256`;
- hashes the exact mission bytes and requires an exact match;
- rejects duplicate JSON keys in the mission;
- calls the research-mission validator and requires mission schema `1.1`;
- requires exactly one first-class mission pin for the selected `policy_id`;
- requires research-program schema `1.1` and program policy `1.0`;
- requires the program `mission_binding.sha256` to equal the supplied mission root;
- type-strictly compares the program's normalized mission with the normalized exact mission bytes;
- type-strictly compares the projected top-level policy-pin list with the mission pin list, including order;
- requires the exact source-trust policy bytes to hash to the selected mission pin;
- requires the policy file's top-level `policy_id` to match the selected mission pin;
- rejects unknown top-level fields in the policy identity envelope.

The source-trust policy's detailed rule semantics are intentionally **not** validated here. That remains the responsibility of `qualify_acquisition_record_under_pinned_policy()` when an exact acquisition record is evaluated.

## What success means

A successful report means:

> Exact mission bytes match the supplied mission root, the relevant program projection matches those authenticated mission bytes, and exact policy bytes match the selected first-class policy pin.

The report may therefore set `policy_pin_provenance_authenticated_under_supplied_mission_root=true`.

It must also state that the provenance of the externally supplied expected mission root is **not** authenticated by this contract.

## What success does not mean

This layer does not authenticate:

- the provenance or institutional authority of the supplied expected mission SHA;
- the complete provenance of the research-program state;
- detailed source-trust policy rule semantics;
- any acquisition record or historical acquisition event;
- external provider or institution identity;
- provider credentials or transport-peer identity;
- physical measurement or experiment truth;
- scientific-result validity;
- source or replication independence;
- calibrated confidence;
- empirical scientific authority;
- scientific-status mutation;
- execution/network/physical-experiment authority;
- positive scientific closeout.

Accordingly, this layer cannot reopen `empirical_derived` or `empirical_direct` Scientific Critic authority.

## Next bridge

A later rooted acquisition bridge may call this authenticator itself and then call `qualify_acquisition_record_under_pinned_policy()` using the mission-authenticated policy SHA. That can establish a bounded statement such as `local_record_reliance_qualified_under_authenticated_mission_pin=true` without claiming external provider identity or empirical scientific authority.
