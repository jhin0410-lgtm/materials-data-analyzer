# TM-Fe-Si cross-repository descriptive case

Status: `real_source_replay_complete`

This is the first real end-to-end case connecting a
`materials-characterization-analyzer` producer bundle to a
`materials-data-analyzer` consumer-owned physical-property table.

## Sources

- Data in Brief article DOI: `10.1016/j.dib.2022.108868`
- Mendeley Data DOI: `10.17632/gp8rkw2k6v.2`
- dataset version: `2`
- license: `CC BY 4.0`
- compositions: Ti/Zr/Hf/V/Nb/Ta variants at nominal `TM7Fe52Si41`

The MCA checksum-bound XRD descriptive producer was merged at
`9be7c5ab1306639d90db15b61d2a7139073758ba`. Its actual source replay produced
6 samples, 6 measurements and 36 review-required XRD features while retaining a
maximum downstream use of `descriptive`.

## Consumer-owned magnetic quantity

MDA reads only the explicitly labeled 300 K M-H trace in columns G:H of each
of the six frozen public workbooks. The raw workbook filename, size and SHA-256
must match the audited source exactly.

The consumer records the first and last observed loop endpoints near +30 kOe
(accepted field tolerance: ±0.005 kOe) and reports:

- endpoint magnetization mean, in `emu/g`;
- absolute difference between the two endpoint magnetizations;
- actual endpoint field minimum and maximum;
- source SHA-256 and loop point count.

The value is deliberately named
`mh_300k_plus30koe_endpoint_mean_emu_g`. It is **not** called saturation
magnetization because the source subset and this workflow do not establish a
saturation criterion. No interpolation, smoothing, outlier removal, coercivity
extraction or Curie-temperature extraction occurs.

## Join contract

The MCA bundle is first consumed through the existing MDA characterization
workflow without an external process table. The case consumer then validates all
three fields before one-to-one joining the magnetic observations:

1. `sample_id`
2. `nominal_composition`
3. `preparation_family_id`

The frozen preparation family is
`tm-fe-si-arc-melt-remelt-1050c-1d-air-cool`.

Row-order, spreadsheet-row, filename-position and inferred exact-aliquot joins
are prohibited. The stable identity means nominal composition plus preparation
family. The publication does not establish that the powdered XRD portion and
bulk magnetic specimen were the same physical aliquot.

## Actual replay

The PR implementation was installed from its CI-built wheel and replayed against
the checksum-bound MCA XRD bundle plus all six real M-H workbooks.

Observed result:

- status: `verified_descriptive_cross_repo_case`
- samples: `6`
- characterization evidence: `Diagnostic`
- requested use: `descriptive`
- maximum allowed use: `descriptive`
- cross-modal table SHA-256:
  `4efa75f7ddf76339d63085a281e5b420617d17efddbd9e3b0b9bb53af53c3570`
- magnetic consumer table SHA-256:
  `4c5d28ff0f943c883e6b906d686a382d163a79cb672c679c6a9fbb2e4a15987c`

A negative-control run requested `predictive` use. It exited with code `1`
because the producer maximum is `descriptive`; neither the requested output nor
the transactional staging directory remained afterward.

The compact replay evidence is frozen at
`configs/research/tm_fe_si_cross_repo_real_replay.v1.json`.

## Run

After generating the MCA bundle with the producer documented in the MCA
repository, run from the MDA repository root:

```powershell
$python = (Resolve-Path ".\.venv313\Scripts\python.exe").Path

& $python -m materials_data_analyzer.tm_fe_si_cross_repo_cli `
  --bundle-manifest "<MCA_BUNDLE>\characterization_handoff_bundle.json" `
  --magnetic-source-dir "C:\Users\USER\Desktop\Datasets on materials research of hard ferromagnet in TM-Fe-Si (TM=Ti, Zr, Hf, V, Nb, and Ta) ternary systems" `
  --requested-use descriptive `
  --output ".\outputs\tm_fe_si_cross_repo_descriptive"
```

The output is transactional and never overwrites an existing directory. It
contains the normal MDA characterization-import evidence, six-row magnetic
consumer table, joined descriptive table, source manifest, summary and report.
Raw workbooks are not copied into outputs or committed.

## Scientific closeout

**Diagnostic.** The real workflow supports per-composition descriptive
inspection and demonstrates provenance-preserving software/identity handoff.

It does **not** establish:

- independent XRD peak truth;
- phase identity or phase fraction;
- absolute XRD intensity comparability;
- saturation magnetization, coercivity or Curie temperature;
- identical physical XRD/VSM aliquots;
- statistically generalizable association;
- predictive performance;
- causality;
- engineering-release readiness.

There are only six nominal compositions. The workflow intentionally does not
compute correlation significance, fit predictive models, or promote a
mechanistic claim. A stronger scientific claim requires a new validation design
with exact sample lineage, hypothesis-relevant metadata/truth, and enough
independent samples for the stated inference.
