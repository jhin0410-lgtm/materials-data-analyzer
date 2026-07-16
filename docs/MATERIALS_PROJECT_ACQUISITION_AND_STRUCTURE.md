# Materials Project Acquisition And Structure Plan

Status: `v2.2.3_complete`

v2.2.3 separates three Materials Project modes:

- `audit_existing`: read tracked v1.3 manifests and compact artifacts only.
- `enrich_existing_ids`: future credential-gated enrichment for the current 838 material IDs.
- `expand_query_universe`: future planning only; no broad query is executed in this step.

## Existing-ID Enrichment Boundary

Future structure enrichment must be bounded to existing material IDs unless a new access gate approves a broader query. It must request only the fields needed for structure entity conversion:

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

## Local-Only Structure Policy

Real MP structures can be large and may include runtime-specific object representations. Row-level structure payloads must remain local-only under ignored output paths such as:

```text
outputs/materials_project_structure_v2_2/
```

Tracked outputs are limited to compact scope, coverage, adapter, and operator summaries. If no actual API enrichment is executed, coverage must remain `unavailable_no_local_api_data`; synthetic examples cannot be used as acquisition evidence.

## Expansion Plans

The preferred next execution scope is the current 838 material IDs. Broader target-specific or structure-aware datasets are future plans and require separate bias, storage, provenance, and validation review.
