# Evidence Provider Controller Integration

## Purpose

This layer connects authenticated `ProviderState` requirements to the public recursive
research controller without turning provider metadata into action candidates, empirical
evidence, or scientific authority.

It builds on the generic Evidence Provider Contract and the provenance-aware Comparability
Engine.

## Planning overlay

`build_provider_planner_program_state()` converts each authenticated provider requirement into
one deterministic planner goal and evidence gap.

The generated provider goal always has:

- exact provider-state SHA ancestry;
- the aggregate requirement identifier;
- requirement/action semantics copied as planning metadata;
- `action_frontier=[]`;
- `candidate_availability_asserted=false`;
- `authorization_granted=false`.

Therefore a provider requirement can make an unknown or blocker visible to the planner, but it
cannot manufacture an executable candidate.

If no independently available action exists, the existing autonomous planner stops with
`no_affordable_informative_action` rather than fabricating an action.

## Exact candidate matching

The normal public recursive candidate-match boundary is unchanged.

A selected action must still be:

1. present in the independently reconstructed planner ranked actions;
2. the exact selected planner candidate;
3. uniquely compatible with the validated discrepancy objective;
4. SHA-bound to the planning handoff, source discrepancy report, selected candidate, and
   matched objective;
5. separately authorized before execution.

Provider goals are never inserted into the action frontier, so this layer cannot bypass that
path.

## Persistent research state

When authenticated provider inputs are supplied to
`build_public_recursive_planning_checkpoint()`, the controller:

1. reconstructs the provider aggregate from externally trusted ProviderState SHA roots;
2. verifies that the planner program contains the exact provider overlay and no provider-created
   candidates;
3. persists the complete provider requirement aggregate and overlay verification inside
   `recursive_checkpoint.persistent_research_state.evidence_provider_state`;
4. binds the resulting checkpoint through the existing checkpoint SHA and recursive resource
   budget.

The planning context serializes the exact ProviderStates and their trusted SHA roots so the next
cycle can independently reconstruct the same provider aggregate.

If a successor planning context omits explicit provider inputs, the exact predecessor provider
inputs are inherited. The current planner program must still contain the matching provider
overlay; silently dropping provider requirements fails closed.

## Single-provider transitions

`build_provider_state_transition()` and `apply_provider_state_transition()` support an
authenticated replacement of exactly one existing provider identity.

The transition records:

- previous and current provider-state SHA;
- previous and current aggregate SHA;
- all unchanged provider-state SHA ancestry;
- whether the provider state actually changed;
- whether provider-derived replanning is required.

A replacement cannot add an unknown provider under the guise of an update.

If the replacement SHA is identical to the previous state, the transition reports:

- `state_changed=false`;
- `next_planning_cycle_required=false`;
- `stop_reason=no_new_provider_information`.

This provider-specific stop signal does not override independent new information from a model,
execution, or epistemic transition. It prevents provider metadata churn alone from creating a
new research cycle.

`build_provider_successor_planner_program_state()` enforces this boundary for provider-only
updates: when the replacement ProviderState SHA is unchanged it returns no successor planner
program at all. When the state changes, it builds a new provider overlay without creating candidate
actions. The exact transition remains a separate authenticated object inside the canonical-SHA-bound
successor bundle and, for recursive cycles, is also bound through the planning-context ancestry.
The complete successor bundle can be independently replayed with
`validate_provider_successor_planner_program_state()`.

## Re-diagnosis boundary

A post-transition domain provider may issue a new ProviderState only through its own existing
verification/trust boundary. The generic controller does not infer that a model execution,
graph-version change, file count, or newly named artifact changed a provider's scientific state.

After such an externally authenticated replacement, only the matching provider identity may be
updated. The new provider set is then re-aggregated and projected into the next planner program.

## Authority boundary

Provider-controller composition never:

- creates empirical measurements;
- promotes scientific status;
- asserts candidate availability;
- grants authorization;
- compiles an execution request;
- performs network access or equipment control;
- converts graph/version churn into scientific information;
- treats planning metadata as causal, predictive, or engineering validation.

The existing recursive resource budget, deterministic plan reconstruction, exact candidate
matching, authorization, typed execution, epistemic transition, and bounded stopping mechanisms
remain authoritative.
