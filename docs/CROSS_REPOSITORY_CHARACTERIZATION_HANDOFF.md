# Cross-Repository Characterization Handoff

## Purpose

This workflow consumes a versioned bundle produced by the independently installed [`materials-characterization-analyzer`](https://github.com/jhin0410-lgtm/materials-characterization-analyzer) repository.

The repositories exchange files only. They do not import each other's internal modules, share an environment contract, or infer links from row order or filenames.

## Producer bundle

Required sibling files:

```text
characterization_handoff_bundle.json
characterization_features_long.csv
sample_context.csv
case_source_manifest.json
case_analysis_manifest.json
comparability_matrix.csv
```

The bundle manifest must use schema `1.0` and type `materials_characterization_feature_handoff`. It records checksums, sizes, exact columns, counts, instruments, quality flags, producer versions, evidence references, join policy, and the producer scientific closeout.

## Consumer command

```powershell
python scripts/consume_characterization_handoff_bundle.py `
  --bundle-manifest <producer-result>/characterization_handoff_bundle.json `
  --output outputs/cross-repository-characterization
```

The output directory must be absent or empty. Existing files are never removed or silently overwritten.

## Validation sequence

```text
bundle schema/type
-> sibling-path and symlink boundary
-> every recorded SHA-256 and file size
-> exact 12-column long feature schema
-> numeric and finite feature values
-> source-hash and preprocessing coverage
-> unique sample-context IDs
-> exact feature/context sample-ID set agreement
-> explicit unit-label normalization for stable feature keys
-> explicit sample_id handoff
-> wide feature table and integrated sample table
-> consumer summary, report, and manifest
```

The producer feature file is preserved unchanged. Before wide-column key generation, the consumer writes `characterization_features_bundle_input.csv` and applies one explicit lexical rule: every `%` symbol in the unit label becomes the ASCII token `percent`. Examples are `%` → `percent` and `%/degC` → `percent/degC`.

This rule does not change numeric values or physical units. The mappings, affected row count, rule identifier, and `numeric_values_modified = false` are written to both the consumer summary and manifest.

The consumer preserves methods, feature labels, quality flags, source hashes, preprocessing identifiers, and physical unit meaning. It rejects path traversal, row-order joins, duplicate semantic features, silent aggregation, and inferred metadata.

## Public DWCNT end-to-end case

The GitHub Actions workflow `.github/workflows/cross-repository-public-dwcnt.yml` performs a real two-repository execution:

1. checks out this repository;
2. checks out `materials-characterization-analyzer` at pinned commit `09a7e02b46924c44b9798ebab146281af50a28d7`;
3. installs both repositories independently;
4. downloads the public DWCNT source subset from Recherche Data Gouv;
5. executes Raman, FTIR, XPS, and TGA characterization contracts;
6. preserves the TEM method-mismatch block;
7. exports the producer bundle;
8. consumes and verifies the bundle here;
9. uploads producer and consumer evidence.

The commit is pinned so producer changes cannot silently alter an existing consumer validation. Updating it requires deliberate contract review and a new successful workflow run.

## Outputs

The consumer writes:

- `characterization_features_bundle_input.csv`, the explicitly normalized handoff input;
- validated long features;
- a feature dictionary;
- one-row-per-sample wide features;
- integrated sample-context and characterization table;
- join audit;
- standard characterization handoff manifest;
- `cross_repository_handoff_summary.json`;
- `cross_repository_handoff_report.md`;
- `cross_repository_handoff_manifest.json`.

## Scientific closeout

The public DWCNT result remains **Diagnostic**.

Supported:

- producer and consumer contracts interoperate;
- feature and evidence files are checksum-bound;
- one explicit `public-dwcnt` sample ID joins across the file boundary;
- Raman, FTIR, XPS, and TGA feature records retain source and preprocessing provenance;
- unit-label normalization is explicit, checksum-covered, and does not alter values;
- no direct internal imports, row-order joins, model training, or scientific metric recomputation occur.

Not supported:

- identical physical aliquots across instruments;
- process-response modeling or process optimization;
- causal or mechanistic interpretation;
- phase, chemical-state, or functional-group confirmation;
- predictive generalization;
- engineering release decisions.

A one-sample multimodal bundle proves interoperability and provenance transfer, not a statistical relationship. A future process-characterization study requires multiple explicitly traceable samples with compatible process histories and outcomes.
