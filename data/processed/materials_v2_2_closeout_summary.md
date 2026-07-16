# Materials v2.2 Scientific Trust Closeout

- release readiness: `release_ready`
- composition context decision: `performance_degraded`
- known-structure context decision: `structure_predictive_value_limited`
- representative model: `none`
- graph/GNN evidence: `none`; periodic graph artifacts remain representation-only
- target policy: original v1.3 `energy_above_hull` remains source of truth; current API target is audit-only

## Prediction Contexts

- `composition_only_pre_structure`: composition physics descriptors were evaluated and predictive improvement was not supported
- `known_structure_post_relaxation`: structure descriptors gave limited evidence in one primary group split only

## Evidence Levels

- `composition_feature_builders`: `predictive_value_not_supported`
- `structure_descriptors`: `predictive_value_limited`
- `periodic_graph_artifacts`: `artifact_generated`
- `known_structure_prediction`: `predictive_value_limited`
- `prediction_intervals`: `evaluated`
- `representative_model`: `unavailable`

## Key Counts

- composition feature rows: `838`
- structure returned documents: `838`
- known-structure cohort rows: `838`
- graph artifacts: `838`

## Boundary

Prediction intervals are residual diagnostics in `eV/atom`, not DFT uncertainty, source uncertainty, or experimental uncertainty. The v2.2 closeout preserves negative and limited results rather than promoting them into a representative model.
