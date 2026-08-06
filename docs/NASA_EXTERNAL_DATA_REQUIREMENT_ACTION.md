# NASA External Data Requirement Action

`external_data_requirement_generation` converts a verified unresolved NASA
battery-analysis blocker into a checksum-bound minimum evidence contract. It
does not download data, train a model, relabel an existing cohort as external,
or upgrade the current scientific evidence.

## Current scientific use

### Undersupported exact-temperature groups

When protocol stratification returns `protocol_groups_too_small`, the action
reads the verified exact-temperature group metrics and reports, for every
observed `ambient_temperature_median_c` group:

- the currently evaluated battery count;
- the predeclared minimum of five evaluated batteries;
- the minimum additional battery count needed to make the diagnostic eligible.

The five-battery threshold is an eligibility rule inherited from the
predeclared protocol action. It is not a power calculation and does not imply
that five batteries per group are sufficient for a transferable or causal
claim.

### Missing or non-identifying protocol metadata

`protocol_metadata_insufficient` is not treated as an ordinary sample-count
deficit.

When evaluated batteries are missing `ambient_temperature_median_c`, the action
returns `current_blocker_not_resolvable_by_more_data` and requires authoritative
battery-level metadata recovery. Additional rows do not repair missing metadata
on the already evaluated batteries. Filename inference, battery-ID inference,
rounding, binning, and unsupported imputation are prohibited. When authoritative
metadata cannot be recovered, the fallback is a genuinely independent external
or predeclared calibration cohort with complete source-recorded temperature
metadata.

When all evaluated batteries have metadata but fewer than two exact temperature
groups exist, the action requires at least one additional source-recorded exact
group. It does not guess a new temperature value.

### Missing target-reference metadata

When target-reference analysis returns
`required_reference_metadata_missing`, the primary evidence route is recovery
of authoritative battery-level `reference_capacity_ah` metadata from the source
record, declaration, or measurement documentation. Adding more rows does not
repair an undefined reference on the current batteries. Post-forecast target
values, filename inference, and silent target repair are prohibited.

Only when authoritative reference metadata cannot be recovered does the
contract fall back to a genuinely independent external or predeclared
calibration cohort with explicit source-bound reference-capacity semantics.

## Scientific boundaries

A generated cohort contract requires independent external evidence or a cohort
whose calibration role was declared before evaluation. Existing NASA evaluation
batteries may not be relabelled as external. Required metadata include explicit
units, source identity, acquisition provenance, sample identity, compatible
exact-horizon and target/reference semantics, and battery-disjoint evaluation.
Temperature values remain exact source-recorded values: rounding, binning,
filename inference, and battery-name inference are prohibited.

The action preserves the current `Unsupported` predictive evidence level.
Authoritative metadata recovery permits only the specified predeclared
diagnostic. A future cohort satisfying a fallback contract likewise makes only
that diagnostic eligible; neither route by itself establishes statistical
power, causality, transportability, external validation, or predictive
validity.

## Request

Create a JSON request with exactly these keys:

```json
{
  "schema_version": "1.0",
  "action_id": "NASA-EXTERNAL-001",
  "action_type": "external_data_requirement_generation",
  "research_run": "outputs/nasa_autonomous_loop",
  "registry": "configs/research/nasa_external_data_requirement_action_registry.v1.json",
  "repository_root": ".",
  "expected_registry_sha256": "<canonical SHA-256 from validate-actions>"
}
```

## Execute and verify

```powershell
.\.venv313\Scripts\python.exe `
  .\scripts\run_nasa_external_data_requirement_action.py `
  execute `
  --request .\external_data_requirement_request.json
```

```powershell
.\.venv313\Scripts\python.exe `
  .\scripts\run_nasa_external_data_requirement_action.py `
  verify `
  --report .\outputs\nasa_autonomous_loop\actions\NASA-EXTERNAL-001\action_result.json
```

The action writes:

- `reports/external_data_requirement.json`;
- `action_result.json`.

After recording the completed action, it stops the bounded research loop with
`external_evidence_required`. The verifier recomputes the contract from the
immutable prerequisite report, verifies file checksums and ledger binding, and
confirms the terminal reason.
