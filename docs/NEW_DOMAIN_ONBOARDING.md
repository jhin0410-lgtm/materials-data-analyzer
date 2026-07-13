# New Domain Onboarding

Status: `scaffold_stage` for v2.0.4.

New domains can be described with a metadata-only onboarding contract before
any connector, loader, model, or executable adapter exists. This keeps the
platform honest about what a dataset must define before analysis begins.

## Minimum Contract

`data/platform/case_study_onboarding_schema_v2.json` describes the onboarding
contract. A new domain should define:

- identity and domain
- primary unit of analysis
- input data type
- time key or an unavailable reason
- group keys or an unavailable reason
- target or event definition
- leakage policy
- validation policy
- trust policy
- artifact definitions
- local-only patterns
- credential policy
- resource budget
- allowed and prohibited claims
- stop conditions
- documentation and tests

All paths must be repository-relative. Raw and local-only artifacts cannot be
declared as tracked compact outputs.

## Validation Policy Selection

The onboarding validator checks policy compatibility:

- time-aware policies require a `time_key`
- group-aware policies require `group_keys`
- combined asset/time policies require both
- `random_reference_only` is not primary evidence

Missing keys can be explained when the scientific scope supports it, but the
validator will reject a policy that requires unavailable structure.

## Trust Policy Requirements

A trust policy is required before a case study can become an execution
candidate. The policy must define allowed statuses, representative-model rules,
calibration boundary, explainability boundary, production-claim policy,
allowed claims, prohibited claims, and stop conditions.

`production_ready` is not an onboarding status.

## Example

`configs/examples/environmental_monitoring_onboarding.json` is a synthetic
metadata-only example. It describes a future environmental sensor-monitoring
case study with:

- `sensor_id`
- `location_id`
- `observation_timestamp`
- future threshold-exceedance target
- location/time holdout design
- sensor drift and future-window leakage boundaries

It is not registered as an official plugin and is not executable.

## CLI

```powershell
python -m src.cli validate-onboarding configs/examples/environmental_monitoring_onboarding.json
python -m src.cli inspect-onboarding configs/examples/environmental_monitoring_onboarding.json
python -m src.cli onboarding-plan configs/examples/environmental_monitoring_onboarding.json
```

Add `--json` before the command for machine-readable output.

## Execution Boundary

Passing onboarding validation does not:

- download data
- read raw data
- run a model
- execute an adapter
- register a plugin
- prove scientific validity
- grant production claims

Execution requires a separate explicit adapter mapping and an execution
allowlist review.

## Common Failure Modes

- a time-aware policy without a time key
- a group-aware policy without group keys
- raw data declared as tracked
- local-only output declared as generated compact
- absolute paths or `..` traversal
- missing trust policy
- empty prohibited-claim list
- treating metadata onboarding as completed analysis
