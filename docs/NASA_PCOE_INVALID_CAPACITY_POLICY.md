# NASA PCoE invalid discharge-capacity policy

## Trigger

The official NASA PCoE battery archive contains discharge operations whose MATLAB `Capacity` field may be unusable as a physical degradation target. Observed cases include finite nonpositive values and non-finite or otherwise malformed scalar fields.

The importer classifies these target defects as:

- `missing`: the field is absent;
- `nonnumeric`: the value cannot be converted to a numeric value;
- `nonscalar`: more or fewer than one numeric value is present;
- `nonfinite`: the scalar is `NaN`, positive infinity, or negative infinity;
- `nonpositive`: the finite scalar is zero or negative.

## Import behavior

For any invalid `Capacity` target, the importer:

1. validates the associated voltage, current, time, and optional temperature vectors first;
2. retains the MAT file and discharge operation in the source inventory;
3. records the original `battery_id`, source operation index, one-based discharge ordinal, issue class, observed representation, and exclusion reason;
4. writes the operation to `nasa_pcoe_excluded_operations.csv` and `nasa_pcoe_import_warnings.csv`;
5. excludes that operation from both `nasa_pcoe_cycle_summary.csv` and `nasa_pcoe_raw_signal.csv`;
6. preserves later source discharge ordinals, so canonical `cycle_index` may contain explicit gaps;
7. reports imported, excluded, and per-reason invalid-capacity counts in the inventory, provenance, and import manifest.

The importer does **not** replace the value, clip it to a positive number, interpolate or infer a target, smooth the trajectory, or renumber later cycles.

## Fatal versus recoverable conditions

An unusable capacity target is a recoverable, auditable source-quality condition because the canonical prediction target cannot be trusted but the source operation identity remains known.

Structural ambiguity remains fatal, including:

- mismatched voltage/current/time vector lengths;
- non-finite measured signal vectors;
- non-monotonic or negative elapsed time;
- nonpositive measured voltage;
- mismatched temperature-vector length;
- ambiguous battery identity;
- unsafe archive paths or excessive archive expansion;
- conflicting same-ID MAT checksums.

This distinction prevents invalid targets from aborting a complete official archive import without hiding corrupted trajectories.

## Scientific interpretation

An excluded operation is not evidence that the physical cell had exactly zero capacity, infinite capacity, or no discharge. It means the source operation does not provide a valid positive finite scalar capacity target under the canonical degradation contract.

Any resulting cycle gap remains visible in quality review and downstream trajectory diagnostics. Predictive conclusions must report the exclusion count and reason distribution, especially when exclusions are concentrated in particular batteries, protocols, or lifecycle regions.
