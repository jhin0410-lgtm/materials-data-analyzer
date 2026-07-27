# NIST AM-Bench 2018-02 Process–Characterization Case Study

## Purpose

This case study is the first real-data use of the cross-repository
characterization-feature handoff. It links explicit laser-processing conditions
to source-reported optical-microscopy melt-pool measurements through one stable
`sample_id` per AMMT trace.

It is deliberately small and complete: ten traces, three process conditions,
trace-level width/depth measurements, deterministic integration, descriptive
summaries, plots, and a scientific closeout. It does not train a predictive
model.

## Official Sources

- NIST benchmark description:
  `https://www.nist.gov/ambench/amb2018-02-description`
- NIST transverse cross-section results and Table 2 values:
  `https://www.nist.gov/ambench/chal-amb2018-02-mp-xsection`
- NIST Public Data Repository optical-micrograph record:
  `https://doi.org/10.18434/mds2-3830`
- Associated experiment publication:
  `https://doi.org/10.1007/s40192-020-00169-1`

The tracked numeric tables were manually transcribed from the official NIST
results page and checked against the published case-level means and standard
deviations. No optical image or third-party paper content is redistributed.

The PDR record is versioned. At implementation time the latest listed release
was `1.0.3` dated 2026-01-05. The trace-level process and measurement values in
this repository come from the NIST benchmark/result webpages, not from parsing
the PDR image files.

## Experimental Context

- Material: nickel-based superalloy IN625.
- System: NIST Additive Manufacturing Metrology Testbed (`AMMT`).
- Geometry: individual laser scan tracks on a bare substrate without powder.
- Cases:
  - A: actual power 137.9 W, scan speed 400 mm/s, traces 5–7;
  - B: actual power 179.2 W, scan speed 800 mm/s, traces 8–10;
  - C: actual power 179.2 W, scan speed 1200 mm/s, traces 1–4.
- Characterization: polished transverse cross sections measured using the
  microscope-control metrology mode reported by NIST.
- Reported individual-measurement uncertainty: approximately 0.5 µm.

The corrected AMMT laser powers are used. Commanded powers are not substituted
for the source-reported actual powers.

## Tracked Inputs

### `source_process_conditions.csv`

One row per trace with:

- stable `sample_id`;
- case and trace identifiers;
- corrected actual laser power;
- scan speed;
- system and material.

### `source_melt_pool_measurements.csv`

One row per trace with source-reported:

- melt-pool width mean and within-measurement standard deviation;
- melt-pool depth mean and within-measurement standard deviation.

These standard-deviation columns are the NIST-reported microscope measurement
statistics for each trace. They are distinct from the between-trace standard
deviations recomputed for each process case.

## Reproduction

```powershell
python scripts/build_nist_ambench_2018_02_case_study.py `
  --output outputs/nist_ambench_2018_02
```

The command performs no network access. It verifies the two tracked source
tables, converts the measurement table to the stable 12-column
characterization-feature contract, runs the explicit `sample_id` handoff, and
writes descriptive outputs.

## Main Outputs

- `ambench_characterization_features_long.csv`
- `ambench_process_conditions_normalized.csv`
- `characterization_features_validated_long.csv`
- `characterization_feature_dictionary.csv`
- `characterization_features_wide.csv`
- `integrated_sample_table.csv`
- `sample_join_audit.csv`
- `ambench_case_summary.csv`
- `melt_pool_width_by_linear_energy.png`
- `melt_pool_depth_by_linear_energy.png`
- `ambench_case_study_report.md`
- `ambench_case_study_manifest.json`

`linear_energy_density_j_mm` is calculated as actual laser power divided by
scan speed. It is a line-energy descriptor, not volumetric energy density. It
does not account for absorptivity, spot-size effects, thermal boundary
conditions, or material-property variation.

## Scientific Closeout

Status: `diagnostic`.

Supported:

- the tracked tables reproduce the source-reported ten trace measurements;
- all ten process and characterization rows join one-to-one by explicit
  `sample_id`;
- recomputed case-level width/depth means and between-trace standard deviations
  match NIST Table 2 after source-level rounding;
- the software produces deterministic integration, summaries, figures, and a
  provenance manifest.

Not supported:

- causal attribution to power, speed, or line energy independently;
- process optimization;
- predictive generalization beyond these ten AMMT traces;
- transfer to powder-bed builds, other machines, other alloys, or different
  surface/atmosphere conditions;
- replacement of the NIST metrology procedure;
- uncertainty propagation beyond the source-reported values.

The dataset has only three unique process conditions and ten traces. A model
fit would mostly memorize those conditions, so modeling is intentionally
excluded.

## License and Attribution

Repository code and original documentation are covered by the root MIT license.
The NIST data and webpages remain subject to NIST terms and attribution
requirements. This repository attributes NIST as the source and does not imply
NIST endorsement or certification of this project.
