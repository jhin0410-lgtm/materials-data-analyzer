# TM-Fe-Si cross-repository descriptive case

Status: `implementation_ready_for_real_source_replay`

This is the first real end-to-end case connecting a
`materials-characterization-analyzer` producer bundle to a
`materials-data-analyzer` consumer-owned physical-property table.

## Sources

- Data in Brief article DOI: `10.1016/j.dib.2022.108868`
- Mendeley Data DOI: `10.17632/gp8rkw2k6v.2`
- dataset version: `2`
- license: `CC BY 4.0`
- compositions: Ti/Zr/Hf/V/Nb/Ta variants at nominal `TM7Fe52Si41`

The MCA producer is the checksum-bound XRD descriptive case merged in
`materials-characterization-analyzer` at commit
`9be7c5ab1306639d90db15b61d2a7139073758ba`.

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

The MCA bundle is first consumed through the existing
`mda-characterization-import` implementation without an external process table.
The case consumer then validates all three fields before one-to-one joining the
magnetic observations:

1. `sample_id`
2. `nominal_composition`
3. `preparation_family_id`

Row-order, spreadsheet-row, filename-position and inferred exact-aliquot joins
are prohibited. The stable identity means nominal composition plus preparation
family. The publication does not establish that the powdered XRD portion and
bulk magnetic specimen were the same physical aliquot.

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

The output is transactional and is never written over an existing directory.
It contains the normal MDA characterization-import evidence, the six-row
magnetic consumer table, the joined descriptive table, source manifest, summary
and report. Raw workbooks are not copied into outputs or committed.

## Scientific closeout

**Diagnostic.** This case demonstrates a real, provenance-preserving software
and identity handoff and supports per-composition descriptive inspection.

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

There are only six nominal compositions. The workflow therefore intentionally
does not compute correlation significance, fit predictive models, or promote a
mechanistic claim. A scientifically stronger claim would require independent
sample identity and measurement metadata plus a validation design appropriate
to the specific hypothesis.
