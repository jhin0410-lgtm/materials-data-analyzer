# Battery External Cohort Next Source Selection Gate

Status: `v2.6.11_feature_stage_complete`

## Objective

v2.6.11 closes the SNL LFP payload-expansion line and selects the next
source-evidence target from the nine archives already recorded by v2.6.4.

The question is deliberately narrower than dataset admission:

> Which existing local archive has the strongest provider-issued source package
> for resolving current provenance blockers without authorizing raw analysis,
> cohort merging, or model execution?

## Upstream boundaries

The gate verifies and preserves:

- v2.6.4 external-cohort admission checksum:
  `2776bc152c0e4655f0c90ec6513883aea3758cac7fac687e02e5685c72dfdb6f`;
- v2.6.10 SNL LFP closeout checksum:
  `0093de000c25cfcbbd36eaf8216eabc7fb3bc3db23b724dbffcb69b4d77ddf28`;
- SNL LFP evidence line: `closed_at_diagnostic_boundary`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- Ridge generalization: `unsupported`;
- public `PLATFORM_VERSION`: `2.4.0`.

## Candidate universe

The tracked inventory contains exactly nine archives:

| Archive | Cycle files | Time-series files | v2.6.11 disposition |
| --- | ---: | ---: | --- |
| `CALCE.zip` | 7 | 7 | `hold_source_identity_ambiguous` |
| `HNEI.zip` | 15 | 15 | `hold_no_provider_command_artifact` |
| `Michigan Expansion.zip` | 18 | 18 | `hold_local_representation_omits_defining_signal` |
| `Michigan Formation.zip` | 40 | 40 | `selected_for_bounded_source_binding_only` |
| `Oxford.zip` | 8 | 8 | `reserve_versioned_source_no_command_artifact` |
| `SNL LFP.zip` | 30 | 30 | `closed_diagnostic_no_incremental_payload` |
| `SNL NCA.zip` | 24 | 24 | `hold_same_study_limitation` |
| `SNL NMC.zip` | 32 | 32 | `hold_same_study_limitation` |
| `UL-Purdue.zip` | 22 | 22 | `hold_source_mapping_incomplete` |

The archive names and counts come from the tracked read-only inventory audit.
No archive or CSV payload is opened by v2.6.11.

## Hard gate

A candidate is selected only when the official provider record declares all of
the following:

1. a stable dataset record;
2. a dataset DOI;
3. a detailed README;
4. raw cycler data;
5. cell tracker material;
6. test schedules;
7. source code;
8. a source-family relationship to one existing local archive.

This is a Boolean hard gate. Weighted scoring and substitution of missing
evidence are prohibited.

Exact local-file binding is not required for selection because selection only
authorizes the next binding audit. It does not establish that binding.

## Selected candidate

`Michigan Formation.zip` is selected for
`bounded_official_source_package_binding_only`.

The official University of Michigan Deep Blue Data record identifies:

- dataset DOI `10.7302/pa3f-4w30`;
- 40 NCM111/graphite pouch cells;
- nominal capacity of 2.36 Ah;
- fast and baseline formation groups;
- room-temperature and 45 °C cycle-life testing;
- Maccor cycler data processed through Voltaiq;
- a detailed README;
- raw formation and cycling data;
- cell tracker files;
- test schedules;
- source code and post-processed outputs.

Provider record:

```text
https://deepblue.lib.umich.edu/data/concern/data_sets/b2773w109
```

These declarations can address chemistry, nominal capacity, cell identity,
formation-protocol provenance, cycling-temperature groups, cycler identity,
and command-schedule evidence. They do not yet prove that the local
`Michigan Formation.zip` entries are exact derivatives of that provider
package.

## Why other candidates are not selected

### Oxford reserve

The Oxford Research Archive record supplies DOI
`10.5287/bodleian:KO2kdmYGg`, Version 1, a 740 mAh Kokam pouch-cell identity,
and a README. It is retained as the strongest reserve.

The recovered record does not declare a provider test-schedule or command
artifact, so it does not pass the command-provenance hard gate.

### Michigan Expansion hold

The provider DOI and instrumentation record are useful, but expansion is the
defining measurement. The tracked standardized Battery Archive inventory
contains electrical and temperature cycle/time-series columns and does not
show an expansion column. The local representation may therefore omit the
measurement that gives the source study its primary scientific meaning.

### SNL siblings hold

`SNL NCA.zip` and `SNL NMC.zip` share the same study-level limitation already
reached by the SNL LFP line. Additional chemistry breadth does not provide the
missing provider row, step, command, or official distribution binding.

### Remaining holds

CALCE lacks an exact study-to-archive identity in the recovered evidence.
HNEI and UL-Purdue have useful study descriptions but no recovered stable
provider package with cell trackers and test schedules.

## Decision

```text
selected archive:
Michigan Formation.zip

selection status:
selected_for_bounded_source_binding_only

local archive to official dataset binding:
not_established

provider package to standardized cycle rows:
not_established

cross-cohort comparability:
not_admitted

predictive validation:
blocked

overall:
next_source_candidate_selected_gate_not_passed
```

## Authorized next scope

The next stage may inspect only:

- the official Deep Blue metadata record;
- the provider README and file-manifest inventory;
- cell tracker filenames and schemas;
- test schedule filenames and schemas;
- source-code provenance and declared conversion paths.

It must stop before:

- downloading the 2.37 GB raw provider bundle;
- reading local archive payloads;
- inferring commands from measured current or voltage;
- treating the DOI as an exact checksum binding;
- harmonizing targets;
- merging cohorts;
- running or tuning a model.

## Scientific closeout

- Classification: `diagnostic`
- Result:
  `michigan_formation_selected_for_bounded_source_binding_only`
- Strongest evidence: the provider dataset record declares artifacts that can
  directly reduce the command, cell-identity, and source-provenance blockers.
- Primary limitation: no provider file identity or conversion map is yet bound
  to the local standardized archive.
- Suitable for: bounded provider-metadata inventory and binding design.
- Unsuitable for: external validation, model evaluation, mechanism claims, or
  engineering decisions.

## CLI

Preview without writes:

```powershell
python -m src.platform_core.battery_external_cohort_next_source_selection_gate --json preview
```

Run deterministic tracked-evidence verification:

```powershell
python -m src.platform_core.battery_external_cohort_next_source_selection_gate --json run
```

Validate the tracked result:

```powershell
python -m src.platform_core.battery_external_cohort_next_source_selection_gate --json validate "data/processed/battery_v2_6_11_external_cohort_next_source_selection_summary.json"
```

## Checksums

- candidate register:
  `fc0a863cd80756fee7048682fc2c0d13b876d5ee6442b889daa1bc30b1fa8b00`;
- selection contract:
  `c960b21fc061393d4ebeba5e9a6a5f2d105c25da1514f8017feee0deef339079`;
- tracked compact result:
  `5cbb6b979bd6529e28d24af1ecb0e1579439fef2be710904081d8e81d032747b`.

## Software validation

Focused tests verify:

- exact upstream checksums and prior scientific boundaries;
- the fixed nine-archive candidate universe;
- exact inventory pair counts;
- Boolean hard-gate selection;
- Michigan Formation as the only passing candidate;
- Oxford reserve and SNL LFP closeout dispositions;
- path safety;
- deterministic byte-for-byte tracked-result regeneration;
- rejection of cross-cohort admission, payload reads, downloads, and model use.

Passing these tests validates software behavior and evidence-contract
preservation. It does not validate local-to-provider dataset identity.
