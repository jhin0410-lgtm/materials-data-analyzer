# Materials Known-Structure Prediction Context

Status: `v2.2.5_complete`

v2.2.5 keeps two Materials prediction contexts separate.

## Composition-Only Pre-Structure

`composition_only_pre_structure` uses formula and composition-derived static
elemental summaries before a crystal structure is known. This is the v2.2.1
context. Its preserved conclusion remains `performance_degraded`: the selected
composition physics features did not improve the matched primary validation,
and no representative physics-aware model was selected.

## Known-Structure Post-Relaxation

`known_structure_post_relaxation` assumes a structure is already known or has
already been calculated. v2.2.5 uses the v2.2.4 snapshot-aligned cohort and
Tier-1 structure descriptors in this separate context only.

This context is not pre-structure screening. MP relaxed structures should not
be treated as available at the same time as a composition-only candidate
screening task.

## Claim Boundary

v2.2.5 may support a bounded statement about whether known-structure
descriptors add value on the existing group-aware validation problem. It does
not support:

- DFT replacement
- phase-stability guarantee
- synthesizability prediction
- graph neural network evidence
- hybrid physics-ML claim
- causal mechanism claim
- use of current API target values as replacement labels

The original v1.3 `energy_above_hull` target remains the modeling target.
Current MP target values are audit-only snapshot-alignment metadata.
