# ADR: Canonical Scientific Control Plane

Status: proposed for Issue #234

## Decision

`materials-data-analyzer` uses one conceptual Autonomous Research Scientist control plane. Existing ledgers, planning transitions, bounded cycles, authenticated epistemic transitions, and mission-specific autonomous-production extensions remain replay-compatible implementations or primitives of that control plane; they are not competing definitions of research truth.

The canonical scientific state is multidimensional. It distinguishes research questions, bounded missions, hypotheses, observations, derived results, evidence, claims, inferences, contradictions, comparability assessments, uncertainty state, evidence gaps, candidate actions, decisions, and stop state. A one-dimensional readiness ladder may summarize that state for a provider or release decision, but it is not the canonical research state.

## Canonical state machine

```text
DEFINE / LOAD MISSION
-> FORM / LOAD HYPOTHESES
-> MAP VERIFIED EVIDENCE + GAPS
-> GENERATE ACTION FRONTIER
-> SELECT SCIENTIFIC ACTION
-> AUTHORIZE SELECTED ACTION
-> EXECUTE AUTHORIZED ACTION
-> INDEPENDENTLY VERIFY RESULT
-> INGEST VERIFIED EVIDENCE
-> APPLY EPISTEMIC UPDATE
-> CRITIQUE / FALSIFY
-> REPLAN
-> CLASSIFY STOP OR CONTINUE
```

This ADR does not claim every current implementation already performs every stage generically. It fixes the target semantics so future work does not add another competing controller.

## Science Plane

The Science Plane owns questions and hypotheses, observations and derived results, evidence and claims, inferences, contradictions and alternative hypotheses, comparability, uncertainty, evidence-gap diagnosis, scientific action value, and scientific stopping semantics.

Its central question is:

> Given the verified state, what research action should be attempted next?

The Science Plane does **not** grant network, filesystem, execution, budget, or physical-experiment authority.

## Governance Plane

The Governance Plane owns provenance authentication, source/access policy, execution authorization, execution limits, resource budgets, filesystem and transaction integrity, operational recovery, and audit.

Its central question is:

> May the already-selected action execute under the authenticated policy and available resources?

The Governance Plane does **not** decide that an action is scientifically valuable merely because it is authorized, and it cannot promote an artifact into scientific truth.

## Provider authority boundary

The required direction is:

```text
Provider / Executor
-> Raw ArtifactBundle
-> Independent Domain Validator
-> Validated EvidencePacket
-> Epistemic Kernel
```

A provider may produce data and domain-specific verification artifacts. It may not make its own execution success sufficient proof of scientific validity. A checksum, successful transport, successful parser run, readiness projection, reasoning proposal, or simulation result does not automatically become empirical evidence.

The canonical `EvidencePacket` is intentionally deferred to Issue #235. The Comparability Engine is intentionally deferred to Issue #236. This ADR prevents those contracts from inheriting provider-specific or transport-specific authority by accident.

## Readiness projections

The characterization L0-L8 evidence ladder remains useful and is explicitly retained as a monotonic readiness projection. It answers which prerequisites are supported for a characterization source/result. It is not the complete internal research state because calibration, material match, uncertainty, independence, replication, preprocessing, method validity, and claim scope may be unresolved on separate dimensions.

Therefore:

- readiness projection != canonical research state;
- readiness projection != downstream-use authorization;
- readiness projection != scientific-status promotion.

## Existing controller inventory

| Surface | Classification | Canonical role |
|---|---|---|
| immutable research-loop kernel/ledger | canonical primitive | append-only authenticated research state/history |
| mission-level research program | canonical primitive | mission and reasoning-proposal contract |
| `run_research_cycle()` | canonical primitive | at most one explicit authorized action, then one replan |
| policy-authorized closed loop | compatibility facade | bounded controller over historical planning/authorization contracts |
| autonomous-production extensions | domain implementation | mission-pinned real-evidence production extensions |
| planning-adapter facade | compatibility facade | historical plus typed domain planning projection |
| authenticated epistemic transition | canonical primitive | authenticated verified-evidence-to-state transition |

This classification is architectural, not a deprecation notice. Historical public artifacts and APIs remain unchanged unless a later migration supplies an explicit compatibility path.

### `run_research_cycle()` is not a second product controller

`run_research_cycle()` intentionally executes at most one explicit typed action, does not create an execution request for the caller, does not loop automatically, and replans once. It remains the safe single-step primitive under the larger control-plane semantics.

## Terminal vocabulary

The canonical vocabulary distinguishes why research stops instead of treating every stop as equivalent:

- `converged`
- `decision_threshold_reached`
- `irreducible_uncertainty`
- `contradictory_evidence`
- `blocked_external_evidence`
- `review_required`
- `resource_budget_exhausted`
- `marginal_information_value_too_low`
- `authorization_or_safety_blocked`

Historical planning statuses are not rewritten. `manual_review_gate` maps unambiguously to `review_required`. `operationally_blocked` and `terminal_for_current_scope` remain semantically unresolved until their historical reason/blocker provides enough evidence to choose a stronger canonical class. This prevents a compatibility projection from inventing scientific convergence.

## Why this is additive

Current research artifacts are SHA-bound and replayable. Rewriting old status fields would damage provenance and can silently alter scientific meaning. The initial implementation therefore adds `scientific_control_plane.py` as a deterministic architecture contract while leaving existing transition schemas untouched.

Future work may project current state into this vocabulary, but the projection must preserve source artifact identity and must not mutate historical records.

## Invariants

1. Science decides **should**; Governance decides **may**.
2. Science does not grant execution authority.
3. Governance does not grant scientific authority.
4. Provider execution does not self-validate scientific truth.
5. Architecture metadata creates no empirical evidence.
6. Successful transport creates no scientific validity.
7. Readiness projections do not become canonical state.
8. Ambiguous historical stops do not receive invented convergence semantics.
9. Mission-specific autonomous-production code remains a domain implementation, not the generic epistemic model.
10. New providers must eventually enter through the generic contracts in #235, #236, and #207 instead of adding new core planner branches.

## Consequences

The immediate cost is that some current controller terminology remains duplicated while compatibility is preserved. That is intentional. Refactoring can now be evaluated against a stable target instead of changing architecture and implementation simultaneously.

The next implementation order is:

1. Issue #235: `EvidencePacket v1` plus independent validator.
2. Issue #236: provenance-aware Comparability Engine.
3. Issue #207: generic Evidence Provider Contract.
4. multidimensional hypothesis/claim/evidence graph and persistent multi-gap state.
5. action-frontier information-value/cost/risk ranking.
6. falsification/alternative-hypothesis critic.
7. uncertainty engine and scientific research-competency benchmark.

## Scientific boundary

This ADR and its machine-readable contract are architecture metadata only. They create no measurement, no empirical evidence, no new IN625 comparability bridge, no calibration relation, no predictive/causal/engineering authorization, and no closure of external TEM/SAED evidence blockers.
