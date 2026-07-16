# Materials Prediction Contexts

Status: `v2.2.5_complete`

Materials v2.2 now separates two scientific prediction contexts that should not
be mixed.

## Composition-Only Pre-Structure

`composition_only_pre_structure` is the v2.2.1 context. Inputs are formula,
composition, and static elemental-property summaries available before a
structure is known or relaxed.

The current conclusion is preserved:

- composition-derived physics features did not improve the matched primary
  validation.
- the decision remains `performance_degraded`.
- no representative model, physics-constrained model, or hybrid physics-ML
  claim is selected.

## Known-Structure Post-Relaxation

`known_structure_post_relaxation` is a separate context. Inputs may
include Materials Project relaxed structures, structure descriptors, and
periodic graph artifacts after a structure exists.

This context is not a replacement for DFT and is not a pre-structure screening
claim. Relaxed MP structures are not available at the same prediction time as
composition-only candidate screening unless the task explicitly assumes a known
or calculated structure.

## v2.2.4 Boundary

v2.2.4 performs bounded structure enrichment for the existing 838 Materials
Project material IDs, checks snapshot alignment, converts structures into
JSON-safe entities, builds descriptor candidates, and writes periodic graph
artifacts locally.

It does not train a structure-aware model, claim descriptor value, claim GNN
evidence, or overwrite the original target.

## v2.2.5 Boundary

v2.2.5 runs the first known-structure post-relaxation comparison on the
snapshot-aligned 838-row cohort. The result is
`structure_predictive_value_limited`: structure descriptors improved one
primary group split only, and no representative model was selected.

This does not change the v2.2.1 composition-only result, which remains
`performance_degraded`.
