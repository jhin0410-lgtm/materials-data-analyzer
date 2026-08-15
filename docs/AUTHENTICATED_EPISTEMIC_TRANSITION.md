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
