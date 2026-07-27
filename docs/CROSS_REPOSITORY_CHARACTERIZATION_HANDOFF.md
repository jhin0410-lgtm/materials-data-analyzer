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
<source evidence file recorded by the manifest>
<analysis evidence file recorded by the manifest>
<comparability evidence file recorded by the manifest>
```

The evidence filenames are not inferred by the consumer. The bundle manifest records each sibling filename, checksum, and byte size. The consumer resolves only those explicit references and rejects absolute paths, nested paths, symlinks, checksum mismatches, and unrecorded substitutions.

The bundle manifest must use schema `1.0` and type `materials_characterization_feature_handoff`. It records checksums, sizes, exact columns, counts, instruments, quality flags, producer versions, evidence references, join policy, and the producer scientific closeout.

## Consumer command

```powershell
python scripts/consume_characterization_handoff_bundle.py `
  --bundle-manifest <producer-bundle>/characterization_handoff_bundle.json `
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

The result contains one sample and four executed instrument feature groups. It validates multimodal interoperability but does not provide process variables, targets, or statistical replication.

## Public RWGS XRD/SEM/EDS end-to-end case

The GitHub Actions workflow `.github/workflows/cross-repository-public-rwgs.yml` performs a second real two-repository execution:

1. checks out this repository;
2. checks out `materials-characterization-analyzer` at pinned commit `613783d803792fc283acee006a2fc5ebf6b20aee`;
3. installs both repositories independently;
4. downloads the public RWGS catalyst source archives from Zenodo;
5. verifies published checksums and executes the selected `5%Cu/Al2O3` case;
6. exports 31 XRD and EDS feature records through bundle schema `1.0`;
7. preserves the SEM `blocked_method_mismatch` status without creating SEM numeric features;
8. preserves the unresolved `Ni` context and `nominal_composition_confirmed = false`;
9. consumes the bundle, verifies all hashes, performs a one-to-one `sample_id` join, and uploads producer and consumer evidence.

The RWGS case tests a different scientific boundary from DWCNT: a blocked modality and a composition conflict must remain visible after integration rather than being silently dropped or converted into apparently complete multimodal data.

Producer commits are pinned so producer changes cannot silently alter an existing consumer validation. Updating a pin requires deliberate contract review and a new successful workflow run.

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

Both public handoff cases remain **Diagnostic**.

Supported:

- producer and consumer contracts interoperate;
- feature and evidence files are checksum-bound;
- explicit sample IDs join across the file boundary;
- methods, units, quality flags, source hashes, and preprocessing identifiers are preserved;
- blocked modalities and unresolved quality conflicts remain explicit in sample context and claim boundaries;
- unit-label normalization is explicit, checksum-covered, and does not alter values;
- no direct internal imports, row-order joins, model training, or scientific metric recomputation occur.

Not supported:

- identical physical aliquots across instruments;
- process-response modeling or process optimization;
- causal or mechanistic interpretation;
- phase, chemical-state, functional-group, or nominal-composition confirmation;
- quantitative particle-size claims from the blocked RWGS SEM image;
- predictive generalization;
- engineering release decisions.

A one-sample bundle proves interoperability and provenance transfer, not a statistical relationship. A future process-characterization study requires multiple explicitly traceable samples with compatible process histories, acquisition conditions, and valid outcomes.
