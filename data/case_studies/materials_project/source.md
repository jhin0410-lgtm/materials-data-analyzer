# Materials Project Source Template

## Source

- Source: Materials Project API
- API key: read only from `MP_API_KEY`
- Query: element probe, default `Fe` and `Si`
- License or terms:
- Access date:

## Limitations

Materials Project values are computed materials properties from a database/API.
They are not direct experimental measurements and should not be presented as lab
or manufacturing results.

## Ingestion

```bash
python scripts/ingest_data.py --source materials_project --limit 50
```

## Analyzer Commands

```bash
python src/process_data.py --mode eda --input data/processed/materials_project_fe_si.csv --run-name mp_fe_si_eda
```

```bash
python src/process_data.py --mode process --input data/processed/materials_project_fe_si.csv --target band_gap_ev --goal maximize --run-name mp_fe_si_bandgap_process
```

```bash
python src/process_data.py --mode simulation --input data/processed/materials_project_fe_si.csv --target band_gap_ev --features formation_energy_ev_atom energy_above_hull_ev_atom density_g_cm3 volume_a3 --run-name mp_fe_si_bandgap_simulation
```
