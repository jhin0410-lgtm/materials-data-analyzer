# Battery Source-Metadata Recovery

Status: `v2.3.5_completed_with_explicit_source_limits`

The v2.3.5 audit establishes exact lineage from all 34 PGIR battery
trajectories to the local package identified by the Kaggle slug
`patrickfleith/nasa-battery-dataset`. The local archive is 239,496,734 bytes
with SHA256
`787ba917fc381c0bd354f515966b1831191ceb5b26985ee8b0000bb6bf96efee`.
Its `metadata.csv` has SHA256
`182fcf36be0899db30ec0f7b04ed32e11fdf1cbd308241b22ea2a2722f5bc4f8`.
The archive member `cleaned_dataset/metadata.csv` has the same checksum as the
local extracted file.

This is exact immediate-upstream lineage, not proof of the official NASA
source snapshot. The local package does not identify an authoritative NASA
snapshot/version, retrieval timestamp, or source measurement-calibration
record, so those fields remain unavailable.

## Cell Lineage

The nine local protocol documents map without gaps or duplicates to all 34
cells:

| Protocol document group | Cells |
|---|---|
| `README_05_06_07_18` | B0005, B0006, B0007, B0018 |
| `README_25_26_27_28` | B0025, B0026, B0027, B0028 |
| `README_29_30_31_32` | B0029, B0030, B0031, B0032 |
| `README_33_34_36` | B0033, B0034, B0036 |
| `README_38_39_40` | B0038, B0039, B0040 |
| `README_41_42_43_44` | B0041, B0042, B0043, B0044 |
| `README_45_46_47_48` | B0045, B0046, B0047, B0048 |
| `README_49_50_51_52` | B0049, B0050, B0051, B0052 |
| `README_53_54_55_56` | B0053, B0054, B0055, B0056 |

The source metadata contains 7,565 rows and 2,794 discharge rows. All 2,794
full-summary composite keys match the source discharge metadata. The 2,495
analysis-ready rows all match source metadata by the exact composite key
`battery_id`, `filename`, `uid`, and `test_id`; all referenced raw discharge
files exist and share the expected six-column header.

## Recovered Evidence

Source-supported metadata recovered for all 2,495 analysis-ready rows:

- cycle start timestamp, with timezone unavailable;
- ambient temperature;
- discharge duration;
- measured temperature, current, and voltage summaries;
- elapsed time from the first observed discharge and the preceding discharge;
- cell-group protocol-document reference.

The source also has 1,956 impedance rows across all 34 cells. `Re` and `Rct`
are both numeric in 1,947 rows; nine rows lack a complete pair. These records
were audited but were not aligned to discharge cycles or promoted into the
capacity evaluator.

## Limits

Protocol documents support group-level operating context, but variable-
condition groups do not provide a cycle-specific command log. Measured current
is not substituted for a commanded protocol. Source uncertainty is recorded as
`unavailable`, never zero, and no missing field is default-filled or inferred.

External documentation is needed only for the genuinely missing official NASA
snapshot/version, cycle-specific commanded conditions where absent, and
measurement/calibration uncertainty. NASA PCoE is the preferred official
route; NIST OAR is discovery/catalog support. CALCE would be a separate
dataset requiring a comparability audit. NREL energy-system data and NVD
security data are not substitutes for battery protocol or uncertainty
evidence. No network download was performed.
