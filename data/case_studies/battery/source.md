# Battery Aging Dataset Source Template

> Status: template only. Fill this out after choosing the NASA Battery Aging
> Dataset source or a properly licensed Kaggle mirror.

## Source

- Dataset title:
- Source URL:
- Mirror URL, if any:
- Repository or publisher:
- Access date:
- License or terms:
- Redistribution allowed in this repository: yes/no/unclear

## Raw Data Policy

The full raw battery aging dataset should not be committed to this repository by
default. Keep raw files under `data/raw/battery/` locally and commit only small,
properly licensed processed summaries when redistribution is clearly allowed.

Do not commit Kaggle API keys, tokens, credentials, private experiment logs, or
large raw archives.

## Processed Summary Target Schema

- `battery_id`
- `cycle_index`
- `ambient_temperature_c`
- `discharge_capacity_ah`
- `capacity_retention_percent`
- `internal_resistance_ohm`
- `failed`

`failed` is not an original NASA/Kaggle label in this preprocessing template.
It is derived for analysis as `1` when `capacity_retention_percent < 80` and
`0` otherwise. Treat it as a screening label, not as a confirmed failure
diagnosis.

## Intended Analyzer Modes

- `eda`
- `reliability`
- `simulation`

## Preprocessing Command

```bash
python notebooks/battery_preprocessing.py --input data/raw/battery/<raw-file>.mat --output data/processed/battery_cycle_summary.csv
```

## Notes

- Describe raw file structure after inspection.
- Record any unit conversions.
- Record any removed fields or anonymization steps.
- State limitations before interpreting degradation or failure behavior.
