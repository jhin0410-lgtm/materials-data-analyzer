# NIST AM-Bench 2018-02 compact source package

This directory contains a compact, manually transcribed table from the official
NIST AM-Bench 2018-02 melt-pool cross-section results and a source contract that
binds the table to the official pages and DOI.

Files:

- `trace_measurements.csv`: ten trace-level process and reported optical
  cross-section measurement rows;
- `source_contract.json`: source identity, checksum, case definitions, corrected
  metadata, reported class summaries, and scientific claim boundary.

The CSV is not a raw instrument export and does not replace the public NIST data
record. The official raw images and other AM-Bench artifacts are not copied into
this repository.

Run the complete case study from the repository root:

```powershell
python scripts/run_nist_ambench_single_track_case_study.py `
  --output outputs/nist_ambench_2018_single_track
```

See `docs/NIST_AMBENCH_2018_SINGLE_TRACK_CASE_STUDY.md` for provenance,
validation, outputs, and scientific limitations.
