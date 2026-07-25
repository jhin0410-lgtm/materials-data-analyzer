# Battery SNL LFP Source Evidence Recovery

Status: `v2.6.5_snl_lfp_source_evidence_recovery_feature_stage_complete`

## Purpose

v2.6.5 performs one bounded source-document recovery step for the local
`SNL LFP.zip` candidate identified by v2.6.4. It records authoritative study
and publication evidence before any archive row is read, any archive is
extracted, or any validation experiment is selected.

The package does not claim that the local archive is an official dataset
snapshot. It also does not promote study-level documentation into local
battery-, file-, cycle-, or instrument-channel evidence without a verified
binding.

## Bounded Source

The selected source is the Sandia commercial 18650 cycling study described in:

- the official Battery Archive SNL study page;
- the official Battery Archive metadata rules;
- the DOE OSTI record for DOI `10.1149/1945-7111/abae37`, OSTI ID `1650174`;
- the Sandia publication record `SAND2020-8433J`.

The source scope is restricted to `SNL LFP.zip`. Evidence is not generalized to
SNL NCA, SNL NMC, or the other six Battery Archive bundles.

## Recovered Document Evidence

The fixed eight-field matrix records the following document-level evidence:

| Field | Recovery | Documented evidence | Remaining binding gap |
| --- | --- | --- | --- |
| Chemistry | recovered | commercial 18650 LFP, A123 Systems APR18650M1A | no verified local entry-to-cell binding |
| Nominal capacity | recovered | 1.1 Ah for APR18650M1A | no verified local entry-to-cell binding |
| Ambient temperature | partial | chamber equilibration and K-type cell-skin thermocouple monitoring | no cycle-level setpoint or command binding |
| Charge protocol | partial | 0.5C charge, capacity checks, and 0-100% SOC CCCV termination rules | no cycle-specific charge-command log binding |
| Discharge protocol | partial | DOD/rate groups and capacity-check discharge protocol | no cycle-specific discharge-command log binding |
| Cutoff voltage | partial | LFP 100% DOD regime documented as 2.0-3.6 V | not established for every local file or cycle |
| Calibration | partial | Arbin, chamber, and thermocouple equipment identities | no channel map, calibration, accuracy, drift, or uncertainty |
| Source snapshot | unresolved | DOI, OSTI ID, and SAND number identify the publication | no versioned official data distribution or checksum binding |

Seven fields now have useful source-document evidence. None satisfies the
promotion granularity required by the v2.6.4 admission gate.

## Target Boundary

The source study documents capacity retention relative to nominal capacity and
uses 80% capacity as an end-of-life benchmark. That does not establish the exact
five-cycle-ahead target construction used by v2.6.1.

Therefore:

```text
source metric documented: true
aligned to v2.6.1 target: false
predictive target ready: false
```

## Decision

```text
source document recovery: completed_with_remaining_binding_gaps
bounded inventory binding: eligible_for_read_only_inventory_binding
cross-cohort comparability: not_admitted
predictive validation: blocked
overall: source_evidence_recovered_gate_not_passed
```

The next step may inspect only:

- the checksum of `SNL LFP.zip`;
- the zip central directory;
- entry names, sizes, CRC values, and paths;
- an explicit parsed-label provenance manifest.

It must not extract the archive, read CSV rows, merge cohorts, or run a model.

## Scientific Closeout

- Result: `source_document_evidence_partially_recovered`
- Evidence level: `authoritative_study_documentation_without_local_artifact_binding`
- Classification: `diagnostic`
- Strongest evidence: official Battery Archive, OSTI, and Sandia records document
  the cell model, nominal capacity, equipment, protocol groups, and the
  regime-specific LFP voltage range.
- Primary limitation: no checksum-verified relationship connects the local
  archive entries to the documented cells and conditions. Calibration,
  uncertainty, data-distribution version, and target alignment remain unresolved.

This result is suitable for bounded inventory-binding design and provenance
contracts. It is not suitable for CSV analysis, cross-cohort equivalence,
predictive validation, model selection, mechanism claims, or engineering
decisions.

## Preservation Boundary

The package verifies and preserves:

- v2.6.4 checksum: `2776bc152c0e4655f0c90ec6513883aea3758cac7fac687e02e5685c72dfdb6f`;
- prior overall decision: `not_admitted_for_cross_cohort_validation`;
- persistence MAE: `3.425575369058076`;
- Ridge MAE: `4.15369918179312`;
- `PLATFORM_VERSION = 2.4.0`;
- no network, credential, raw-data read, archive extraction, source mutation,
  inference, model execution, or metric recomputation.

## Run

Preview without writes:

```powershell
python -m src.platform_core.battery_source_evidence_recovery --json preview
```

Run the deterministic audit:

```powershell
python -m src.platform_core.battery_source_evidence_recovery --json run
```

Validate an output:

```powershell
python -m src.platform_core.battery_source_evidence_recovery --json validate outputs/v2_6_battery_snl_lfp_source_evidence/recovery_summary.json
```

Local details:

- `outputs/v2_6_battery_snl_lfp_source_evidence/source_document_register.json`;
- `outputs/v2_6_battery_snl_lfp_source_evidence/recovery_matrix.json`;
- `outputs/v2_6_battery_snl_lfp_source_evidence/recovery_summary.json`.

Tracked compact summary:

- `data/processed/battery_v2_6_5_snl_lfp_source_evidence_summary.json`.
