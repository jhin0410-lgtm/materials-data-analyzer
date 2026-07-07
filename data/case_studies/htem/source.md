# HTEM Source Template

## Source

- Source:
- Base URL:
- Query elements:
- License or terms:
- Access date:

## Scope

This first ingestion version keeps sample-level scalar fields only; spectra are
excluded in this first ingestion version.

## Ingestion

```bash
python scripts/ingest_data.py --source htem --elements Zn Sn --limit 50
```

## Analyzer Commands

```bash
python src/process_data.py --mode eda --input data/processed/htem_sample_properties.csv --run-name htem_eda
```
