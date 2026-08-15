# Authenticated Epistemic Transition Producer

The authenticated transition producer binds the exact bytes of a transition proposal and a
domain-verification decision v1.1 to an exact directional `inference_edge_id`. It emits that
relation as **diagnostic only**. The producer does not make the relation scientifically true,
does not authorize execution, and does not grant stop/reframe or positive-closeout authority.

## Publication platforms

Atomic no-replace publication is currently supported only on **Windows and Linux**. The public
producer fails closed on other operating systems before transition inputs are consumed. This is
a feature-level restriction; the rest of `materials-data-analyzer` is not thereby declared
Windows/Linux-only. Adding another platform requires a platform-safe atomic no-replace directory
publication primitive plus regression coverage.

## Filesystem trust boundary

The producer assumes exclusive write ownership of its private staging tree from creation through
publication. It is not a sandbox against a hostile process sharing the same OS identity and write
access to that staging parent/tree. No same-identity concurrent-tamper resistance is claimed.

## Inherited provenance

Inherited authenticated lineage is re-authenticated from its exact snapshotted base/proposal/
verifier bytes before republishing. The stored binding must equal the recomputed binding, artifact
hashes must be canonical SHA-256 text, and result snapshot role/hash identities must match the
exact proposal. This establishes byte/identity coherence only; `verifier_id` remains free text and
no institutional credential authority is inferred.

## Evidence-node limitation

Inherited `evidence` nodes are currently rejected. Their existing `evidence_binding` contract is
workstream/role/SHA only and has no first-class resolvable artifact path/origin binding, so the
producer cannot make those nodes self-contained without inventing provenance. A later evidence
origin contract must provide checksum-bound resolvable artifacts before this restriction can be
removed. The same principle is why new `empirical_derived` authenticated transitions remain
fail-closed in this producer.

## Historical replay validation

Inherited authenticated lineage is accepted only when its exact historical base graph can be
materialized against the enclosing graph's still-operative artifact bindings and passes the graph
validator, its exact proposal passes the full transition proposal contract using the snapshotted
result artifacts, and its v1.1 decision passes both exact-edge authentication and the established
scope validator. The historical result node, tests edge, and diagnostic inference edge must also
be present with matching semantics in the enclosing graph. Copying a self-consistent lineage
record into an unrelated graph is therefore not sufficient.

Any inherited or current transition carrying unresolved `input_evidence_bindings` remains
fail-closed until the separate evidence-origin contract provides checksum-bound resolvable input
snapshots. Existing inherited `domain_verified` relations from the legacy graph contract may still
retain their prior evaluator authority; the authenticated producer reports that retention explicitly
and does not describe those relations as re-authenticated v1.1 authority.

## Authenticated graph-chain continuity

Inherited authenticated transitions must form a consecutive suffix of the legacy transition
lineage. For each hop, the exact historical `parent_graph_id`/SHA must match that record's exact
base snapshot, and the proposal `new_graph_id` must lead to the next authenticated record's exact
base graph. The final inherited hop is anchored to the exact current base bytes/SHA authenticated
by the current v1.1 verifier. Each immediate successor must contain exactly the base structure plus
the authenticated result/tests/diagnostic-inference additions; unrelated grafted structure is
rejected. This provides a forward-anchored graph-ID/SHA replay chain rather than accepting a
self-consistent historical subgraph merely because it appears somewhere in the current graph.

Authenticated lineage records use an exact top-level key set. Unknown authority or credential
claims are rejected instead of being copied through opaque metadata. Exact current-base node
artifact and edge-verifier SHA bindings are also required to be canonical lowercase SHA-256 text
so every published bundle remains consumable by the same replay contract.
