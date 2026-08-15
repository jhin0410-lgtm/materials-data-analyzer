# Independent Authenticated Transition Consumer

`authenticated_transition_consumer` re-authenticates the **current/final transition** in a published authenticated-transition bundle from the bundle's own exact bytes.

It is intentionally separate from the producer. The consumer does not trust producer-returned booleans or treat manifest authority flags as evidence. Its authoritative chain is:

1. `epistemic_graph.json` exact bytes;
2. the final `authenticated_transition_lineage` record;
3. the exact bundle-relative base graph, proposal, v1.1 verifier decision, and result snapshots named by that record;
4. independently recomputed SHA-256 identities;
5. `authenticate_inference_binding()` over the exact proposal and verifier bytes;
6. the exact successor relation to the bound base graph;
7. the realized result node, `tests` edge, and **diagnostic** directional edge in the exact graph;
8. independent epistemic-graph schema validation of the exact base and successor;
9. cross-checks against the informational manifest.

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
- the exact proposal obeys the producer's action/execution/result-origin compatibility rules;
- the exact proposal scope is compatible with the target claim scope under the currently supported producer contract;
- the successor node set is exactly the bound base plus one result node;
- the successor edge set is exactly the bound base plus one `tests` edge and one diagnostic directional edge;
- inherited node/edge semantic identity is preserved, with bundle-path relocation allowed only where artifact/verifier role+SHA identity is unchanged;
- non-lineage graph metadata is preserved and legacy/authenticated lineage is extended by exactly one current-transition record;
- the graph contains the exact normalized result node and `tests` edge;
- the directional relation remains `assessment_level: diagnostic` and has not been silently promoted;
- both the exact bound base and final successor satisfy the epistemic-graph schema after more-specific checksum/append/edge checks have run;
- the manifest's graph and artifact bindings are consistent with the independently verified bundle objects;
- bundle-relative paths do not escape the bundle, traverse symlink/reparse-point components, use Windows alternate-data-stream/reserved forms, or contain other Windows-nonportable components at validation time.

## What it does not prove

A successful report explicitly does **not** establish:

- scientific truth or scientific-status promotion;
- verifier institutional identity, credentials, or independence;
- calibrated scientific confidence;
- support independence;
- independently established empirical origin;
- execution authorization or network/physical-experiment authorization;
- stop/reframe authority;
- positive scientific closeout;
- re-authentication of the entire historical authenticated-lineage chain;
- bundle immutability after the consumer returns;
- resistance to a hostile concurrent writer with permission to mutate the bundle during validation.

The consumer remains provenance-only. A later Scientific Critic authority adapter may use the consumer as a prerequisite, but that adapter must call this consumer itself rather than trusting a caller-supplied report dictionary.

## Evidence-origin boundary

Both `empirical_derived` and `empirical_direct` remain fail-closed. A proposal label such as `external_physical_experiment`, a filename, a role name, or opaque metadata is not independent evidence of empirical origin.

The current producer also rejects unresolved input evidence because the legacy evidence binding lacks a first-class checksum-bound, resolvable origin-artifact contract. A separate evidence-origin provenance contract is required before any later policy can consider empirical inference authority, and that contract must not by itself be confused with physical truth, verifier credentials, result validity, or positive scientific closeout.
