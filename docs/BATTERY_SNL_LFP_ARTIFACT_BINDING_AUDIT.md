# Battery SNL LFP Artifact Binding Audit

Status: `v2.6.6_feature_stage_complete_local_artifact_pending`

## Objective

v2.6.6 implements the bounded, read-only artifact-binding audit authorized by
v2.6.5. The only candidate is:

```text
data/raw/battery_archive/SNL LFP.zip
```

The raw archive is intentionally ignored by Git and is not present in the GitHub
execution context. The tracked compact result therefore records
`pending_local_artifact`; it does not fabricate an archive checksum or entry
inventory.

## Allowed reads

When the archive is available in a local checkout, the audit may:

1. stream the archive bytes to compute SHA-256;
2. read the ZIP central directory with `ZipFile.infolist()`;
3. record entry names, normalized paths, compressed and uncompressed sizes,
   CRC-32, compression type, flags, and path-safety results;
4. classify cycle and time-series filenames;
5. parse filename labels with `entry_name` provenance.

The audit does not call `ZipFile.open`, `ZipFile.read`, `extract`, or
`extractall` for entry payloads.

## Expected inventory contract

The earlier read-only raw-data audit recorded the following expected structure:

| Field | Expected |
| --- | ---: |
| Total entries | 60 |
| Cycle CSV entries | 30 |
| Time-series CSV entries | 30 |
| Complete cycle/time-series pairs | 30 |
| Root prefix | `SNL LFP/` |

These values are an expected inventory contract, not proof that a newly observed
local archive is the official versioned distribution.

## Filename-label policy

A name such as:

```text
SNL LFP/SNL_18650_LFP_15C_0-100_0.5-1C_a_cycle_data.csv
```

may be parsed into labels such as `LFP`, `15C`, `0-100`, and `0.5-1C`. Every
parsed value is recorded with:

```text
provenance = entry_name
scientific_evidence = false
```

The parser does not establish battery chemistry, commanded temperature,
charge/discharge protocol, cutoff policy, or study identity.

## Decisions

Possible local artifact statuses are:

- `pending_local_artifact`: the ignored archive is unavailable;
- `local_artifact_inventory_bound`: checksum and safe central-directory inventory
  match the expected 60-entry contract;
- `inventory_contract_mismatch`: counts, pairing, or root prefix differ;
- `rejected_unsafe_archive_inventory`: traversal, duplicate, or encrypted entries
  are detected.

Even the strongest local result does **not** establish:

- document-to-archive binding;
- an official versioned distribution snapshot;
- battery/file or cycle/protocol equivalence;
- calibration or measurement uncertainty;
- cross-cohort comparability;
- predictive-validation eligibility.

## CLI

```bash
python -m src.platform_core.battery_snl_lfp_artifact_binding --json preview
python -m src.platform_core.battery_snl_lfp_artifact_binding --json run
python -m src.platform_core.battery_snl_lfp_artifact_binding --json validate \
  outputs/v2_6_battery_snl_lfp_artifact_binding/artifact_binding_summary.json
```

`preview` checks only configuration, prior evidence integrity, and archive
presence. `run` reads archive bytes for SHA-256 and the central directory only
when the local archive exists.

## Outputs

Local-only outputs:

```text
outputs/v2_6_battery_snl_lfp_artifact_binding/
├─ artifact_binding_summary.json
└─ central_directory_manifest.json
```

Tracked compact output:

```text
data/processed/battery_v2_6_6_snl_lfp_artifact_binding_summary.json
```

The tracked compact output excludes the row-level entry manifest.

## Validation boundary

Synthetic ZIP fixtures verify software behavior, deterministic checksums,
central-directory-only access, path safety, expected pairing, output isolation,
and evidence non-promotion. Synthetic success does not prove the identity or
scientific comparability of the user's local archive.

## Scientific closeout

Current tracked result: **Inconclusive**.

- Strongest evidence: v2.6.5 source documentation and a bounded local archive
  path are defined.
- Primary limitation: the Git-ignored archive bytes are unavailable in GitHub,
  so no real checksum or central-directory manifest has been recorded here.
- Suitable for: executing the bounded local identity audit.
- Unsuitable for: CSV analysis, metadata promotion, cohort merging, model
  evaluation, or engineering decisions.
