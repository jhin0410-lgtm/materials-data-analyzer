# Platform v2.2 Closeout

Status: `release_ready`.

v2.2 closes the first Materials physics-aware evidence cycle. It adds
composition-derived features, scientific entity and quantity contracts,
controlled Materials Project structure enrichment, known-structure descriptor
comparison, and a machine-readable trust closeout.

## Final Decisions

- Composition-only pre-structure context: `performance_degraded`.
- Known-structure post-relaxation context: `structure_predictive_value_limited`.
- Representative model: `none`.
- Graph/GNN evidence: none; graph artifacts are representation-only.
- DFT replacement, phase-stability guarantee, synthesizability prediction, SHAP,
  physics-constrained modeling, and hybrid physics-ML claims remain prohibited.

## Closeout Outputs

- `data/platform/v2_2_capability_matrix.json`
- `data/platform/materials_prediction_context_registry_v2.json`
- `data/processed/materials_v2_2_capability_matrix.json`
- `data/processed/materials_v2_2_evidence_summary.json`
- `data/processed/materials_v2_2_claim_matrix.json`
- `data/processed/materials_v2_2_uncertainty_boundary.json`
- `data/processed/materials_v2_2_prediction_contexts.json`
- `data/processed/materials_v2_2_closeout_decision.json`
- `data/processed/materials_v2_2_closeout_summary.md`

These artifacts are compact summaries. They contain no row-level material IDs,
targets, predictions, structure bodies, graph bodies, API keys, or local paths.

## CLI

```powershell
python -m src.cli audit-v2-2-scientific-evidence
python -m src.cli show-v2-2-capability-matrix
python -m src.cli show-v2-2-claim-matrix
python -m src.cli show-v2-2-prediction-contexts
python -m src.cli show-v2-2-uncertainty-boundaries
python -m src.cli validate-v2-2-artifact-lineage
python -m src.cli validate-v2-2-result-preservation
python -m src.cli export-v2-2-closeout-summary
python -m src.cli evaluate-v2-2-release-readiness
```

All commands read tracked compact artifacts only. They do not call the
Materials Project API, regenerate descriptors, load graph bodies, train models,
or recompute predictions.

## Release Boundary

`release_ready` means the evidence contracts, claim boundaries, artifact
lineage, and documentation are internally consistent. It does not mean that a
useful physics-aware predictive model exists. The negative and limited results
are part of the release.

Future v2.3 work should focus on PGIR/RFC-style representation governance and
broader evidence requirements before any graph model, physics-constrained
model, or richer structure-aware learning claim is attempted.
