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

## Public carbon four-material end-to-end case

The GitHub Actions workflow `.github/workflows/cross-repository-public-carbon-four-materials.yml` performs a third real two-repository execution:

1. checks out this repository;
2. checks out the reviewed `materials-characterization-analyzer` `0.8.6` producer at pinned commit `7242594f775b8dbe651a6131bb1b39b5f60c62cd`;
3. installs both repositories independently;
4. verifies Recherche Data Gouv dataset version `1.0` and exact source bindings for DWCNT, MWCNT, FLG, and GNP;
5. verifies supplied checksums before source persistence and executes Raman, FTIR, XPS, and TGA for all four sample IDs;
6. retains TEM as source-readiness evidence with quantitative analysis blocked;
7. exports 495 review-required feature records from 16 measurements through bundle schema `1.0`;
8. consumes the bundle and verifies 495/495 source hashes and preprocessing identifiers;
9. performs four explicit `sample_id` matches with no unmatched records, aggregation, inferred metadata, or row-order joining;
10. verifies that no `char__tem__` numeric columns appear and uploads producer and consumer evidence.

The dedicated case documentation is in `docs/PUBLIC_CARBON_FOUR_MATERIAL_HANDOFF.md`. This case validates a multi-sample bundle, but the four material classes are not controlled process levels and must not be interpreted as a process-response series.

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

All three public handoff cases remain **Diagnostic**.

Supported:

- producer and consumer contracts interoperate;
- feature and evidence files are checksum-bound;
- explicit sample IDs join across the file boundary;
- methods, units, quality flags, source hashes, and preprocessing identifiers are preserved;
- blocked modalities and unresolved quality conflicts remain explicit in sample context and claim boundaries;
- unit-label normalization is explicit, checksum-covered, and does not alter values;
- no direct internal imports, row-order joins, model training, or scientific metric recomputation occur;
- the same schema supports both one-sample and four-sample diagnostic bundles.

Not supported:

- identical physical aliquots across instruments;
- treating different material classes as controlled process levels;
- process-response modeling or process optimization;
- causal or mechanistic interpretation;
- phase, chemical-state, functional-group, or nominal-composition confirmation;
- quantitative particle-size claims from the blocked RWGS SEM image;
- quantitative TEM morphology from the blocked carbon images;
- predictive generalization;
- engineering release decisions.

A multi-sample bundle proves scalable interoperability and provenance transfer, not a statistical process relationship. A valid process-characterization study requires explicitly traceable samples with controlled and compatible process histories, acquisition conditions, replicates, valid outcomes, and uncertainty estimates.
