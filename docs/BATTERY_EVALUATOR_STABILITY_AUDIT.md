# Battery Evaluator Stability Audit

Status: `descriptive_evaluator_stable_with_policy_restrictions`

v2.3.5 reruns the existing v2.3.4 descriptive evaluator with nine
predeclared, one-factor configurations. It does not tune thresholds against
findings or select a reference after inspecting outcomes.

## Policies

The exact v2.3.4 configuration is the baseline. Sensitivity variants cover:

- relaxed and strict algorithmic thresholds;
- first-valid and first-five-median analysis-ready references;
- three- and seven-observation windows;
- cycle-gap allowances of two and three.

All nine policies requested 34 trajectories, evaluated the same 33, and
blocked the same one four-observation trajectory. The baseline produced 383
raw findings. Total findings ranged from 272 under strict thresholds to 508
with a three-observation window. This spread is policy sensitivity, not
evidence for a physical transition.

## Bounded Events

Overlapping or adjacent windows from the same trajectory and finding category
are consolidated before stability classification. The result is 489 bounded
descriptive events:

| Stability status | Events | Interpretation |
|---|---:|---|
| `stable_across_policies` | 211 | present under every eligible predeclared policy |
| `stable_with_restrictions` | 97 | baseline-supported with at least half of eligible policies |
| `policy_sensitive` | 50 | supported by multiple policies but below the restricted-stability boundary |
| `insufficient_support` | 131 | supported by only one policy or lacking sufficient eligible-policy support |

The protocol-context-change count is zero because the recovered source
evidence is cell-group-level and static within each mapped trajectory. It does
not prove that commanded protocol conditions were constant cycle by cycle.

## Time And Reference Boundaries

All 2,495 cycle timestamps are parseable and chronologically monotonic within
the 34 cells. The evaluator records that physical time is available, but its
findings remain defined on cycle index; it does not estimate a physical-time
degradation rate. Alternative reference policies operate on an audit copy and
never overwrite the source-recorded v2.3.4 reference.

## Reproduction

The preview is side-effect free. Actual execution requires the local Kaggle
package and local PGIR artifacts and must be explicit:

```powershell
python -m src.cli preview-battery-source-metadata-audit configs/examples/battery_source_metadata_stability_audit.json
python -m src.cli run-battery-metadata-stability-audit configs/examples/battery_source_metadata_stability_audit.json --execute
python -m src.cli validate-battery-metadata-stability
python -m src.cli show-battery-metadata-stability
python -m src.cli evaluate-battery-external-data-requirement
```

Cell/cycle lineage, per-policy findings, and consolidated event rows remain
under ignored `outputs/battery_metadata_stability_v2_3/`. Only aggregate,
identity-free summaries are tracked.
