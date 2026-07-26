# Battery Michigan Formation Deep Blue Metadata Retrieval Gate

Status: `v2.6.13_feature_stage_complete_pending_local_metadata_retrieval`

## Objective

v2.6.13 tests whether the official University of Michigan Deep Blue REST API can recover stable **top-level file-set metadata** for dataset `b2773w109` without downloading provider files.

This is not an internal provider manifest reader. It is not a local archive loader, a cohort-admission step, or a model-validation step.

## Authoritative API contract

The official Deep Blue REST API documents:

- dataset metadata endpoint: `GET /data/concern/data_sets/:data_set_id.json`;
- file-set metadata endpoint: `GET /data/concern/file_sets/:file_set_id.json`;
- dataset responses containing `file_set_ids`, file counts and sizes;
- file-set responses containing stable IDs, labels, sizes, MIME types and repository checksum fields.

Documented download endpoints are explicitly denied by this gate:

- `/data/concern/data_sets/:data_set_id/zip_download.json`;
- `/data/downloads/:file_set_id.json`.

Official references:

- `https://deepblue.lib.umich.edu/data/rest-api`
- `https://deepblue.lib.umich.edu/data/concern/data_sets/b2773w109`

## Network and payload boundary

An executed run permits only:

1. one HTTPS GET to the exact dataset JSON endpoint;
2. at most two HTTPS GETs to exact file-set JSON endpoints, and only when the dataset response does not already embed the two file-set records.

The implementation rejects HTTP, alternate hosts, credentials, query strings, fragments, redirects, download endpoints, malformed or duplicate file-set IDs, oversized responses, and provider dataset identity changes.

| Item | Bound |
|---|---:|
| Dataset metadata response | 1 MiB |
| Each file-set response | 256 KiB |
| File-set endpoint requests | 2 |
| Total metadata requests | 3 |
| Request timeout | 30 seconds |

## Retained metadata

Dataset fields:

- `id`, `title`, `doi`
- `total_file_count`, `total_file_size`, `total_file_size_human_readable`
- `file_set_ids`

File-set fields:

- `id`, `title`, `label`
- `date_uploaded`, `date_modified`
- `file_size`, `file_size_human_readable`
- `checksum_algorithm`, `checksum_value`, `original_checksum`
- `mime_type`

Raw JSON, descriptions, creator lists, depositor information, email addresses and contact metadata are not retained. Each response is represented only by byte length, content type and SHA-256 response digest.

## Current tracked state

The tracked summary is intentionally pending:

```text
retrieval_status: pending_local_metadata_retrieval
network_called: false
overall_status: pending_local_metadata_retrieval
```

CI validates the request boundary and parser with synthetic JSON. CI does not make live Deep Blue requests.

Pending tracked checksum:

```text
ea35e4a5dbd7e1233750aac795d6b112750e0f0de9a564467c1cfea660a16eef
```

## Local execution

Preview:

```powershell
python -m src.platform_core.battery_michigan_formation_deepblue_metadata_retrieval_gate --json preview
```

Run the bounded metadata retrieval:

```powershell
python -m src.platform_core.battery_michigan_formation_deepblue_metadata_retrieval_gate --json run
```

The command writes:

```text
outputs/v2_6_battery_michigan_formation_deepblue_metadata/deepblue_metadata_result.json
data/processed/battery_v2_6_13_michigan_formation_deepblue_metadata_summary.json
```

Validate that an executed result was produced:

```powershell
python -m src.platform_core.battery_michigan_formation_deepblue_metadata_retrieval_gate --json validate "data/processed/battery_v2_6_13_michigan_formation_deepblue_metadata_summary.json" --require-executed
```

If the API request is blocked or provider metadata changed, the command fails closed with a sanitized error category. It does not fall back to a download or infer missing metadata.

## Interpretation

A successful complete result may establish only:

- API-verified provider dataset identity;
- two stable top-level file-set identities;
- available labels, sizes, MIME types and repository checksums.

It still does not establish:

- internal file inventory inside an archived top-level file set;
- cell-tracker or test-schedule schemas;
- provider cell IDs to Battery Archive entries;
- provider schedules to standardized cycle rows;
- provider checksum to local archive identity;
- cross-cohort comparability;
- predictive validation.

The scientific status remains `diagnostic`.

## Checksums

```text
v2.6.12 upstream
b1ce09e4ce06c9ec90839b63e1f2546d1fd2808f9c8ea6717edc5bc0fe93ce7d

metadata retrieval contract
7e9791087a25d03230f54118d04c53bb429d6bd79b3ce8d5c13bb9132dcf74e3

REST API evidence
797786d50b4266a91c6d534ea94ca63b20eeeeeca2f97f31811fc7dd423aa04f

pending tracked result
ea35e4a5dbd7e1233750aac795d6b112750e0f0de9a564467c1cfea660a16eef
```

## Scientific closeout before local execution

- **Result:** metadata retrieval contract implemented; provider-specific metadata not yet executed.
- **Evidence level:** official API documentation plus synthetic software validation.
- **Status:** `inconclusive`.
- **Primary limitation:** no retained dataset-specific API response.
- **Suitable for:** software contract validation.
- **Unsuitable for:** source binding, cohort admission, model validation or engineering decisions.
