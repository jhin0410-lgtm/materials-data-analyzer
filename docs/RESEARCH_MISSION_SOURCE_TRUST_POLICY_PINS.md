# Mission-Level Source-Trust Policy Pins

Research missions now have an explicit versioned slot for source-trust policy pins.

This change is intentionally a control-plane capability, not a new scientific-authority grant.

## Schema versions

Mission schema `1.0` remains a supported legacy contract. It cannot contain `source_trust_policy_pins`.

Mission schema `1.1` may contain the optional first-class field:

```json
{
  "source_trust_policy_pins": [
    {
      "policy_id": "example-local-policy-v1",
      "sha256": "<64 lowercase hex characters>"
    }
  ]
}
```

A `1.1` mission does not have to contain pins. An explicitly present pin list must be non-empty.

Each pin is limited to exactly `policy_id` and `sha256`. Duplicate policy IDs, duplicate policy SHA-256 values, malformed hashes, surrounding policy-ID whitespace, and unknown nested authority-looking fields fail closed.

## Program projection

`build_research_program()` copies the normalized mission pins into top-level `source_trust_policy_pins` and continues to bind the exact mission file bytes through `mission_binding.sha256`.

Changing a policy pin therefore changes the exact mission-file SHA.

The top-level program copy is convenience/provenance data. It is **not** an independent trust root and must never be accepted without checking it against the exact mission bytes.

## Metadata boundary

Mission `metadata` remains opaque informational data. A value such as:

```json
{
  "metadata": {
    "source_trust_policy_pins": [...],
    "provider_authenticated": true
  }
}
```

does not create a first-class policy pin and grants no authority.

## Root-of-trust boundary

An exact mission containing a policy SHA still does not prove that the mission itself is trusted. A caller could construct arbitrary mission bytes and a matching program state.

A later bridge must therefore require an explicit external expected mission SHA (or an equivalent independently trusted root), re-read the exact mission bytes, validate schema `1.1`, re-check the policy pin, and cross-check the program state's `mission_binding`, normalized mission, and projected pin set.

Until that root is supplied and checked, neither the mission nor the program may claim that policy-pin provenance is independently authenticated.

## Scientific authority boundary

Mission policy pins do not authenticate:

- external provider or institution identity;
- provider credentials;
- historical network acquisition truth;
- transport-peer identity;
- underlying physical measurement or experiment lineage;
- source or replication independence;
- scientific result validity;
- calibrated confidence;
- empirical scientific authority;
- execution/network/physical-experiment authority;
- scientific-status mutation;
- positive scientific closeout.

In particular, a locally accepted external-database record can still be an `analysis_output` or `computational_output`; its database provenance alone does not establish empirical measurement origin.