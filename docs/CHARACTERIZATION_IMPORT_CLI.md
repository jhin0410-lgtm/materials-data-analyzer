# Installed Characterization Bundle Import

`mda-characterization-import` is the installed consumer entry point for versioned
handoff bundles produced by `materials-characterization-analyzer`.

```bash
mda-characterization-import \
  --bundle-manifest path/to/characterization_handoff_bundle.json \
  --output outputs/characterization-import
```

An optional consumer-owned process table may be supplied only when it has an
explicit `sample_id` column and its sample set and shared case, trace, material,
or system identity agree exactly with the producer context:

```bash
mda-characterization-import \
  --bundle-manifest path/to/characterization_handoff_bundle.json \
  --process-table path/to/process_table.csv \
  --output outputs/process-characterization-import
```

## Validation boundary

Before integration, the consumer verifies:

- bundle schema and type;
- feature, context, and evidence file SHA-256 and byte size;
- exact stable feature columns;
- feature, sample, measurement, instrument, and quality-flag counts;
- complete source-checksum and preprocessing identifiers;
- unique, nonblank, exactly matching `sample_id` sets;
- the declared no-row-order, no-silent-aggregation, no-metadata-inference join contract;
- optional process-table identity agreement;
- producer scientific-closeout fields.

The legacy script `scripts/consume_characterization_handoff_bundle.py` remains a
compatibility wrapper around the installed command.

## Outputs

The consumer preserves the existing public filenames and writes a sample-level
evidence dossier consisting of:

- validated long-format characterization features;
- a feature dictionary and wide feature table;
- an integrated sample table;
- a sample join audit;
- source and cross-repository manifests;
- a JSON summary;
- a Markdown handoff report.

This is an interoperability and provenance dossier, not a model result. The
consumer does not retrain a model, recompute scientific metrics, infer missing
sample identity, establish physical-aliquot equivalence, or authorize causal,
predictive, optimization, or engineering claims.
