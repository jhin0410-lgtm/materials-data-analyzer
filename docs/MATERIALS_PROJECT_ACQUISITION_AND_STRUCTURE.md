# Materials Project Acquisition And Structure Plan

Status: `v2.2.4_complete`

v2.2.3 separated three Materials Project modes:

- `audit_existing`: read tracked v1.3 manifests and compact artifacts only.
- `enrich_existing_ids`: future credential-gated enrichment for the current 838 material IDs.
- `expand_query_universe`: future planning only; no broad query is executed in this step.

## Existing-ID Enrichment Boundary

Structure enrichment is bounded to existing material IDs unless a new access
gate approves a broader query. It requests only the fields needed for structure
entity conversion and snapshot alignment:

- `material_id`
- `formula_pretty`
- `composition`
- `composition_reduced`
- `chemsys`
- `nelements`
- `structure`
- `symmetry`
- `density`
- `volume`
- current target field and available provenance metadata

API credentials may come only from local secret sources such as `MP_API_KEY`. Key values must not be stored in tracked configs, logs, manifests, exceptions, or compact outputs.

## v2.2.4 Bounded Execution

v2.2.4 executed `enrich_existing_ids` for the existing 838 Materials Project
material IDs. The current API returned 838 documents, with no missing or
duplicate returned IDs. The row-level structure chunks were converted into 838
valid JSON-safe `CrystalStructureEntity` records.

The current API `energy_above_hull` values were used only for drift audit. The
original v1.3 target was not overwritten. Alignment summary:

- exact target matches: 257
- within numeric tolerance: 581
- target drift: 0
- snapshot-aligned future cohort candidate: 838

## Local-Only Structure Policy

Real MP structures can be large and may include runtime-specific object representations. Row-level structure payloads must remain local-only under ignored output paths such as:

```text
outputs/materials_project_structure_v2_2/
```

Tracked outputs are limited to compact scope, coverage, descriptor, graph,
alignment, and operator summaries. If no actual API enrichment is executed in a
future environment, coverage must remain `unavailable_no_local_api_data`;
synthetic examples cannot be used as acquisition evidence.

## Expansion Plans

The current 838 material IDs are now enriched for structure-readiness review.
Broader target-specific or structure-aware datasets are future plans and
require separate bias, storage, provenance, and validation review.

## v2.2.5 Use

v2.2.5 uses the v2.2.4 snapshot-aligned cohort for a bounded
known-structure post-relaxation comparison. It keeps the original v1.3 target
as the modeling label, treats current API target values as audit-only, and
records `structure_predictive_value_limited`. The comparison does not use
periodic graph artifacts as model inputs and does not claim GNN evidence or
DFT replacement.
