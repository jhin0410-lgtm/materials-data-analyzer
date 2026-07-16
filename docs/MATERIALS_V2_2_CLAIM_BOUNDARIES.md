# Materials v2.2 Claim Boundaries

Status: `release_ready`.

## Allowed

- Materials Project scope was audited as an 838-row Fe/Si-containing multinary
  subset.
- Composition-derived physics features were generated and used in a matched
  comparison.
- Controlled structure enrichment returned current structures for the existing
  838 material IDs.
- `CrystalStructureEntity` records, Tier-1 structure descriptors, and
  deterministic periodic graph artifacts were generated.
- Known-structure group-aware comparison and prediction-interval diagnostics
  were completed.

## Limited

- Structure predictive value is `structure_predictive_value_limited`, not
  broadly supported. Improvement appeared in one primary group split only.
- Structured uncertainty is supported as metadata and prediction-interval
  diagnostics, while source uncertainty remains unavailable.

## Unsupported Or Prohibited

- composition physics predictive-value success
- representative Materials Project model
- graph model or GNN validation
- physics-constrained model
- hybrid physics-ML
- pre-structure stability screening validation
- phase-stability guarantee
- synthesizability prediction
- DFT replacement
- causal structure-property mechanism proof
- production scientific decision

The phrase "physics-informed feature used" is not equivalent to a
physics-constrained model, a hybrid physics-ML model, or a DFT surrogate.
