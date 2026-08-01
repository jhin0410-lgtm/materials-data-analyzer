# NASA PCoE nonpositive discharge-capacity policy

## Trigger

The official NASA PCoE battery archive contains discharge operations whose scalar MATLAB `Capacity` value can be zero or negative. Such a value is not accepted as a physical degradation target.

## Import behavior

For a finite `Capacity <= 0 Ah`, the importer:

1. retains the MAT file and discharge operation in the source inventory;
2. records the original `battery_id`, source operation index, one-based discharge ordinal, observed value, and exclusion reason in `nasa_pcoe_import_warnings.csv`;
3. excludes that operation from both `nasa_pcoe_cycle_summary.csv` and `nasa_pcoe_raw_signal.csv`;
4. preserves later source discharge ordinals, so the canonical `cycle_index` may contain an explicit gap;
5. reports imported, excluded, and nonpositive-capacity operation counts in the inventory and import manifest.

The importer does **not** replace the value, clip it to a positive number, interpolate a target, smooth the trajectory, or renumber later cycles.

## Fatal versus recoverable conditions

A finite nonpositive scalar capacity is a recoverable, auditable source-quality condition. Structural ambiguity remains fatal, including mismatched vector lengths, nonfinite signal vectors, ambiguous battery identity, unsafe archives, or conflicting same-ID MAT checksums.

## Scientific interpretation

An excluded operation is not evidence that the physical cell had exactly zero capacity. It indicates that the source operation does not provide a valid positive scalar capacity target under the canonical degradation contract. Any resulting cycle gap must remain visible in quality review and downstream trajectory diagnostics.
