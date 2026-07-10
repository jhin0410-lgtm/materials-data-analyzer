# Materials Project Source Notes

## Source Scope

This case study uses a local Materials Project API-derived pilot artifact:

```text
data/processed/materials_project_fe_si.csv
```

The current artifact has 50 rows and 7 columns. It contains materials whose
formulas include Fe and Si, but it is not a binary-only Fe-Si dataset.

## Provenance Status

The v1.2.1 query specification is reconstructed from the existing connector and
local processed CSV. Exact historical retrieval timestamp, Materials Project
API version, and database version are currently incomplete or unknown.

Current credential-free query contract:

```text
data/case_studies/materials_project/query_spec.json
```

Current compact provenance artifacts:

```text
data/processed/materials_project_query_manifest.json
data/processed/materials_project_property_inventory.csv
```

Future regeneration should update the query specification and manifest
together.

## Credential Policy

- API credentials are not included in this repository.
- The connector reads the API key only from `MP_API_KEY`.
- Do not store API keys, tokens, local private paths, or raw API credentials in
  source notes, configs, manifests, tests, or README files.

## Raw And Processed Artifact Policy

- `data/processed/materials_project_fe_si.csv` is currently a local-only
  generated artifact and is not Git-tracked.
- Raw Materials Project API responses belong under local ignored raw-data paths.
- Compact query manifests, field inventories, and source notes may be tracked
  when they contain no credentials and no absolute local paths.

## Limitations

Materials Project values are computed materials properties from a database/API.
They are not direct experimental measurements and should not be presented as lab
or manufacturing results.

The current local pilot artifact should not be used to claim new material
discovery, DFT execution by this repository, or experimentally validated
performance.

Materials Project access terms, license, citation requirements, and any
publication constraints must be confirmed by the user before publishing a case
study.
