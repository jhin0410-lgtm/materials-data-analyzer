# Battery Archive Source Notes

## Source Scope

This case study uses Battery Archive raw data stored locally as 9 zip files
under `data/raw/battery_archive/`.

Raw zip files are not included in the repository. Users must confirm the
Battery Archive access terms, license, and citation requirements before
publishing or redistributing derived work.

## Raw Inventory

The raw inventory audit found:

- 9 local Battery Archive zip files
- 196 `*_cycle_data.csv` files
- 196 timeseries CSV files
- no separate metadata CSV/JSON/Excel/MAT file

The current case study uses only the `*_cycle_data.csv` files. Timeseries CSV
processing is out of scope for v1.1.5.

## Metadata

Source, chemistry, form factor, temperature, SOC window, charge C-rate, and
discharge C-rate are parsed from filenames. Filename-derived metadata is useful
for grouping and screening, but it should be treated as parsed metadata rather
than a manually curated ground-truth schema.

## Raw Data Policy

- Do not commit raw Battery Archive zip files.
- Do not commit extracted raw CSV files.
- Do not list every raw filename in case-study documentation.
- Keep large generated cycle-level tables local unless a tracking decision is
  made explicitly.
- Compact inventory, series summary, group summary, and quality summary files
  may be treated as reproducibility artifacts when documented.
