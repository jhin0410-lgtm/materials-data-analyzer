# NASA External Source Candidate Audit

This step starts only after a verified `NASA-EXTERNAL-001` result has stopped the
bounded NASA research loop with `external_evidence_required`.

It does **not** resume the stopped loop, download a dataset, train a model, or
upgrade predictive evidence. It screens authoritative external-source candidates
against the generated evidence contract and fails closed when scientific
semantics are unresolved or incompatible.

## Current first candidate

The registry contains the KIT Luh/Blank 2024 result-data cohort:

- dataset DOI: `10.35097/1969`;
- publication DOI: `10.1038/s41597-024-03831-x`;
- 228 LG INR18650HG2 NMC/C+SiO cells;
- four aging-temperature settings: 0, 10, 25, and 40 degree_Celsius;
- 48 cyclic-aging operating conditions with three cells per condition;
- version-2 result archive size: 333.4 MB;
- license: CC BY 4.0.

The publication describes a crossed cyclic design across temperature, voltage
window, and charge/discharge-rate combinations. The cohort is structurally
strong and remains valuable as a separate battery-aging benchmark candidate.
It is **not**, however, scientifically admissible as direct evidence for the
current NASA exact-horizon external diagnostic.

## Semantic closeout

All three required semantic comparisons are now resolved as
`confirmed_mismatch`.

### 1. Protocol-temperature semantics: mismatch

The NASA importer reads `ambient_temperature` from each source discharge
operation and the protocol summary derives `ambient_temperature_median_c` as the
battery-level median of those discharge-operation values. It is therefore a
protocol field associated with the NASA discharge measurements used to build the
capacity trajectory.

The KIT publication distinguishes the cell's aging operating temperature
(0-40 degree_Celsius) from the reference capacity measurement. Before a check-up,
all cells are moved to room temperature, 25 degree_Celsius, and stabilized. The
remaining capacity is then measured during the standardized check-up at that
room temperature.

Therefore neither substitution is valid for the NASA contract:

- KIT aging temperature is an exposure/operating condition, not the ambient
  condition of the comparable capacity measurement;
- KIT check-up capacity temperature is 25 degree_Celsius for all cells and
  cannot provide the required exact-temperature groups.

No rounding, binning, inferred mapping, or use of pool setpoint as a replacement
is permitted.

### 2. Exact-horizon semantics: mismatch

Battery Degradation Intelligence uses a fixed warm-start horizon. The target row
must exist exactly at `origin_cycle + horizon`, where NASA `cycle_index` is the
one-based ordinal of discharge operations. Missing target rows are excluded;
they are not interpolated.

KIT comparison capacity is measured in scheduled check-ups. The first follow-up
check-up occurs one week after the initial check-up and subsequent check-ups are
performed at three-week intervals. Capacity trajectories are also represented
against check-up/cycle counters and equivalent full cycles. Those observations
cannot be relabeled as the NASA discharge-operation horizon without changing the
scientific question.

### 3. Target/reference semantics: mismatch

The current public NASA importer preserves each source discharge `Capacity` and
derives `capacity_retention_percent` against the documented 2.0 Ah rated
capacity. It explicitly does not use the first observed discharge as the 100%
reference.

KIT determines remaining usable capacity through a standardized full CC-CV
charge-discharge check-up at 25 degree_Celsius and 1/3 C with its documented
cut-off condition. That is a useful and arguably cleaner reference-performance
measurement, but it is not the same target measurement protocol as the NASA
trajectory used by the current exact-horizon analysis.

## Current disposition

The expected audit disposition for `kit-luh-blank-2024-result-v2` is now:

```text
scientifically_ineligible
```

with these blockers:

```text
protocol_temperature_semantics_mismatch
exact_horizon_semantics_mismatch
target_reference_semantics_mismatch
```

This means **ineligible for the current NASA diagnostic**, not low-quality data.
The source remains an independent candidate for a separately predeclared
battery-aging benchmark whose target, horizon, and protocol definitions are
native to KIT.

The tool continues to return:

- `eligible_for_predeclared_diagnostic=false`;
- `eligible_for_external_validation_claim=false`;
- predictive evidence level `Unsupported`.

No KIT download is required to establish this semantic disposition because the
mismatches are already explicit in the authoritative publication and the NASA
analysis contract.

## Known data-quality events

The source publication documents temperature-control events that must not be
silently removed or overwritten if KIT is used in a future standalone benchmark:

- 2022-11-27 22:40 UTC to 2022-11-29 16:50 UTC: cooling/heating interruption
  caused the colder pools to operate around 9-13 degree_Celsius and the warm
  pool around 32-33 degree_Celsius;
- 2023-04-23 around 11:47: a Peltier circuit failure in the 25 degree_Celsius
  pool lowered average cell temperature by about 2.5 degree_Celsius and
  increased variation;
- cell surface temperatures can differ materially from the pool setpoint during
  operation.

Any future standalone KIT ingestion must preserve these conditions through
measured values, quality flags, explicit exclusions, or a documented sensitivity
analysis. This NASA audit does not choose that preprocessing policy.

## Run the source audit

Use the requirement generated by the completed external-data action:

```powershell
.\.venv313\Scripts\python.exe `
  .\scripts\audit_nasa_external_source_candidates.py `
  --requirement `
  .\outputs\nasa_autonomous_loop_20260805-231546\actions\NASA-EXTERNAL-001\reports\external_data_requirement.json `
  --registry `
  .\configs\research\nasa_external_source_candidates.v1.json `
  --output `
  .\outputs\nasa_external_source_audit\source_candidate_audit.json
```

The current KIT registry entry is expected to produce:

```text
scientifically_ineligible
```

## NASA closeout boundary

Do not resume the NASA bounded research loop, relax the fixed-horizon contract,
pool KIT cells with NASA cells, redefine temperature groups, or change the target
merely to make an external source fit.

NASA remains stopped at `external_evidence_required` until an independent source
is found whose protocol-temperature, exact-horizon, and target/reference
semantics actually match the predeclared contract. In parallel, KIT may be
considered for a **separate** benchmark with its own predeclared scientific
question.
