# Battery SNL LFP Transition Artifact Evidence Gate

Status: `v2.6.10_feature_stage_complete`

## Objective

v2.6.10 answers the narrowest unresolved question left by v2.6.9:

> Does an authoritative source explain the anomalous fourth cycle-summary row
> without requiring a broader time-series or full-file read?

The answer is bounded. The official Battery Archive SNL study page attributes
periodic spikes in the study data to transitions between the three-cycle
capacity check and the normal cycling round. v2.6.10 compares that document-level
statement with the checksum-bound row-4 contrasts already recorded by v2.6.9.

This stage does not read the raw archive, CSV payloads, or time-series entries.
It does not establish the exact identity of row 4.

## Upstream identity

The gate verifies and preserves:

- v2.6.5 source-evidence checksum:
  `b6e0c950f11cb1edfbd3afdd15776af25c76b092d130d6038b6653ecd63ba846`;
- v2.6.9 cycle-regime checksum:
  `dc6c7c4046d81ddf879c2f1538eab75708dd387f7d9d940adc0c6dfc2c3e01dc`;
- local archive SHA-256:
  `006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d`;
- v2.6.9 decision:
  `candidate_supported_not_established`.

## Authoritative source evidence

The bounded source is the official Battery Archive SNL study page:

```text
https://www.batteryarchive.org/snl_study.html
```

The page records that periodic spikes are caused by the transition between the
three-cycle capacity check and the normal cycling round.

Evidence scope:

- authoritative at the study-description level;
- relevant to transition artifacts in this dataset family;
- not a versioned dataset snapshot;
- not an exact CSV row map;
- not a cycle-command or step log.

## Row-4 audit

No new source values are read. The gate reuses the exact decimal strings already
tracked by v2.6.9.

For each of the three representatives, row 4 is compared with the range across
rows 5-8 using:

- minimum current;
- maximum current;
- minimum voltage;
- maximum voltage;
- charge capacity;
- discharge capacity.

No fitted threshold, tolerance, rounding, smoothing, imputation, or unit
conversion is used.

### Observed contrasts

| Protocol family | Row-4 fields outside rows 5-8 |
| --- | --- |
| 0-100% SOC | charge capacity, discharge capacity |
| 20-80% SOC | minimum voltage, maximum voltage, charge capacity, discharge capacity |
| 40-60% SOC | minimum voltage, maximum voltage, charge capacity, discharge capacity |

Charge and discharge capacity are outside the rows 5-8 ranges in all three
representatives.

## Decision

```text
official transition-artifact evidence:
recovered_document_level

row-4 transition pattern:
observed_all_representatives

row 4 to source transition binding:
transition_consistent_not_row_bound

row-4 exact identity:
not_established

capacity-check versus bulk-cycle discrimination:
candidate_supported_not_established

time-series read gate:
not_authorized_no_provider_step_or_command_binding

overall:
transition_artifact_consistency_recorded_gate_not_passed
```

The official note and the three row-4 contrasts are mutually consistent.
However, consistency is not identity. The source does not say that a particular
converted CSV row is the transition record, and the archive still lacks a
verified step identifier, command log, conversion map, or instrument-channel
binding.

## Why time-series expansion is not authorized

A larger time-series read would add measured samples but would not, by itself,
provide the missing commanded-step semantics. Without provider-backed step
metadata or a conversion contract, more rows could strengthen a pattern while
still failing to identify the experiment command.

Therefore v2.6.10 explicitly stops the payload-expansion path.

A future step may proceed only if at least one provider-backed artifact exists:

- a cycle-to-step conversion map;
- an Arbin schedule or command export;
- a documented step identifier;
- a provider-issued explanation linking converted cycle rows to protocol phases.

Without such evidence, the scientifically correct state is to preserve the
diagnostic boundary rather than collect more data without a discriminating
contract.

## Scientific closeout

Classification: **Diagnostic**

- Result:
  `source_transition_artifact_consistent_with_row4_pattern_not_row_bound`
- Evidence level:
  official study artifact note plus checksum-bound row-4 contrasts in three
  representatives.
- Strongest evidence:
  the official source attributes periodic spikes to capacity-check/normal-round
  transitions, and row 4 differs from rows 5-8 in every representative.
- Primary limitation:
  no exact row, step, command, conversion, or channel binding exists.
- Suitable for:
  provenance closeout, transition-artifact diagnostics, and deciding not to
  broaden reads without provider metadata.
- Unsuitable for:
  confirmed capacity-check labels, command reconstruction, universal cycle
  classification, cohort comparison, predictive validation, or engineering
  decisions.

## CLI

Preview the tracked-only contract:

```powershell
python -m src.platform_core.battery_snl_lfp_transition_artifact_evidence_gate --json preview
```

Generate the deterministic result:

```powershell
python -m src.platform_core.battery_snl_lfp_transition_artifact_evidence_gate --json run
```

Validate the tracked summary:

```powershell
python -m src.platform_core.battery_snl_lfp_transition_artifact_evidence_gate --json validate data/processed/battery_v2_6_10_snl_lfp_transition_artifact_evidence_summary.json
```

## Outputs

Local full result:

```text
outputs/v2_6_battery_snl_lfp_transition_artifact_evidence/
└─ transition_artifact_evidence_result.json
```

Tracked summary:

```text
data/processed/battery_v2_6_10_snl_lfp_transition_artifact_evidence_summary.json
```

Tracked checksum:

```text
0093de000c25cfcbbd36eaf8216eabc7fb3bc3db23b724dbffcb69b4d77ddf28
```

## Preservation boundary

v2.6.10 does not:

- access the network or credentials during execution;
- read archive bytes or CSV payloads;
- read time-series entries;
- fit thresholds or classify rows;
- infer commands, steps, channels, or physical-cell identity;
- merge cohorts;
- train or evaluate a model;
- recompute v2.6.1 metrics;
- change `PLATFORM_VERSION`, which remains `2.4.0`.
