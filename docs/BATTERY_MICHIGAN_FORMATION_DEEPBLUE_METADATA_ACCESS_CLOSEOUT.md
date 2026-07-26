# v2.6.13 Michigan Formation Deep Blue Metadata Access Closeout

## Status

- Software validation: supported
- Live metadata retrieval: failed with `http_status_403`
- Scientific closeout: inconclusive
- Overall status: `provider_metadata_endpoint_access_denied_gate_not_passed`

## Observed execution

The user executed the bounded metadata-only command from the tracked v2.6.13 branch:

```powershell
python -m src.platform_core.battery_michigan_formation_deepblue_metadata_retrieval_gate --json run
```

The command returned:

```json
{"error_category":"http_status_403","retrieval_status":"failed","valid":false}
```

The observation is recorded only as `user_reported_local_execution_context`.
It does not establish that the provider API is globally inaccessible.

## Request boundary preserved

The attempted request was limited to the official dataset JSON endpoint:

```text
https://deepblue.lib.umich.edu/data/concern/data_sets/b2773w109.json
```

The retrieval implementation already supplied:

- `Accept: application/json`
- a declared metadata-audit User-Agent
- no credentials
- no query string
- no redirects
- no provider download endpoint

The official Deep Blue REST API documentation continues to describe dataset and file-set JSON metadata endpoints. The observed HTTP 403 therefore records an access failure for this execution context, not evidence that the documented endpoint contract is false.

## Retained evidence

The tracked compact result retains only:

- endpoint identity;
- HTTP status category `403`;
- one attempted network call;
- no redirect followed;
- no credentials sent;
- no response body retained;
- all scientific non-admission boundaries.

It does not retain an HTTP response body, cookies, headers, depositor data, contact metadata, or provider payload.

## Decision

```text
provider_dataset_identity:
documented_not_api_verified

top_level_file_set_metadata:
access_denied_for_observed_execution_context

internal_provider_manifest:
not_established

local_archive_binding:
not_established

provider_to_standardized_row_binding:
not_established

cross_cohort_comparability:
not_admitted

predictive_validation:
blocked

overall_status:
provider_metadata_endpoint_access_denied_gate_not_passed
```

## Scientific interpretation

### Supported

- The bounded metadata request was attempted.
- The observed request returned HTTP 403.
- No metadata body was recovered.
- No provider or local payload was read.
- No model, metric, cohort merge, or command inference was performed.

### Not supported

- The Deep Blue API is globally unavailable.
- The dataset is private or withdrawn.
- The local `Michigan Formation.zip` matches either provider file set.
- Provider file-set IDs, labels, sizes, MIME types, or checksums were recovered.
- Cross-cohort comparability or predictive validation is admissible.

## Stop decision

No browser-cookie emulation, credential use, WAF bypass, alternate host, redirect acceptance, or download-endpoint substitution is authorized.

The Michigan Formation metadata-binding route stops here unless one of the following becomes available through an ordinary provider-supported path:

1. a provider metadata export supplied by Deep Blue;
2. a browser-accessible JSON response saved without downloading provider files;
3. a provider contact response identifying a supported API access method;
4. a stable top-level file-set manifest published separately by the provider.

Until then, additional request retries do not improve scientific provenance and should not block completion of the wider v2.6 evidence line.

## Tracked checksum

```text
5b43bec9448c339b0a6cc958f7af321a44d16b0acffc66099e7436d07975e7f2
```

## Validation

```powershell
python -m src.platform_core.battery_michigan_formation_deepblue_metadata_access_closeout --json validate "data/processed/battery_v2_6_13_michigan_formation_deepblue_metadata_summary.json"
```

Expected result:

```json
{
  "valid": true,
  "retrieval_status": "failed",
  "error_category": "http_status_403",
  "deterministic_result_checksum": "5b43bec9448c339b0a6cc958f7af321a44d16b0acffc66099e7436d07975e7f2"
}
```
