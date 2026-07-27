# NIST AM-Bench 2018-02 Cross-Repository Process–Characterization Handoff

## Purpose

This workflow is the first real cross-repository case in which:

- `materials-characterization-analyzer` owns characterization measurements and their provenance;
- `materials-data-analyzer` owns process variables and process–characterization integration;
- both repositories independently validate the same ten physical trace identities before joining.

The case uses NIST AM-Bench 2018-02 single laser tracks on IN625 in the NIST Additive Manufacturing Metrology Testbed (`AMMT`).

## Pinned producer

The workflow checks out `materials-characterization-analyzer` at:

```text
ca7242331d3aab7d5d4999df297ccc1a8b011934
```

Producer changes cannot silently alter this validation. Updating the pin requires deliberate review and another successful workflow run.

## Ownership boundary

### Characterization producer

The producer exports:

- ten stable AMMT trace `sample_id` values;
- NIST case and trace identity;
- IN625 material and AMMT system context;
- melt-pool width mean and within-measurement standard deviation;
- melt-pool depth mean and within-measurement standard deviation;
- measurement method, source type, source SHA-256, preprocessing ID, and quality flag;
- raw-image-not-parsed and process-conditions-not-included declarations.

The producer does not export laser power, scan speed, or a derived line-energy descriptor.

### Process consumer

The consumer supplies:

- corrected actual laser power;
- scan speed;
- NIST case and trace identity;
- material and system identity.

The consumer does not alter producer feature values or independently remeasure the optical micrographs.

## Identity gate

An external process table is admitted only when:

1. it contains a unique, nonblank `sample_id` column;
2. its `sample_id` set exactly matches the producer bundle;
3. at least one additional identity column is shared;
4. every shared `case_id`, `trace_number`, `material`, and `system` value agrees for every sample;
5. no row-order join or metadata inference is used.

After validation, producer context columns that are absent from the process table are appended by an explicit one-to-one `sample_id` merge. The resulting validated process input is saved and checksummed.

## User command

First generate the producer bundle:

```powershell
python <materials-characterization-analyzer>/scripts/export_nist_ambench_2018_02_optical_metrology_bundle.py `
  --config <materials-characterization-analyzer>/case_studies/nist_ambench_2018_02/case_config.json `
  --output <materials-characterization-analyzer>/outputs/nist-ambench-2018-02-optical-metrology
```

Then consume it with the process table:

```powershell
python scripts/consume_characterization_handoff_bundle.py `
  --bundle-manifest <materials-characterization-analyzer>/outputs/nist-ambench-2018-02-optical-metrology/characterization_handoff_bundle.json `
  --process-table data/case_studies/nist_ambench_2018_02/source_process_conditions.csv `
  --output outputs/cross-repository-nist-ambench-2018-02
```

The output directory must be new or empty.

## Expected evidence

Producer:

- 10 samples;
- 10 optical-metrology measurements;
- 40 feature records;
- 40/40 source hashes;
- 40/40 preprocessing identifiers;
- one instrument: `optical_microscopy_metrology`.

Consumer:

- 10 matched samples;
- 0 process-only samples;
- 0 characterization-only samples;
- verified identity columns: `case_id`, `trace_number`, `material`, `system`;
- 0 identity mismatches;
- integrated process columns for actual power and scan speed;
- four optical-metrology feature columns;
- no model or optimization artifact.

The tracked characterization source tables in both repositories must also be byte-identical. This prevents two independently edited transcriptions from appearing to represent the same NIST evidence.

## Scientific closeout

**Evidence level: Diagnostic**

Supported:

- one controlled benchmark material and system are used;
- ten explicit trace identities link process conditions and characterization results;
- three process conditions include trace-level replication;
- source and preprocessing provenance survive the repository boundary;
- the integrated values reproduce the rounded NIST case-level melt-pool summary;
- software can reject identity-conflicted process tables before integration.

Not supported:

- independent extraction from raw optical images;
- causal separation of power and scan speed because only three process combinations exist;
- process optimization or predictive modeling;
- uncertainty propagation beyond source-reported values;
- transfer to powder-bed builds, other alloys, systems, atmospheres, or geometries;
- engineering release or certification decisions.

This case is suitable as a credible end-to-end process–characterization demonstration. It remains insufficient for a general predictive Virtual Research Partner model.
