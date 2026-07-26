# Battery Michigan Formation Provider-Package Structure Gate

Status: `v2.6.12_feature_stage_complete`

## Objective

v2.6.12 performs the smallest evidence step authorized by v2.6.11:

> Recover the official Michigan fast-formation provider-package structure and
> determine whether an exact provider file manifest and local Battery Archive
> binding can be established without downloading or reading data payloads.

This is a provider metadata closeout, not a loader, data acquisition, dataset
admission, comparability, or model stage.

## Selected source

The bounded provider source is the University of Michigan Deep Blue Data record:

- title: `Battery test data - fast formation study`;
- Deep Blue dataset ID: `b2773w109`;
- dataset DOI: `10.7302/pa3f-4w30`;
- published: `2021-09-24`;
- last modified: `2022-11-17`;
- repository file-set count shown by the public record: `2`;
- total repository size shown by the public record: `2.37 GB`.

Official source:

`https://deepblue.lib.umich.edu/data/concern/data_sets/b2773w109`

The provider record states that forty prismatic lithium-ion pouch cells were
built with an NCM111 cathode, graphite anode, and nominal capacity of 2.36 Ah.
Two formation groups were used: fast formation and baseline formation. Cycle
life testing was performed at room temperature and 45 °C. Maccor equipment
collected formation and cycling data, Voltaiq was used for processing, and CSV
exports were produced.

These are provider document declarations. They are not independently remeasured
or inferred by v2.6.12.

## Recovered package structure

The official provider record declares four top-level package areas:

| Declared folder | Provider-declared contents | v2.6.12 status |
| --- | --- | --- |
| `code` | copy of the source code; related DOI `10.5281/zenodo.5525258` | recovered at document level |
| `data` | raw cycler files from formation, cycling, and coin-cell testing | recovered at document level |
| `documents` | cell tracker files and test schedules | recovered at document level |
| `output` | post-processed outputs | recovered at document level |

The presence of the `documents` folder is important because it supplies a
credible provider-side location for cell identity and command artifacts that
were absent from the SNL LFP evidence line.

However, a folder declaration is not an exact file manifest.

## Exact manifest result

The public dataset record exposes a count of two repository file sets and a
total size of 2.37 GB, but the evidence captured for this gate does not expose:

- file-set identifiers;
- file-set labels;
- repository checksums;
- MIME types or individual sizes;
- internal filenames;
- cell tracker filenames;
- test schedule filenames;
- cell tracker schemas;
- test schedule schemas;
- source-code file manifests.

The exact provider package manifest therefore remains:

`not_established`

Deep Blue documents payload-free dataset and file-set metadata endpoints at:

`https://deepblue.lib.umich.edu/data/rest-api`

v2.6.12 records only that these endpoint types are documented. It does not
claim that the dataset-specific JSON or file-set metadata was successfully
retrieved.

## Battery Archive relationship

Battery Archive states that uploaded data are converted to a standard format.
Its University of Michigan study summary identifies the same fast-formation
study and reports forty Michigan cells divided between fast and baseline
formation, followed by room-temperature or 45 °C cycling.

Official study summary:

`https://www.batteryarchive.org/study_summaries.html`

This establishes a study-level source-family relationship. It does not establish:

- the exact conversion implementation used for this dataset;
- the provider file used to create each standardized CSV;
- the provider cell tracker row corresponding to each local cell stem;
- the provider test schedule corresponding to each standardized cycle;
- an official checksum for `Michigan Formation.zip`;
- a provider-file-to-local-entry mapping.

## Decision

The v2.6.12 decision is:

- provider dataset identity: `established`;
- provider package folder structure: `recovered_document_level`;
- provider file-set count: `2`, recorded from the public repository page;
- exact provider file manifest: `not_established`;
- cell tracker presence: `declared_document_level`;
- test schedule presence: `declared_document_level`;
- cell tracker schema: `not_established`;
- test schedule command semantics: `not_established`;
- provider package to local archive binding: `not_established`;
- provider file to standardized row binding: `not_established`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- overall:
  `provider_package_structure_recovered_exact_manifest_not_established_gate_not_passed`;
- scientific closeout: `diagnostic`.

## Scientific interpretation

### Supported

The official Deep Blue provider record supports the existence and identity of
the dataset, its DOI, principal study conditions, two repository file sets,
total repository size, and the declared package folders. It also supports the
document-level statement that cell trackers and test schedules exist somewhere
inside the provider package.

### Diagnostic only

The recovered structure is useful for deciding the next provenance step, but it
does not identify exact files or schemas. The evidence is therefore suitable
for metadata planning and source-binding design only.

### Not supported

v2.6.12 does not support:

- treating the Deep Blue DOI as the identity of the local ZIP;
- treating the two repository file sets as two internal data files;
- treating a declared test schedule as cycle-row command binding;
- treating a declared cell tracker as a local cell-ID map;
- inferring internal filenames from the local archive;
- admitting Michigan Formation for cross-cohort validation;
- target harmonization;
- model training, evaluation, or metric comparison;
- mechanism, causal, or engineering conclusions.

## Read and execution boundary

The implementation reads only tracked repository artifacts:

- v2.6.11 next-source selection summary;
- v2.6.12 provider evidence record;
- v2.6.12 decision contract;
- v2.6.12 example config.

It does not perform:

- network access;
- credential access;
- provider dataset download;
- provider file payload reads;
- local `Michigan Formation.zip` reads;
- local CSV reads;
- filename-derived metadata inference;
- command inference;
- cohort merge;
- target alignment;
- model execution;
- metric recomputation.

## Next authorized scope

A subsequent gate may attempt only payload-free repository metadata:

1. retrieve the Deep Blue dataset JSON if available without a bundle download;
2. recover file-set identifiers;
3. retrieve file-set metadata records;
4. record stable labels, sizes, MIME types, and repository checksums;
5. determine whether those metadata expose tracker or schedule artifacts.

It must stop if manifest metadata require downloading provider files.

Even a successful file-set metadata retrieval would not authorize payload reads,
local archive reads, target harmonization, cohort merging, or model execution.

## Checksums

- v2.6.11 upstream:
  `5cbb6b979bd6529e28d24af1ecb0e1579439fef2be710904081d8e81d032747b`;
- provider evidence:
  `079741f6b6082829f4754495e2b1f96433e574049de029f8bef593440402924a`;
- provider structure contract:
  `bac45b313696cd20502e740d2b29c25ba76e9c5605f38fc7476e75b7de042408`;
- tracked result:
  `b1ce09e4ce06c9ec90839b63e1f2546d1fd2808f9c8ea6717edc5bc0fe93ce7d`.

## CLI

Preview without writing output:

```bash
python -m src.platform_core.battery_michigan_formation_provider_package_structure_gate --json preview
```

Write the ignored local result:

```bash
python -m src.platform_core.battery_michigan_formation_provider_package_structure_gate --json run
```

Validate the tracked result:

```bash
python -m src.platform_core.battery_michigan_formation_provider_package_structure_gate --json validate data/processed/battery_v2_6_12_michigan_formation_provider_package_summary.json
```

Expected validation checksum:

`b1ce09e4ce06c9ec90839b63e1f2546d1fd2808f9c8ea6717edc5bc0fe93ce7d`

## Preservation

- `PLATFORM_VERSION` remains `2.4.0`;
- Ridge generalization remains `unsupported`;
- v2.6.11 selection remains bounded to source-binding review;
- no existing loader, model, metric, threshold, public API, or raw artifact is
  modified.
