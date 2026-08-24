# ADR: Canonical Scientific Control Plane

Status: proposed for Issue #234

## Decision

`materials-data-analyzer` uses one conceptual Autonomous Research Scientist control plane. Existing ledgers, planning transitions, bounded cycles, installed multicycle controllers, persistent research episodes, diagnostic authenticated-transition bundles, and mission-specific autonomous-production extensions remain replay-compatible implementations, facades, or primitives of that control plane; they are not competing definitions of scientific truth.

The canonical scientific state is multidimensional. It distinguishes research questions, a scientific mission, hypotheses, observations, derived results, evidence, claims, inferences, contradictions, comparability assessments, uncertainty state, evidence gaps, candidate actions, and decisions. Operational run lifecycle and scientific stopping disposition are deliberately separate state dimensions rather than scientific-state nodes.

The current historical `bounded mission` artifact is a composite compatibility contract: its objective/scope/success criteria project into the Science Plane, while autonomy policy, source/access trust pins, and request-delegation policy project into Governance. Preserving the legacy bytes does not make those policy fields Science-owned.

## Canonical state machine

```text
DEFINE / LOAD SCIENTIFIC MISSION
-> FORM / LOAD HYPOTHESES
-> MAP VALIDATED EVIDENCE + GAPS
-> GENERATE ACTION FRONTIER
-> SELECT SCIENTIFIC ACTION
-> AUTHORIZE SELECTED ACTION
-> EXECUTE AUTHORIZED ACTION
-> INDEPENDENTLY VERIFY RESULT
-> INGEST VALIDATED EVIDENCEPACKET
-> APPLY AUTHORITY-BEARING EPISTEMIC UPDATE
-> CRITIQUE / FALSIFY
-> REPLAN
-> CLASSIFY SCIENTIFIC STOP OR CONTINUE
```

Operational lifecycle events such as interruption, execution failure, operator stop, or checkpoint blocking are recorded orthogonally. They may stop automation without implying scientific convergence, irreducible uncertainty, or any other scientific stopping disposition.

This ADR does not claim every current implementation already performs every stage generically. It freezes target semantics so future work does not add another competing controller or authority path.

## Science Plane

The Science Plane owns research questions; scientific mission objective, scope, and success criteria; hypotheses; observations and derived results; evidence and claims; **inference formation and assessment**; contradictions and alternative hypotheses; comparability; uncertainty; evidence-gap diagnosis; scientific action value; and scientific stopping semantics.

Its central question is:

> Given the independently validated scientific state, what research action should be attempted next and what scientific meaning is justified?

The Science Plane does **not** grant network, filesystem, execution, budget, source-access, request-delegation, or physical-experiment authority.

## Governance Plane

The Governance Plane owns provenance authentication; autonomy/access/delegation policy; source/access policy; execution authorization; execution limits; resource budgets; filesystem and transaction integrity; operational recovery and audit; and run-lifecycle recording.

Its central question is:

> May the already-selected action execute under authenticated policy, authority, safety, and resource constraints?

The Governance Plane does **not** decide that an action is scientifically valuable merely because it is authorized. Authentication or successful execution cannot promote an artifact into scientific truth.

## Legacy mission projection

Current mission files intentionally remain byte-for-byte replayable. Their compatibility projection is split semantically:

```text
Legacy bounded mission
├─ Science projection
│  ├─ research objective
│  ├─ scientific scope
│  └─ scientific success criteria
└─ Governance projection
   ├─ autonomy policy
   ├─ source/access trust policy pins
   ├─ request-delegation policy
   └─ execution constraints
```

The Science projection cannot modify an execution-policy input. A future canonical mission schema may encode the separation directly, but this ADR does not rewrite historical mission artifacts.

## Provider and scientific-authority boundary

The required direction is:

```text
Provider / Executor
-> Raw ArtifactBundle
-> Independent Domain Validator
-> Validated EvidencePacket
-> Authority-bearing Epistemic Update
-> Epistemic Kernel
```

A provider may produce data and domain-specific verification artifacts. It may not make its own execution success sufficient proof of scientific validity. A checksum, authenticated provenance record, successful transport, successful parser run, readiness projection, reasoning proposal, or simulation result does not automatically become validated scientific evidence.

Scientific-state reconstruction therefore requires **validated EvidencePackets and an authority-bearing epistemic update**. Authentication is necessary provenance/governance evidence, not sufficient scientific validation.

The canonical `EvidencePacket` is intentionally deferred to Issue #235. The Comparability Engine is intentionally deferred to Issue #236. This ADR prevents those contracts from inheriting provider-specific or transport-specific authority by accident.

## Diagnostic authenticated transitions

The current `authenticated_epistemic_transition` implementation is retained as a canonical provenance/diagnostic primitive because it authenticates and publishes a diagnostic transition bundle. It explicitly applies **no scientific authority**. Re-authenticating that bundle likewise grants no scientific authority.

Accordingly:

- diagnostic transition != authority-bearing epistemic update;
- authentication != scientific validation;
- a future authority-bearing update must consume validated EvidencePackets and satisfy a separate scientific authority contract.

This distinction prevents a diagnostic edge from becoming scientific state merely because its bytes and lineage are authentic.

## Canonical ResearchRun partition

One product-level `ResearchRun` is partitioned as:

```text
identity
scientific_state
governance_state
run_lifecycle
scientific_stop_disposition
derived_projections
```

Authority sources are explicit:

- `scientific_state`: validated EvidencePackets + authority-bearing epistemic updates;
- `governance_state`: authenticated policy, authorization, execution, resource, transaction, and audit records;
- `run_lifecycle`: authenticated operational lifecycle events;
- `scientific_stop_disposition`: Science Plane assessment over validated scientific state;
- `derived_projections`: non-authoritative views of canonical state.

A run may therefore be operationally `blocked`, `interrupted`, or `execution_failed` while its scientific stop disposition remains `continue` or `undetermined`. Conversely, `converged` is a scientific disposition, not an operational lifecycle code.

## Readiness projections

The characterization L0-L8 evidence ladder remains useful and is explicitly retained as a monotonic readiness projection. It answers which prerequisites are supported for a characterization source/result. It is not the complete internal research state because calibration, material match, uncertainty, independence, replication, preprocessing, method validity, and claim scope may be unresolved on separate dimensions.

Therefore:

- readiness projection != canonical research state;
- readiness projection != downstream-use authorization;
- readiness projection != scientific-status promotion.

## Existing controller inventory

| Surface | Classification | Canonical role |
|---|---|---|
| immutable research-loop kernel/ledger | canonical primitive | append-only authenticated state/history primitive |
| mission-level research program | compatibility facade | legacy composite scientific-mission + governance-policy contract |
| `run_research_cycle()` | canonical primitive | at most one explicit authorized action, then one replan |
| `mda-research-multicycle` / `run_bounded_multicycle()` | compatibility facade | finite predeclared-request controller over the one-action primitive; hard cap 32 |
| `mda-research-epistemic-multicycle` / `run_epistemically_bounded_multicycle()` | compatibility facade | finite epistemic-graph-gated controller over the one-action primitive; hard cap 32 |
| `mda-autonomous-evidence-loop` mission-authorized evidence loop | domain implementation | bounded trusted-source external-evidence loop |
| persistent research episode | canonical primitive | operational lifecycle/iteration checkpoint persistence; not an execution loop by itself |
| policy-authorized closed loop | compatibility facade | bounded controller over historical planning/authorization contracts |
| autonomous-production extensions | domain implementation | mission-pinned real-evidence production extensions |
| planning-adapter facade | compatibility facade | historical plus typed domain planning projection |
| authenticated epistemic transition | canonical primitive | authenticated **diagnostic** transition-bundle producer; scientific authority false |

This classification is architectural, not a deprecation notice. Historical public artifacts and APIs remain unchanged unless a later migration supplies an explicit compatibility path.

### `run_research_cycle()` is not a second product controller

`run_research_cycle()` intentionally executes at most one explicit typed action, does not create an execution request for the caller, does not loop automatically, and replans once. Installed multicycle surfaces are classified explicitly as bounded compatibility controllers built over that primitive rather than silently omitted from the architecture inventory.

## Run lifecycle vs scientific stopping vocabulary

Operational run lifecycle may include:

- `active`
- `blocked`
- `concluded`
- `stopped`
- `interrupted`
- `execution_failed`

These values report what happened to the execution/research process. They are not scientific conclusions.

Scientific stopping dispositions include:

- `continue`
- `undetermined`
- `converged`
- `decision_threshold_reached`
- `irreducible_uncertainty`
- `contradictory_evidence`
- `blocked_external_evidence`
- `review_required`
- `resource_budget_exhausted`
- `marginal_information_value_too_low`
- `authorization_or_safety_blocked`

Historical planning statuses are not rewritten. `manual_review_gate` maps unambiguously to the scientific disposition `review_required`. `operationally_blocked` and `terminal_for_current_scope` remain semantically unresolved until their historical reason/blocker provides enough scientific evidence to choose a stronger disposition. An execution failure or caller stop does not become `converged` merely because automation terminated.

## Frozen machine-readable contract

The control-plane tables use immutable tuple/`NamedTuple` source representations. Builders return fresh dictionaries/lists for consumers, while validation compares against independently reconstructed values from the immutable source representation. A caller mutating a returned contract cannot mutate the frozen source and make later validation accept the drift.

## Why this is additive

Current research artifacts are SHA-bound and replayable. Rewriting old status fields, missions, or diagnostic transition schemas would damage provenance and can silently alter scientific meaning. The initial implementation therefore adds deterministic architecture contracts while leaving historical schemas untouched.

Future work may project current state into this vocabulary, but the projection must preserve source artifact identity and must not mutate historical records.

## Invariants

1. Science decides **should**; Governance decides **may**.
2. Science does not grant execution authority.
3. Governance does not grant scientific authority.
4. Inference formation and assessment is Science-owned.
5. Legacy mission execution-policy fields remain Governance-owned even when stored in one historical mission artifact.
6. Provider execution does not self-validate scientific truth.
7. Authenticated artifact != validated scientific evidence.
8. Diagnostic authenticated transition != authority-bearing epistemic update.
9. Scientific state requires validated EvidencePackets and authority-bearing epistemic updates.
10. Operational lifecycle != scientific stopping disposition.
11. Architecture metadata creates no empirical evidence.
12. Successful transport creates no scientific validity.
13. Readiness projections do not become canonical state.
14. Ambiguous historical stops do not receive invented convergence semantics.
15. Installed looping controllers must be classified explicitly rather than hidden from the canonical inventory.
16. Mission-specific autonomous-production code remains a domain implementation, not the generic epistemic model.
17. New providers must eventually enter through the generic contracts in #235, #236, and #207 instead of adding new core planner branches.

## Consequences

The immediate cost is that some current controller and mission terminology remains duplicated while compatibility is preserved. That is intentional. Refactoring can now be evaluated against a stable authority model instead of changing architecture and implementation simultaneously.

The next implementation order is:

1. Issue #235: `EvidencePacket v1` plus independent validator.
2. Issue #236: provenance-aware Comparability Engine.
3. Issue #207: generic Evidence Provider Contract.
4. multidimensional hypothesis/claim/evidence graph and persistent multi-gap state.
5. action-frontier information-value/cost/risk ranking.
6. falsification/alternative-hypothesis critic.
7. uncertainty engine and scientific research-competency benchmark.

## Scientific boundary

This ADR and its machine-readable contracts are architecture metadata only. They create no measurement, no empirical evidence, no new IN625 comparability bridge, no calibration relation, no predictive/causal/engineering authorization, and no closure of external TEM/SAED evidence blockers.
