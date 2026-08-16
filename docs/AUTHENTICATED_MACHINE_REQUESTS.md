# Authenticated Machine Request Authorship

## Scope

This layer permits software to construct one bounded typed **request** only when the
request is rooted in an externally supplied expected mission SHA-256 and an exact
request-delegation policy pin authenticated from those mission bytes.

It does **not** authenticate the person or channel that supplied the mission root,
execute the request, synthesize operator acknowledgement, access the network, perform a
physical experiment, fit or evaluate a model, mutate a scientific claim, or grant
evidence, empirical authority, scientific status, or positive closeout.

## Authority chain

```text
externally supplied expected mission SHA-256
→ exact mission bytes (schema 1.2)
→ first-class request_delegation_policy_pins entry
→ exact request-delegation policy bytes
→ rebuilt program projection consistency
→ current planner/action authorization
→ exact planning registry normalized state + raw bytes
→ planner-selected exact execution registry normalized state + raw bytes
→ current immutable research ledger semantic hash + raw bytes
→ explicit typed inputs
→ authenticated request compiler
→ independently implemented authenticated request verifier
→ existing pinned typed executor (separate later step)
```

Compiler and verifier each invoke the mission-root delegation bridge themselves from the
raw mission and policy bytes plus the independently supplied expected mission SHA. A
caller-supplied precomputed authentication report is not accepted as authority.

## Finite safe request surface

Version 1.0 recognizes only four existing audited typed executor surfaces:

- `audit_existing_battery_run@1.0`
- `target_reference_sensitivity@1.0`
- `protocol_stratification@1.0`
- `external_data_requirement_generation@1.0`

Recognition is not execution authorization. The current planner must select the exact
action/version; current authorization must return
`ready_for_explicit_execution_request`; version, category, cost, binding and input
contract must match the compiler's hardcoded contract and the verifier's independently
duplicated hardcoded contract; and the authenticated delegation policy must permit that
exact action and cost.

A registry or policy cannot add a new safe action. Model fitting/evaluation, NASA source
intake, human closeout, generic commands, network acquisition and physical experiments
remain outside this request-authorship contract. The external-data source-script surface
remains bounded only because downstream execution terminates in the existing hardcoded
typed dispatcher; it is not a general script runner.

## Exact bindings

Compilation and verification bind:

- exact mission bytes and independently supplied expected mission SHA-256;
- exact delegation-policy bytes, policy ID and mission-derived policy pin;
- planning registry ID, normalized SHA-256 and raw-file SHA-256;
- execution registry ID, normalized SHA-256 and raw-file SHA-256;
- immutable research-ledger semantic SHA-256 and exact ledger-file SHA-256;
- exact planner-selected action fingerprint, version, category and cost;
- explicit typed input directories and registry/request aliases;
- exact generated request bytes;
- current action-authorization policy version; and
- current authorized-executor policy version.

The deterministic request `action_id` incorporates all mutable authority inputs. Any
change invalidates the request.

## Output and authority boundary

A successful compiler call creates a new immutable directory containing:

```text
execution_request.json
authenticated_request_manifest.json
```

The output directory must not already exist. The execution request deliberately uses the
existing typed executor request schema and never contains `operator_acknowledgement`.

The manifest may state only:

```text
machine_request_authorship_permitted_under_supplied_external_mission_root = true
```

while all of the following remain false:

```text
expected_mission_root_supplier_authenticated
human_authorship_authenticated
operator_identity_authenticated
operator_acknowledgement_synthesized
execution_authorized
action_executed
network_access_authorized
physical_experiment_execution_authorized
generic_command_execution_authorized
model_fitting_authorized
scientific_evidence_upgraded
scientific_status_changed
empirical_authority_granted
positive_closeout_granted
```

## Independent verifier

`verify_authenticated_machine_request()` does not trust compiler-returned authority
booleans. It independently re-reads duplicate-key-safe mission and policy bytes, checks
the supplied expected mission root, rebuilds the program projection, re-runs the
mission-root bridge, checks downstream policy versions, re-runs current action
authorization, verifies planning/execution registry normalized and raw identities,
rechecks the ledger before and after semantic validation, verifies request bytes and
explicit inputs, derives the deterministic request ID independently, and rejects any
widened authority flag.

Verifier success means only:

```text
bounded_machine_request_verified_eligible_for_existing_typed_executor
```

The exact request must still pass the existing typed executor's separate authorization,
request binding, hardcoded dispatch, ledger transaction and pinned report verification.

## Threat boundary

The design assumes the expected mission SHA-256 arrives through an external operational
trust channel. The code proves consistency under that supplied root; it does not
authenticate the root supplier's identity or secure the supplying channel.

```text
mission-rooted request-authorship eligibility
≠ authenticated human delegation identity
≠ execution authorization
≠ experimental evidence
≠ scientific truth
≠ positive closeout
```

Any future safe action or authority widening requires a new versioned contract,
hardcoded compiler and independent-verifier changes, downstream executor review and
mutation tests.
