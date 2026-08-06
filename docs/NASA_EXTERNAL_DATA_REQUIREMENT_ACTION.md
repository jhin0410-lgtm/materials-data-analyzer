# NASA External Data Requirement Action

`external_data_requirement_generation` converts a verified unresolved NASA
battery-analysis blocker into a checksum-bound minimum data contract. It does
not download data, train a model, relabel an existing cohort as external, or
upgrade the current scientific evidence.

## Current scientific use

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

When target-reference analysis returns
`required_reference_metadata_missing`, the action instead specifies the
minimum explicit `reference_capacity_ah` metadata and provenance contract.

## Scientific boundaries

The generated cohort must be independent external evidence or a cohort whose
calibration role was declared before evaluation. Existing NASA evaluation
batteries may not be relabelled as external. Required metadata include explicit
units, source identity, acquisition provenance, sample identity, compatible
exact-horizon and target/reference semantics, and battery-disjoint evaluation.
Temperature values remain exact source-recorded values: rounding, binning,
filename inference, and battery-name inference are prohibited.

The action preserves the current `Unsupported` predictive evidence level. A
future cohort satisfying the contract would only make the specified diagnostic
eligible; it would not by itself establish statistical power, causality,
transportability, or predictive validity.

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
