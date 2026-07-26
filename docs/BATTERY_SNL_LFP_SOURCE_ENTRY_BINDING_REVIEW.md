# Battery SNL LFP Source-to-Entry Binding Review

Status: `v2.6.7_feature_stage_complete_condition_group_nomenclature_bound`

## Objective

v2.6.7 reviews whether the source evidence recovered in v2.6.5 can be
connected to the checksum-bound local archive inventory recorded in v2.6.6.

The review is deliberately narrower than a loader or CSV-schema inspection.
It reads only tracked JSON evidence packages and does not read the raw ZIP,
entry payloads, CSV headers, or CSV rows.

## Preserved archive identity

| Field | Value |
| --- | --- |
| Archive | `data/raw/battery_archive/SNL LFP.zip` |
| SHA-256 | `006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d` |
| Archive size | `263826451` bytes |
| Entry-manifest checksum | `f85e6f1ac333f7ff20b7bfd01b8599cfe86e8950c4971e9fc074a367da86a75c` |
| Entries | 60 |
| Cycle/time-series pairs | 30 |
| Unsafe, duplicate, encrypted entries | 0 |

The row-level central-directory manifest remains local and is not committed.

## Official source chain

The bounded review uses five source records:

1. Battery Archive SNL study page:
   `https://www.batteryarchive.org/snl_study.html`
2. Battery Archive metadata rules:
   `https://batteryarchive.org/metadata.html`
3. Battery Archive download and attribution FAQ:
   `https://www.batteryarchive.org/faq.html`
4. DOE OSTI record 1650174:
   `https://www.osti.gov/pages/biblio/1650174`
5. Sandia publication record SAND2020-8433J:
   `https://www.sandia.gov/research/publications/details/degradation-of-commercial-lithium-ion-cells-as-a-function-of-chemistry-and-2020-01-09/`

The publication records connect the study cycling files to Battery Archive.
The official metadata rules define the observed filename-token order and
meaning. The SNL study page defines the study-level protocol families.

None of these sources publishes an official checksum or version identifier for
the observed `SNL LFP.zip`.

## Binding hierarchy

| Binding dimension | Decision |
| --- | --- |
| Publication to Battery Archive repository | `established` |
| Battery Archive filename nomenclature | `established` |
| SNL study to condition groups | `established_condition_group_only` |
| Condition groups to entry patterns | `established_repository_nomenclature_only` |
| Physical cell to entry | `not_established` |
| Cycle command to CSV rows | `not_established` |
| Instrument channel to CSV columns | `not_established` |
| Official versioned distribution snapshot | `not_established` |

The words `established` above apply only to the stated level. They do not
promote the filename labels into measured or cycle-specific scientific facts.

## Condition-group map

The 30 observed cell stems aggregate into 12 condition groups. Each cell is
represented by one cycle CSV and one time-series CSV.

| Group | Temperature (°C) | SOC window (%) | Charge C-rate | Discharge C-rate | Replicates | Cells |
| --- | ---: | --- | ---: | ---: | --- | ---: |
| `snl_lfp_group_01` | 15 | `0-100` | 0.5 | 1 | `a,b` | 2 |
| `snl_lfp_group_02` | 15 | `0-100` | 0.5 | 2 | `a,b` | 2 |
| `snl_lfp_group_03` | 25 | `0-100` | 0.5 | 0.5 | `a` | 1 |
| `snl_lfp_group_04` | 25 | `0-100` | 0.5 | 1 | `a,b,c,d` | 4 |
| `snl_lfp_group_05` | 25 | `0-100` | 0.5 | 2 | `a,b` | 2 |
| `snl_lfp_group_06` | 25 | `0-100` | 0.5 | 3 | `a,b,c,d` | 4 |
| `snl_lfp_group_07` | 25 | `20-80` | 0.5 | 0.5 | `a,b,c,d` | 4 |
| `snl_lfp_group_08` | 25 | `20-80` | 0.5 | 3 | `a` | 1 |
| `snl_lfp_group_09` | 25 | `40-60` | 0.5 | 0.5 | `a,b` | 2 |
| `snl_lfp_group_10` | 25 | `40-60` | 0.5 | 3 | `a,b` | 2 |
| `snl_lfp_group_11` | 35 | `0-100` | 0.5 | 1 | `a,b,c,d` | 4 |
| `snl_lfp_group_12` | 35 | `0-100` | 0.5 | 2 | `a,b` | 2 |

Official nomenclature semantics:

- temperature is the environmental cycling temperature;
- SOC bounds describe the beginning-of-life bulk-cycling range;
- charge/discharge rates describe bulk cycling, not capacity checks;
- the final letter denotes a replicate, not a verified physical serial number.

## Protocol-family mapping

- `0-100`: study-level 0.5C charging with CCCV; the LFP 100% DOD regime is
  documented as 2.0-3.6 V.
- `20-80`: constant-current cycling using voltage limits derived from fresh-cell
  discharge curves.
- `40-60`: constant-current cycling using capacity limits.

These are condition-group descriptions. They are not command logs and do not
prove the exact step sequence, cutoff execution, or capacity-check transitions
inside each CSV.

## Evidence-field outcome

No comparability field satisfies its promotion requirement.

| Field | Source-to-entry outcome |
| --- | --- |
| Chemistry | condition-group nomenclature bound; physical cell identity absent |
| Nominal capacity | study cell documented; entry binding absent |
| Ambient temperature | environment label bound at condition-group level |
| Charge protocol | partial condition-group binding |
| Discharge protocol | partial condition-group binding |
| Cutoff voltage | LFP 0-100 regime documented; per-entry cutoff unverified |
| Calibration/uncertainty | not bound |
| Source snapshot/version | not bound |

Therefore:

- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- evidence promotion requirements satisfied: `0 / 8`;
- overall: `condition_group_nomenclature_bound_gate_not_passed`.

## CLI

```bash
python -m src.platform_core.battery_snl_lfp_source_entry_binding --json preview
python -m src.platform_core.battery_snl_lfp_source_entry_binding --json run
python -m src.platform_core.battery_snl_lfp_source_entry_binding --json validate \
  outputs/v2_6_battery_snl_lfp_source_entry_binding/source_entry_binding_review.json
```

## Outputs

Local full result:

```text
outputs/v2_6_battery_snl_lfp_source_entry_binding/
└─ source_entry_binding_review.json
```

Tracked compact result:

```text
data/processed/battery_v2_6_7_snl_lfp_source_entry_binding_summary.json
```

The compact result records 12 condition-group patterns but not the 60-entry
central-directory manifest.

## Software validation

Tests cover:

- strict path and config contracts;
- exact v2.6.5 and v2.6.6 checksum preservation;
- archive and entry-manifest identity preservation;
- 12-group and 30-pair totals;
- SOC-family protocol mapping;
- rejection of physical-cell, cycle-command, snapshot, and evidence promotion;
- deterministic full and compact results;
- declared-output isolation;
- absence of network, archive, dataframe, and model dependencies.

Synthetic fixtures validate software behavior. They do not create new
scientific evidence.

## Scientific closeout

**Result:** Diagnostic.

**Strongest evidence:** the publication is officially linked to Battery
Archive, the repository defines the observed filename semantics, and the
checksum-bound archive contains 30 paired cell stems represented by 12
condition-group patterns consistent with the documented study variables.

**Primary limitation:** no provider-issued release identifier or checksum,
physical cell-to-file map, command log, instrument-channel map, calibration
record, or CSV payload review exists.

**Suitable for:** source attribution, condition-group provenance, bounded
schema-review planning, and evidence-gap prioritization.

**Unsuitable for:** scientific metadata promotion, cohort merging, predictive
validation, model selection, mechanism claims, or engineering decisions.

## Next evidence

The next step should not be unrestricted CSV analysis. A justified v2.6.8
schema-read contract would need to predeclare:

1. the exact two or three representative files;
2. whether only headers or a bounded number of rows may be read;
3. expected columns, units, and cycle-step semantics;
4. how capacity-check and bulk-cycling records will be distinguished;
5. stopping conditions for schema mismatch;
6. an explicit prohibition on cohort merging and model execution.

A provider-issued archive release identifier or checksum would be stronger
evidence than additional internal parsing and should remain the highest-value
source-snapshot request.
