# NASA Protocol Stratification Action

`protocol_stratification` is a typed, checksum-bound research-loop action for one
predeclared question: whether battery-level Ridge-versus-persistence error differs
across exact ambient-temperature groups recorded by the official NASA import.

The action is a post-hoc diagnostic. It does not refit either model, change the
target, remove a battery, replace pooled validation, infer protocol identity, or
upgrade the existing scientific evidence level.

## Scientific contract

The primary protocol field is
`ambient_temperature_median_c` from
`nasa_pcoe_protocol_summary.csv`. Values are used exactly as imported:

- no rounding or tolerance matching;
- no temperature bins;
- no grouping from battery names, filenames, or row order;
- no removal of sparse groups;
- no substitution of a favorable subgroup metric for pooled validation.

The primary response is battery-level
`ridge_mae - persistence_mae` over every exact-horizon prediction row for that
battery. The battery, rather than the prediction row, is the statistical unit.

A Kruskal-Wallis test is executed only when:

- every evaluated battery has explicit finite temperature metadata;
- at least two exact temperature groups are present;
- every observed group contains at least five evaluated batteries.

`protocol_effect_supported` requires both:

- Kruskal-Wallis `p <= 0.05` for the single predeclared test;
- epsilon-squared `>= 0.10`.

Even when both thresholds are met, the evidence status remains `Diagnostic`.
Temperature is observational and may be confounded with source batch, cycling
schedule, instrument conditions, or other protocol variables.

## Outcomes

| Outcome | Meaning |
|---|---|
| `protocol_effect_supported` | The predeclared battery-level diagnostic met both thresholds. This is not causal or transferable evidence. |
| `protocol_effect_not_supported` | Groups were adequately supported, but the predeclared diagnostic did not meet both thresholds. |
| `protocol_metadata_insufficient` | Evaluated batteries lack finite explicit temperature metadata or fewer than two exact groups exist. |
| `protocol_groups_too_small` | At least one observed exact group has fewer than five evaluated batteries; no favorable subset test is run. |

The last two outcomes cause the deterministic policy to prioritize an explicit
external-data requirement rather than continue condition-stratified analysis.

## Prerequisites

The request must reference:

- an active research run containing a verified completed
  `audit_existing_battery_run` action;
- a verified stable `target_reference_sensitivity` action when the audit reported
  target/reference flags;
- the official NASA import directory containing
  `nasa_pcoe_protocol_summary.csv`;
- the Battery analysis directory containing
  `tables/validation_predictions.csv`, `reports/scientific_closeout.json`, and
  `run_manifest.json`;
- `configs/research/nasa_protocol_stratification_action_registry.v1.json` and the
  exact registry SHA-256 returned by `plan-nasa-next-action` or
  `validate-actions`.

## Request

Create a JSON request with exactly these keys:

```json
{
  "schema_version": "1.0",
  "action_id": "A3",
  "action_type": "protocol_stratification",
  "research_run": "outputs/nasa_research_loop",
  "import_run": "outputs/nasa_pcoe_import",
  "analysis_run": "outputs/nasa_battery_analysis",
  "registry": "configs/research/nasa_protocol_stratification_action_registry.v1.json",
  "repository_root": ".",
  "expected_registry_sha256": "<64-character SHA-256 from the verified planner output>"
}
```

Relative paths are resolved from the request file directory. `action_id` must be
new in the research ledger.

## Execute and verify

The legacy action-specific command is an authorization-enforcing compatibility
entry point. The CLI `--registry` is the planning registry used to revalidate the
selected action; the request remains bound to the protocol execution registry
shown above.

```powershell
mda-research-loop execute-nasa-protocol-stratification `
  --repository-root . `
  --run outputs/nasa_research_loop `
  --registry configs/research/nasa_research_action_registry.v1.json `
  --request .\protocol_action_request.json
```

The command rejects a request whose `action_type` is not
`protocol_stratification` and routes execution through the same
`execute-authorized-action` boundary used by the generic CLI.

```powershell
mda-research-loop verify-nasa-protocol-stratification `
  --report .\outputs\nasa_research_loop\actions\A3\action_result.json
```

The action writes only beneath the research action directory:

- `protocol_stratification/battery_protocol_errors.csv`;
- `protocol_stratification/protocol_group_metrics.csv`;
- `protocol_stratification/protocol_stratification.json`;
- `action_result.json`.

The verifier independently reloads the immutable import and analysis inputs,
recomputes the result, reproduces every output byte, verifies prerequisite action
reports, and checks the research-ledger checksum binding.

## Scientific closeout

This action cannot change the closed NASA Ridge result by itself. The current
predictive evidence remains `Unsupported` unless a separate validated analysis
with suitable external or transport evidence changes the scientific closeout.
