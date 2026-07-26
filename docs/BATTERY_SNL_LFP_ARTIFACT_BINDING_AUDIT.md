# Battery SNL LFP Artifact Binding Audit

Status: `v2.6.6_feature_stage_complete_local_artifact_inventory_bound`

## Objective

v2.6.6 implements the bounded, read-only artifact-binding audit authorized by
v2.6.5. The only candidate is:

```text
data/raw/battery_archive/SNL LFP.zip
```

The raw archive remains intentionally ignored by Git. The audit was executed in
a local checkout containing the archive, and the checksum and compact
central-directory result are tracked without committing the raw ZIP or row-level
entry manifest.

## Allowed reads

The audit may:

1. stream the archive bytes to compute SHA-256;
2. read the ZIP central directory with `ZipFile.infolist()`;
3. record entry names, normalized paths, compressed and uncompressed sizes,
   CRC-32, compression type, flags, and path-safety results;
4. classify cycle and time-series filenames;
5. parse filename labels with `entry_name` provenance.

The audit does not call `ZipFile.open`, `ZipFile.read`, `extract`, or
`extractall` for entry payloads. It does not read CSV headers or rows.

## Observed archive identity

| Field | Observed |
| --- | --- |
| Archive SHA-256 | `006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d` |
| Archive size | `263826451` bytes |
| Entry-manifest checksum | `f85e6f1ac333f7ff20b7bfd01b8599cfe86e8950c4971e9fc074a367da86a75c` |
| Total entries | 60 |
| Cycle CSV entries | 30 |
| Time-series CSV entries | 30 |
| Complete cycle/time-series pairs | 30 |
| Other entries | 0 |
| Root prefix | `SNL LFP/` |
| Inventory contract match | `true` |

## Safety result

| Field | Observed |
| --- | ---: |
| Safe entries | 60 |
| Unsafe entries | 0 |
| Duplicate entries | 0 |
| Encrypted entries | 0 |

The recorded local artifact status is:

```text
local_artifact_inventory_bound
```

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

All 60 entry names matched the bounded parser, but this parsing does not
establish battery chemistry, commanded temperature, charge/discharge protocol,
cutoff policy, or study identity.

## Scientific decision

The resulting decision is:

- local artifact inventory binding: `local_artifact_inventory_bound`;
- checksum identity recorded: `true`;
- central-directory inventory recorded: `true`;
- document-to-archive binding: `not_established`;
- official distribution snapshot: `not_established`;
- evidence promotion requirements satisfied: `0 / 8`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- overall: `local_artifact_inventory_bound_gate_not_passed`.

The local checksum and central directory identify this specific local ZIP. They
do **not** establish:

- an independently verifiable official versioned distribution;
- mapping between publication cells and archive entries;
- cycle-level commanded protocols or cutoff policies;
- calibration or measurement uncertainty;
- equivalence with the existing Kaggle NASA-derived cohort;
- predictive-validation eligibility.

## CLI

```bash
python -m src.platform_core.battery_snl_lfp_artifact_binding --json preview
python -m src.platform_core.battery_snl_lfp_artifact_binding --json run
python -m src.platform_core.battery_snl_lfp_artifact_binding --json validate \
  outputs/v2_6_battery_snl_lfp_artifact_binding/artifact_binding_summary.json
```

`preview` checks only configuration, prior evidence integrity, and archive
presence. `run` computes the archive checksum and reads the central directory.
The persisted summary checksum is computed after the row-level manifest is
removed, so the documented `validate` command checks the exact stored payload.
Results produced before this checksum fix must be regenerated with `run` before
validation.

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
central-directory-only access, path safety, expected pairing, persisted-summary
validation, output isolation, and evidence non-promotion. The real local run
establishes the identity and safe inventory of the observed archive only.

## Scientific closeout

Current tracked result: **Diagnostic**.

- Strongest evidence: a SHA-256-identified local archive has a safe 60-entry
  central directory that matches the predeclared 30-pair inventory contract.
- Primary limitation: no official versioned snapshot or source-to-entry mapping
  connects this archive to the documented cells, command logs, or instruments.
- Suitable for: local artifact identity, central-directory inventory, and
  filename-label provenance.
- Unsuitable for: CSV analysis, metadata promotion, cohort merging, model
  evaluation, predictive claims, or engineering decisions.
