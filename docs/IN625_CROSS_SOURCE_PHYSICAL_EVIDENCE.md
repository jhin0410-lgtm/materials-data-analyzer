# IN625 cross-source physical evidence

This research path broadens the IN625 LPBF evidence base beyond one NIST benchmark while preserving the exact acceptance boundary of AMB2018-02 Stage 1.

## Two different scientific questions

### 1. Exact AMB2018-02 AMMT completion

Issue #76 asks whether the missing cells of the AMMT bare-plate experiment can be populated by independently traceable physical measurements under the same benchmark/testbed and calibration semantics:

- 137.9 W / 800 mm/s: at least 3 independent traces;
- 137.9 W / 1200 mm/s: at least 3 independent traces;
- 179.2 W / 400 mm/s: at least 3 independent traces.

A different machine, a nearby power, a shared `P/v`, or a publication mean cannot close that contract. NIST explicitly reports that AMMT commanded powers were later found to be miscalibrated, while the commercial build machine (CBM) power levels were as expected. Therefore commercial-machine 150 W / 195 W values must not be relabeled as AMMT 137.9 W / 179.2 W.

### 2. Independent physical validation of the research system

The wider Virtual Research Partner should use real measurements from other laboratories, machines, material states, and characterization pipelines. Those data are valuable because they test whether a model or physical conclusion transfers beyond a single benchmark. They must, however, remain stratified by their actual provenance and experimental context.

## Registry

`configs/research/in625_single_track_external_source_candidates.v1.json` stores candidate physical sources independently of the Materials Project external-source registry. Each source binds:

- authority, DOI or repository record, and access status;
- extraction mode (`raw_dataset`, `author_table`, `author_figure`, etc.);
- experiment-family identity so a paper and its repository cannot count as independent experiments;
- machine/testbed;
- material and material state;
- laser-power semantics and calibration binding;
- spot-size semantics;
- characterization and replication semantics;
- only process coordinates that have already been verified from the source.

An empty `process_points` list means the source exists but row-level ingestion remains blocked. It is not permission to infer the missing matrix.

## Provenance strength and comparability are separate axes

`in625_external_physical_evidence.py` intentionally does not collapse source quality and experimental comparability into one idea.

Evidence strata include:

1. `exact_benchmark_compatible` — authoritative raw evidence from the NIST AMMT benchmark with the exact calibration semantics;
2. `machine_stratified_physical` — authoritative raw physical data from a different machine/process context;
3. `adjacent_physical` — authoritative raw physical data with a material-state or process-state mismatch that must remain explicit;
4. `publication_derived_physical` — physical results available only through an author table/figure or publication representation;
5. `diagnostic_or_simulated` — useful for software/physics diagnostics but not physical validation;
6. `unusable` — insufficient provenance or ambiguous semantics.

The registry also retains `comparability_class`, because a publication-derived result can still be geometrically or machine-wise close to the benchmark without gaining raw-data provenance.

## Common intake

`in625_external_physical_evidence_intake.py` validates records against the registry and fails closed.

For every record it requires an explicit source candidate, experiment family, physical replication unit, source locator, machine, material state, power semantics, calibration semantics, process coordinate, response name/value/unit, and whether the physical unit is an independent replicate.

For `raw_dataset` sources it also requires source bytes bound by SHA-256 and byte size. Paths must be relative POSIX paths inside the intake root; traversal, drive paths, symlinks, missing files, digest changes, and size changes are rejected.

Most importantly, an ingested `(power, speed)` pair must already occur in that candidate's verified `process_points`. A record cannot create a new source condition by self-declaration.

## Replication and overlap

The physical replication key is based on experiment family plus replication-unit identity. Repeated microscopy measurements of one section or one track can improve measurement precision but do not become independent process replicates.

When the same experiment appears in a raw repository and an associated paper, the experiment-family identity prevents double counting. The repository and paper are different evidence representations of the same physical experiment.

## Current source set

### Exact NIST AMB2018-02 AMMT baseline

NIST `mds2-3830` contains the frozen AMMT cross-sectional optical-microscopy results. It is exact benchmark evidence, but it contains the existing three process cells rather than the three missing Stage 1 cells. Exact compatibility therefore does not imply #76 completion.

### NIST `mds2-2923`

DOI `10.18434/mds2-2923` is an authoritative NIST repository of IN625/IN718 bare-plate single-track cross-sectional micrographs and melt-pool width/depth measurements. NIST lists `Master_TrackList_Measurements.xlsx` plus hundreds of micrograph/top-view resources and describes experiments on three LPBF machines with varied power, scan speed, and spot diameter.

The master workbook is the row-level authority. In the current execution environment the listed XLSX download repeatedly fails before bytes can be authenticated, so its exact rows are not registered or inferred. A request for an alternate authoritative transfer path and calibration clarification has been sent to the NIST data author.

### Weaver, Heigel & Lane

DOI `10.1016/j.jmapro.2021.10.053` reports physical single-track experiments with D4sigma spot sizes from 50 um to 322 um, cross-sectioning, optical microscopy, and thermography. It is associated with the `mds2-2923` experiment family and therefore must not be counted as an independent experiment in addition to repository rows that represent the same tracks.

### Criales et al.

DOI `10.1016/j.ijmachtools.2017.03.004` reports physical Alloy 625 experiments on an EOS M270, including melt-pool width/depth and thermal monitoring. These measurements are useful external physics/model evidence, but EOS machine settings, powder/coupon state, optics, and calibration are not AMMT benchmark semantics.

### Shrestha & Chou

DOI `10.1016/j.jmapro.2020.11.023` reports physical IN625 single tracks on an EOS M270 including 195 W at 400 mm/s and 800 mm/s with surface/metallographic characterization. The numerical neighborhood of an AMMT target does not make these tracks AMMT evidence.

### Li, Guo & Zhao

DOI `10.1016/j.jmatprotec.2016.12.033` reports physical IN625 single-track selective-laser-melting experiments over a broad process range using a laboratory system. The exact row matrix and independent replication semantics remain acquisition work before model ingestion.

### Ghosh et al.

The NIST-authored JOM work `Single Track Melt Pool Measurements and Microstructures in Inconel 625` reports seven distinct bare-plate tracks across a designed power/speed set with cross-sectional measurements. This is valuable publication-derived machine-stratified evidence, but it is not AMB2018-02 AMMT calibration evidence.

### Additional source frontier

The source search also identified a large physical Alloy 625 single-track study on a Concept Laser M2 with 175 Alloy 625 cases spanning power, scan speed, beam diameter, and layer thickness. It is a strong candidate for a subsequent authoritative row-level extraction, but parameter ranges alone are not treated as a Cartesian process matrix. NIST also publishes CBM thermography for AMB2018-02; because CBM and AMMT are different systems with different measurement geometries and power-calibration semantics, those data belong in a machine-stratified layer rather than filling AMMT cells.

## What the system may conclude

Cross-source data may support claims such as:

- a trend is reproduced across independent machines or laboratories;
- a model's residuals shift systematically by machine, spot size, or material state;
- a hypothesis fails leave-one-source-out validation;
- a proposed scaling relation remains or does not remain stable after machine stratification.

It may not conclude that:

- equal `P/v` means two experiments are equivalent;
- a 195 W commercial-machine track is a 179.2 W AMMT track;
- repeated measurements of one track are independent traces;
- a paper and its repository are two independent studies;
- publication-derived values have raw-data provenance;
- external physical evidence closes #76 unless the exact Stage 1 contract is satisfied.

## Next scientific analyses after row-level acquisition

1. Build `source x machine x material_state x power x speed x spot_size x response x independent_replication` support matrices.
2. Detect source overlap before any fit.
3. Fit machine/source-stratified models rather than naïve pooled regressions.
4. Run leave-one-source-out validation.
5. Run sensitivity analyses for powder vs bare plate, spot size, power semantics, and measurement definition.
6. Promote a cross-source claim only when it survives these analyses and its raw/publication provenance tier is reported.

This broader evidence layer is complementary to #76, not a workaround for it.
