# Typed NASA Existing-Run Audit Action

This action is the first end-to-end deterministic action in the autonomous
research loop. It binds the already implemented Battery result audit to a strict
request, verifies the outputs independently, and records a completed or failed
action in the immutable research ledger.

It does not select itself. There is still no planner or language-model action
selection in the stable path.

## Scope

The action type is fixed to:

```text
audit_existing_battery_run
```

The executor directly calls the existing Python audit functions behind
`mda-battery-result-audit`. It does not accept a shell command, arbitrary Python,
or a user-provided module path.

The audit performs:

1. target/reference and cross-battery comparability diagnostics;
2. battery influence and observed-condition triage;
3. manifest and closeout synchronization;
4. independent verification of required outputs and checksums;
5. immutable research-ledger recording.

The existing prediction model is not refit and no validation prediction is
recomputed.

## Preconditions

A research run must already exist and remain active:

```powershell
mda-research-loop init `
  --objective configs/research/nasa_exact_horizon_research_objective.example.json `
  --output outputs/nasa_research_loop
```

The Battery Intelligence analysis run must contain:

```text
config_snapshot.json
run_manifest.json
tables/validated_cycle_summary.csv
tables/forecast_feature_table.csv
tables/validation_predictions.csv
reports/scientific_closeout.json
```

The research run and analysis run must be separate, non-overlapping directories.

## Obtain the registry SHA

Validate the action registry first:

```powershell
mda-research-loop validate-actions `
  --registry configs/research/nasa_research_action_registry.v1.json `
  --repository-root .
```

Copy the reported `registry_sha256` into the request. This prevents a request
from silently executing against a changed action contract.

## Request contract

Create a local JSON request such as:

```json
{
  "schema_version": "1.0",
  "action_id": "NASA-AUDIT-001",
  "action_type": "audit_existing_battery_run",
  "research_run": "outputs/nasa_research_loop",
  "analysis_run": "outputs/nasa_pcoe_signal_enriched_battery_intelligence",
  "registry": "configs/research/nasa_research_action_registry.v1.json",
  "repository_root": ".",
  "expected_registry_sha256": "COPY_THE_64_CHARACTER_SHA256_FROM_VALIDATE_ACTIONS"
}
```

Relative paths are resolved from the request file's directory, not from an
implicit project root. The request rejects duplicate JSON keys, unknown fields,
unsupported schema versions, unsafe action identifiers, a wrong action type, or
an invalid registry hash.

Keep the request local unless it contains only portable, non-sensitive paths.

## Execute

The legacy action-specific command is an authorization-enforcing compatibility
entry point. It revalidates the current planning state, budget, execution
registry, and request binding before invoking the typed executor; it does not
bypass `execute-authorized-action`.

```powershell
mda-research-loop execute-nasa-audit `
  --repository-root . `
  --run outputs/nasa_research_loop `
  --registry configs/research/nasa_research_action_registry.v1.json `
  --request .\nasa_audit_action_request.json
```

The example keeps the request at the repository root so its relative paths above
resolve as shown. If the request is stored in another directory, adjust its
relative path fields accordingly.

A verified success returns exit code `0`. A preflight contract failure returns
exit code `1` and consumes no action budget. An execution or verification failure
that started the registered action returns exit code `2`, rolls back the analysis
run, and records a failed action with its fixed registry cost.

## Transaction and rollback behavior

Before execution the adapter snapshots, byte for byte:

### Immutable analysis inputs

```text
tables/validated_cycle_summary.csv
tables/forecast_feature_table.csv
tables/validation_predictions.csv
config_snapshot.json
```

### Files the existing audit is permitted to create or update

```text
tables/target_integrity_by_battery.csv
tables/error_concentration_by_battery.csv
tables/battery_influence_by_model.csv
tables/battery_diagnostic_priority.csv
tables/battery_condition_error_profile.csv
reports/target_comparability_audit.json
reports/target_comparability_audit.md
reports/battery_influence_triage.json
reports/battery_influence_triage.md
reports/scientific_closeout.json
reports/scientific_closeout.md
run_manifest.json
```

If either audit or the independent verifier fails, all listed files are restored
to their exact prior bytes or removed when they did not previously exist. A failed
action report records the error and whether rollback verification succeeded.

Concurrent writers to the same research or analysis run are not supported in this
first executor.

## Independent verification

A completed action is accepted only when:

- immutable input files are unchanged;
- the pre-existing scientific evidence level is unchanged;
- every required registry output exists;
- required JSON outputs contain objects;
- required CSV outputs contain rows and columns;
- every required output appears in `run_manifest.json`;
- every required manifest checksum matches the current file;
- derived action outcomes are allowed by the exact registry version.

The current outcomes can include:

- `target_or_reference_flags_detected`;
- `pooled_error_instability_detected`;
- `no_audit_flag_with_complete_dimensions`;
- `partial_dimensions_inconclusive`.

Negative and inconclusive outcomes are valid action results.

## Action report and ledger

The report is written under:

```text
<research_run>/actions/<action_id>/action_result.json
```

A completed ledger event checksum-binds the report and all required audit outputs.
A failed ledger event checksum-binds the failure report. Both consume the fixed
cost declared by the versioned registry because execution was attempted.

Re-verify later with:

```powershell
mda-research-loop verify-nasa-audit `
  --report outputs/nasa_research_loop/actions/NASA-AUDIT-001/action_result.json
```

This rechecks the request, immutable inputs, recorded outputs, action-report hash,
and matching ledger status.

## Scientific boundary

This action identifies target/reference anomalies, error concentration, battery
influence, and source/protocol review priorities. It does not:

- remove a battery or row;
- repair, clip, smooth, interpolate, or renormalize a target;
- infer protocol identity;
- replace grouped validation metrics with omission scores;
- refit Ridge or another model;
- establish an external-validation result;
- establish degradation mechanism, causality, engineering readiness, or
  production suitability.

The completed NASA Ridge predictive conclusion remains `Unsupported` unless a
future separately validated research action generates evidence that legitimately
changes the declared hypothesis and claim scope.

## Next boundary

After this action is stable, the next engineering step is a deterministic
selection policy over registered actions. It must initially choose only among
available actions, explain which unresolved blocker it targets, and never execute
planned actions. An LLM planner is not eligible until deterministic candidate
ranking and verifier rejection paths are covered by retrospective benchmarks.
