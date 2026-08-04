# NASA PCoE Audit Closeout

This workflow closes an already-computed NASA PCoE analysis using one
provenance-bound command. It refreshes the existing-artifact audit and review
evidence, validates a completed reviewer disposition against the exact refreshed
evidence SHA-256, finalizes the disposition, and packages the closed audit bundle.

It does **not** import the NASA archive, extract signal features, refit a model,
repair a target, remove a battery, or create an external-validation claim.

## Prerequisites

The local checkout must contain:

- the reviewed Python environment;
- `data/processed/nasa_pcoe_battery_import/`;
- `outputs/nasa_pcoe_signal_enriched_battery_intelligence/`;
- `data/raw/battery/nasa_pcoe/5_Battery_Data_Set.zip`;
- `data/raw/battery/nasa_pcoe/retrieval_receipt.json`;
- a completed 34-battery disposition CSV created for the current evidence.

The import, raw source, detailed analysis, and final audit ZIP are intentionally
Git-ignored local evidence. See [Local Workspace Hygiene](WORKSPACE_HYGIENE.md)
before deleting or moving them.

## One-command Closeout

```powershell
cd "C:\path\to\materials_data_analyzer"

.\scripts\close_nasa_pcoe_audit.ps1 `
  -PythonExecutable ".\.venv313\Scripts\python.exe" `
  -DispositionInput ".\outputs\nasa_protocol_review_disposition_completed.csv"
```

Default inputs:

```text
data/processed/nasa_pcoe_battery_import/
outputs/nasa_pcoe_signal_enriched_battery_intelligence/
data/raw/battery/nasa_pcoe/
```

Default final package:

```text
outputs/nasa_pcoe_full_audit_bundle_post_remediation_closed.zip
```

Custom paths remain available:

```powershell
.\scripts\close_nasa_pcoe_audit.ps1 `
  -PythonExecutable ".\.venv313\Scripts\python.exe" `
  -ImportOutput ".\data\processed\nasa_pcoe_battery_import" `
  -AnalysisOutput ".\outputs\nasa_pcoe_signal_enriched_battery_intelligence" `
  -RawDirectory ".\data\raw\battery\nasa_pcoe" `
  -DispositionInput ".\outputs\completed_disposition.csv" `
  -Destination ".\outputs\nasa_pcoe_full_audit_bundle_post_remediation_closed.zip"
```

## Ordered Safety Gates

The command performs these steps in order:

1. refresh the protocol audit and import-to-analysis binding;
2. regenerate the 34-battery review evidence from existing artifacts;
3. compute the refreshed evidence CSV SHA-256;
4. reject a disposition whose `source_evidence_sha256` does not exactly match;
5. run the official disposition finalizer;
6. require `34` reviewed batteries and `0` pending batteries;
7. package the analysis, available import, source archive, retrieval receipt,
   diagnostics, and completed disposition;
8. print the evidence, disposition, and final ZIP SHA-256 values.

The disposition is checked only after the evidence refresh. An old worksheet
cannot be silently reused against a different evidence packet.

## Successful Terminal Summary

A successful run prints fields including:

```text
reviewed_battery_count: 34
pending_battery_count: 0
predictive_evidence_level: Unsupported
review_evidence_sha256: ...
disposition_input_sha256: ...
closed_audit_bundle_sha256: ...
```

Preserve the final ZIP and printed SHA-256 outside the checkout as canonical
closeout evidence.

## Failure Handling

The workflow stops before final packaging when:

- required import, analysis, raw-source, or disposition paths are missing;
- protocol or import bindings are stale;
- evidence generation fails;
- the completed disposition is bound to a different evidence SHA-256;
- the disposition is incomplete or does not cover all 34 batteries;
- final packaging or hash generation fails.

It does not automatically rewrite reviewer conclusions or initialize a new
worksheet. A changed evidence hash requires a new independent review and a new
completed disposition.

## Scientific Boundary

The closeout establishes a reproducible internal audit package. It does not
establish external predictive validity, causal degradation mechanisms, protocol
transferability, engineering readiness, or production suitability.

The current fixed Ridge predictive result remains **Unsupported**. The package is
appropriate for software/provenance verification and exploratory diagnostic
review, not for deployment or engineering control decisions.
