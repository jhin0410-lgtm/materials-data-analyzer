# Materials Structure Enrichment

Status: `v2.2.4_complete`

v2.2.4 executes a controlled Materials Project enrichment for the existing
v1.3/v2.2 838 material IDs only. It does not expand the query universe, run a
new chemical-system search, or add new material IDs.

## Acquisition Boundary

The allowed mode is `enrich_existing_ids`. Network execution requires an
explicit `--execute`, a local `MP_API_KEY`, a bounded `max_records` no larger
than the existing ID count, and an allowlisted field set.

Credential values are never stored in tracked configs, manifests, compact
outputs, or CLI summaries.

## Actual v2.2.4 Result

- requested unique material IDs: 838
- returned current API documents: 838
- missing IDs: 0
- duplicate returned IDs: 0
- chunk count: 17
- valid `CrystalStructureEntity` conversions: 838
- reduced composition matches: 838
- ordered structures: 838
- disordered structures: 0

The row-level API chunks and converted entities are local-only under:

```text
outputs/materials_project_structure_v2_2/
```

## Snapshot Alignment

The current API `energy_above_hull` is audit-only. The original v1.3 target is
not overwritten.

Actual alignment against the existing target:

- exact target matches: 257
- within numeric tolerance: 581
- target drift: 0
- snapshot-aligned future cohort candidate: 838

Source version metadata remains unavailable for this comparison, so future
structure-aware work should still state that it combines the original modeling
target with a current structure snapshot after an explicit drift audit.

## Claim Boundary

The enrichment demonstrates bounded structure availability and conversion. It
does not demonstrate structure-aware predictive improvement, phase stability
model quality, DFT replacement, or new-material discovery.
