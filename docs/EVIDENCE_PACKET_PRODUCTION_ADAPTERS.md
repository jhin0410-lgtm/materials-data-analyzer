# EvidencePacket Production Adapters

## Purpose

EvidencePacket v1 is provider-independent. Domain adapters live outside the core validator and
may only preserve authority that was already established by an upstream scientific/provenance
contract.

This document records the first two real-system production adapters required by issue #235.

## NIST AM-Bench 2018-02 IN625 trace adapter

`build_nist_ambench_trace_evidence_packets()` converts the reviewed ten-trace NIST AM-Bench
case-study tables into one EvidencePacket per tracked AMMT trace.

Before packet creation the adapter verifies the exact repository source bytes against both pinned
Git blob identities and pinned raw-byte SHA-256 digests for:

- the process-condition CSV;
- the melt-pool measurement CSV;
- the reviewed case-study README;
- the planning-readiness contract.

The Git blob identity binds the reviewed repository object; SHA-256 is the scientific artifact
identity used throughout EvidencePacket provenance.

It also verifies the ten-trace identity join, IN625/AMMT identity, the exact three tracked process
conditions, experimental-context text, and the descriptive-only scientific-use boundary.

Each packet preserves:

- material/sample/case/trace identity;
- actual laser-power and scan-speed values from the tracked source table;
- source-reported melt-pool width/depth means;
- source-reported trace standard deviations;
- exact SHA-256 source bindings;
- calibration as `unknown`;
- comparison as `not_assessed`;
- explicit limitations and descriptive-only scope.

### Authority boundary

The packets are empirical measurement packets because they carry existing physical measurements,
but the adapter deliberately keeps:

- `scientific_status_promoted=false`;
- `downstream_use_authorized=false`;
- `row_level_measurement_authority=false`.

The tracked CSVs are reviewed manual transcriptions from official NIST result pages, not official
raw row artifacts. Creating an EvidencePacket therefore does not promote them to a stronger
row-level authority class.

`build_nist_ambench_trace_validation_material()` returns the packet, exact artifact bytes, and
validation expectation object. It does **not** return or generate a trusted expectation digest.
Any authority-bearing consumer must independently pin/authenticate the complete expectation object
before invoking the authenticated EvidencePacket validator. Producer-side packet+expectation
rehashing is not a trust root.

The regression test may compute the digest locally to exercise the validator API, but that test
digest is explicitly **not** production authority. A production consumer must obtain the digest
from Governance, a mission-pinned immutable record, a signed/attested receipt, or another trust
boundary outside the adapter output.

## Characterization L0-L8 adapter

`build_characterization_planning_evidence_packet()` first invokes the independent
characterization evidence-ladder verifier, then adapts the verified readiness state into a
`planning_metadata` EvidencePacket.

The packet binds the complete verified assessment bytes and records the highest supported evidence
level plus the first blocker. It deliberately carries zero empirical/scientific/downstream
authority:

- `empirical_evidence_created=false`;
- `scientific_status_promoted=false`;
- `downstream_use_authorized=false`;
- `planning_metadata_only=true`;
- `row_level_measurement_authority=false`;
- `authority_source=none`.

L0-L8 maturity remains a readiness projection rather than canonical scientific truth.

## Deterministic heat-conduction reference fixture

`build_heat_conduction_reference_evidence_packet()` adapts the existing audited one-dimensional
heat-diffusion reference solver into an EvidencePacket fixture only after the deterministic run
completes, satisfies the FTCS stability criterion, and passes its analytical sine-eigenmode
validation.

The resulting packet is `simulation_result`, not empirical evidence. It binds the canonical
solver request and deterministic result bytes and records numerical validation error plus the FTCS
Fourier number as derived results.

Its authority remains entirely false:

- `empirical_evidence_created=false`;
- `scientific_status_promoted=false`;
- `downstream_use_authorized=false`;
- `row_level_measurement_authority=false`;
- `authority_source=none`.

The fixture explicitly excludes LPBF melt-pool physics, phase change, material calibration, IN625
predictive validation, and engineering use. Analytical numerical agreement is not empirical
validation.

## Core validator separation

The generic EvidencePacket validator contains no NIST- or characterization-specific branches.
Domain adapters create packets; the generic validator independently checks the typed contract,
canonical self-hash, exact artifact bindings, units, uncertainty/calibration declarations,
lineage, explicit authority flags, and externally authenticated expectations for authority-bearing
packets.

Comparability remains a separate downstream operation. A valid packet is not automatically
comparable, independent, causal, predictive, or engineering-ready.

## Existing negative controls

The EvidencePacket core already rejects, among other attacks:

- source role/path/SHA substitution;
- provider/material/subject substitution;
- unit and calibration drift;
- uncertainty promotion;
- simulation-to-empirical promotion;
- literature-to-row-level promotion;
- duplicate source-family independence claims;
- unknown-field and packet self-hash tampering.

The production-adapter regression suite adds:

- NIST source-byte drift before packet creation;
- rehashed NIST measurement substitution against the original expectation root;
- characterization scientific-status promotion before adaptation;
- planning-metadata-to-empirical authority promotion.

## Scientific boundary

These adapters improve typed transport and replay of existing evidence. They do not discover new
measurements, establish cross-source comparability, transfer calibration, infer independence, fit a
predictive model, or authorize engineering use.
