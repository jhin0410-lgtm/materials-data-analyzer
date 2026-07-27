# Public Carbon Four-Material Cross-Repository Handoff

## Purpose

This workflow validates the existing `materials-data-analyzer` bundle consumer against a real multi-sample characterization package produced by the independently installed `materials-characterization-analyzer` repository.

The producer commit is pinned to:

```text
1994b1f473cb971f96d675b3c04d00e73e3f6873
```

Updating that pin requires deliberate contract review and a new successful real-data workflow. The repositories do not import each other's internal modules.

## Public samples

The bundle contains four explicit source sample classes from Recherche Data Gouv dataset `doi:10.57745/7KA2UG`:

| sample_id | Source class | Material context |
|---|---|---|
| `public-dwcnt` | DWCNT | Double-walled carbon nanotubes |
| `public-mwcnt` | MWCNT | Multi-walled carbon nanotubes |
| `public-flg` | FLG | Few-layer graphene |
| `public-gnp` | GNP | Graphene nanoplatelets |

These are different material classes with different synthesis or procurement histories. They are not controlled levels of one process parameter.

## Executed evidence chain

```text
exact Dataverse datafile IDs and filenames
-> 20 sample files plus one shared readme
-> Raman / FTIR / XPS / TGA execution for four sample IDs
-> TEM source readiness with quantitative segmentation blocked
-> 16 persisted analysis results
-> 495 long-format feature records
-> versioned producer bundle with checksums
-> consumer schema, size, checksum, provenance, and sample-set validation
-> lexical unit-label normalization on a consumer copy
-> feature pivot and explicit sample_id join
-> four-row integrated sample table
-> consumer summary, report, and checksum manifest
```

## Consumer command

After the producer case has generated its bundle:

```powershell
python scripts/consume_characterization_handoff_bundle.py `
  --bundle-manifest <producer-output>/characterization_handoff_bundle.json `
  --output outputs/cross-repository-public-carbon-four
```

The output directory must be absent or empty. Existing files are not deleted or silently overwritten.

## Expected real-data contract

The pinned producer evidence contains:

- 4 samples;
- 16 measurements;
- 495 feature records;
- instruments `ftir`, `raman`, `tga`, and `xps`;
- 495/495 source SHA-256 values;
- 495/495 preprocessing identifiers;
- `review_required` on all exported diagnostic features;
- four unique `sample_id` values in both feature and sample-context tables.

The consumer must produce:

- 4 matched samples;
- 0 process-only samples;
- 0 characterization-only samples;
- 495 validated long records;
- a four-row integrated table;
- no row-order join;
- no silent aggregation;
- no inferred metadata;
- no model training or scientific metric recomputation.

## Unit-label normalization

The producer file remains unchanged. The consumer writes a checksum-covered input copy for stable ASCII feature keys:

```text
%       -> percent
%/degC  -> percent/degC
```

This affects 73 records in the pinned case. Numeric values and physical dimensions are not converted.

## Scientific closeout

**Evidence level: Diagnostic**

Supported:

- the same file contract works for four real sample IDs rather than one;
- producer source identity, preprocessing identity, methods, units, quality flags, and claim boundaries survive the repository boundary;
- explicit `sample_id` joins are complete and auditable;
- different per-sample feature counts can be represented without row-order assumptions;
- unsupported process-science claims remain blocked.

Not supported:

- treating DWCNT, MWCNT, FLG, and GNP as a process series;
- process-response modeling, optimization, or causal attribution;
- identical physical aliquots across characterization techniques;
- phase, chemical-state, functional-group, or reaction confirmation;
- predictive generalization;
- engineering-release decisions.

This workflow proves multi-sample software interoperability and provenance transfer. A scientifically valid process-characterization study still requires controlled and comparable process histories, explicit specimen lineage, replicates, compatible outcomes, and uncertainty estimates.
