# Independent Authenticated Transition Consumer

`authenticated_transition_consumer` re-authenticates the **current/final transition** in a published authenticated-transition bundle from the bundle's own exact bytes.

It is intentionally separate from the producer. The consumer does not trust producer-returned booleans or treat manifest authority flags as evidence. Its authoritative chain is:

1. `epistemic_graph.json` exact bytes;
2. the final `authenticated_transition_lineage` record;
3. the exact bundle-relative base graph, proposal, v1.1 verifier decision, and result snapshots named by that record;
4. independently recomputed SHA-256 identities;
5. `authenticate_inference_binding()` over the exact proposal and verifier bytes;
6. the realized result node, `tests` edge, and **diagnostic** directional edge in the exact graph;
7. cross-checks against the informational manifest.

## Public API

```python
from materials_data_analyzer.research_loop import authenticate_transition_bundle

report = authenticate_transition_bundle("path/to/authenticated_bundle")
```

The report sets `current_transition_exact_provenance_authenticated: true` only after the current transition is independently reconstructed from the bundle.

## CLI

```text
mda-research-program authenticate-transition-bundle --bundle path/to/authenticated_bundle
```

This subcommand deliberately does **not** require a research mission, repository root, runtime context, research program state, network access, or an execution registry.

## What the consumer proves

For the current transition, it verifies:

- exact base/proposal/verifier/result bytes match their recorded SHA-256 values;
- the v1.1 verifier authenticates the exact `inference_edge_id`, transition, result, target, relation, and base graph;
- the stored authenticated binding equals independent recomputation;
- the final legacy lineage record identifies the same exact transition;
- the exact proposal scope is compatible with the target claim scope under the currently supported producer contract;
- the graph contains the exact normalized result node and `tests` edge;
- the directional relation remains `assessment_level: diagnostic` and has not been silently promoted;
- the manifest's graph and artifact bindings are consistent with the independently verified bundle objects;
- bundle-relative paths do not escape the bundle or traverse symlink/reparse-point components at validation time.

## What it does not prove

A successful report explicitly does **not** establish:

- scientific truth or scientific-status promotion;
- verifier institutional identity, credentials, or independence;
- calibrated scientific confidence;
- support independence;
- empirical origin for `empirical_derived` analysis;
- execution authorization or network/physical-experiment authorization;
- stop/reframe authority;
- positive scientific closeout;
- re-authentication of the entire historical authenticated-lineage chain;
- bundle immutability after the consumer returns;
- resistance to a hostile concurrent writer with permission to mutate the bundle during validation.

The consumer remains provenance-only. A later Scientific Critic authority adapter may use the consumer as a prerequisite, but that adapter must call this consumer itself rather than trusting a caller-supplied report dictionary.

## Evidence-origin boundary

The current producer intentionally rejects unresolved input evidence and `empirical_derived` transitions because the existing evidence binding lacks a first-class checksum-bound, resolvable origin artifact contract. This consumer preserves that fail-closed boundary. A separate evidence-origin contract is required before empirical-derived authority can be enabled.
