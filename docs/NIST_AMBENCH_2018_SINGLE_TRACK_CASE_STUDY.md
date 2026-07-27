# NIST AM-Bench 2018-02 Single-Track Case Study

## Purpose

This is the first real process-to-characterization workflow built on the
cross-repository handoff.

It links trace-level process conditions from NIST AM-Bench 2018-02 to reported
optical-microscopy measurements of melt-pool width and depth using explicit
`sample_id` values. It is not a Battery workflow, an image-segmentation
benchmark, or a predictive-model exercise.

## Official source

The tracked table is transcribed from official NIST pages:

- experiment description:
  `https://www.nist.gov/ambench/amb2018-02-description`
- melt-pool cross-section results:
  `https://www.nist.gov/ambench/chal-amb2018-02-mp-xsection`
- correction notice:
  `https://www.nist.gov/ambench/challenges-and-descriptions`
- public data record:
  `https://data.nist.gov/od/id/mds2-3830`
- DOI: `10.18434/mds2-3830`

The source contains ten IN625 traces created on the NIST Additive Manufacturing
Metrology Testbed using three power/speed settings. The cross sections were
measured with optical microscopy.

The tracked CSV is a manually transcribed compact table, not a raw instrument
export or an independent image remeasurement. Its SHA-256 is fixed in
`source_contract.json`.

## Metadata correction

The older results table reports a laser spot-size FWHM of 45 um. NIST's current
experiment description and challenge notice correct the AMMT spot size to
100 um FWHM.

Both values are preserved:

- `legacy_reported_spot_size_fwhm_um = 45`
- `corrected_spot_size_fwhm_um = 100`

The process table uses the corrected value. The reported melt-pool geometry is
not modified.

The workflow also preserves commanded and calibrated laser power separately.
For the AMMT traces:

- commanded 150 W corresponds to calibrated 137.9 W;
- commanded 195 W corresponds to calibrated 179.2 W.

## Run

```powershell
python scripts/run_nist_ambench_single_track_case_study.py `
  --output outputs/nist_ambench_2018_single_track
```

Optional explicit inputs:

```powershell
python scripts/run_nist_ambench_single_track_case_study.py `
  --source-table data/case_studies/nist_ambench_2018_single_track/trace_measurements.csv `
  --source-contract data/case_studies/nist_ambench_2018_single_track/source_contract.json `
  --output outputs/nist_ambench_2018_single_track
```

## Outputs

The case-study root contains:

- `validated_trace_measurements.csv`
- `process_conditions.csv`
- `characterization_features_long.csv`
- `case_summary.csv`
- `melt_pool_width_vs_linear_energy.png`
- `melt_pool_depth_vs_linear_energy.png`
- `case_study_report.md`
- `case_study_manifest.json`

The `handoff/` subdirectory contains the standard characterization handoff:

- validated long features;
- feature dictionary;
- one-row-per-trace wide features;
- integrated process/characterization table;
- sample join audit;
- handoff manifest.

All ten trace identifiers must be `matched`. No row-order join is used.

## Validation

The workflow checks:

1. the tracked CSV checksum;
2. ten unique trace and sample identifiers;
3. exact A/B/C trace membership;
4. commanded and calibrated power settings;
5. scan speeds and the spot-size correction;
6. non-negative reported melt-pool dimensions;
7. reproduction of NIST's class means and between-trace standard deviations
   after rounding to one decimal place;
8. four characterization feature records per trace;
9. ten explicit process-to-characterization matches;
10. absence of model fitting and raw-image reanalysis.

## Scientific closeout

**Diagnostic**

### Strongest evidence

NIST's official process settings and reported optical cross-section measurements
are connected through ten trace identifiers, and the published case-level
summary statistics are reproduced.

### Primary limitation

There are only three unique process settings and ten traces. Replicates improve
descriptive repeatability estimates but do not provide broad or independent
coverage of the process space. The compact table is transcribed from reported
results, and the original images are not remeasured here.

### Suitable for

- demonstrating a real process-to-characterization data contract;
- verifying sample-ID joins and provenance handling;
- descriptive comparison among the three reported settings;
- illustrating metadata correction without silently overwriting source history.

### Unsuitable for

- causal process optimization;
- predictive-model validation;
- mechanism identification;
- generalization to other machines, alloys, or process windows;
- replacing the official NIST metrology or raw-image analysis.
