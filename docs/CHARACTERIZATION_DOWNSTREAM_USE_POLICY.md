# Characterization Downstream-Use Eligibility

## Purpose

`materials-data-analyzer` consumes versioned feature bundles produced by `materials-characterization-analyzer`. File integrity and a successful join are necessary, but they do not make every downstream analysis scientifically admissible.

The public consumption workflow therefore evaluates the intended use before creating consumer outputs.

## Public entry points

Installed CLI:

```bash
mda-characterization-import \
  --bundle-manifest path/to/characterization_handoff_bundle.json \
  --output path/to/consumer-output \
  --requested-use descriptive
```

Python API:

```python
from materials_data_analyzer.characterization_use_policy import (
    consume_characterization_bundle_for_use,
)

outputs = consume_characterization_bundle_for_use(
    "path/to/characterization_handoff_bundle.json",
    "path/to/consumer-output",
    requested_use="descriptive",
)
```

The low-level loader validates bundle files and integration mechanics. User-facing workflows must use the gated API or installed CLI so that intended use is evaluated and recorded.

## Ordered use levels

```text
display < descriptive < association < predictive < causal < engineering
```

A request is blocked when it exceeds the producer-declared `maximum_allowed_use` or fails a stricter prerequisite.

## Independence and leakage controls

Association or stronger use requires an explicit independent grouping field:

```bash
mda-characterization-import \
  --bundle-manifest path/to/bundle.json \
  --output path/to/association-output \
  --requested-use association \
  --split-group-field parent_specimen_id
```

The supplied field must:

- match `downstream_use_policy.independence_group_field` exactly;
- exist in the producer `sample_context` contract;
- represent the scientifically independent unit used for grouping or splitting.

This check prevents accidental row-level pseudo-replication. It does not prove that the producer selected the correct physical independence unit.

Predictive or stronger use additionally requires `measurement_timing: pre_outcome`. Concurrent, post-outcome, or unknown timing is rejected to prevent direct outcome leakage.

Causal and engineering uses require explicit producer declarations that the causal design and operational validation have been established. Those declarations are still subject to independent scientific review.

## Legacy bundles

A bundle without `downstream_use_policy` is treated as a legacy bundle. It remains consumable for compatibility, but its maximum use is fixed to `descriptive` and the consumer records a warning.

Legacy bundles cannot be promoted to association, predictive, causal, or engineering use merely by supplying a split field.

## Audit outputs

A successful gated run writes `characterization_use_eligibility.json` and embeds the same decision in:

- `cross_repository_handoff_summary.json`;
- `cross_repository_handoff_report.md`;
- `cross_repository_handoff_manifest.json`.

The consumer manifest refreshes output SHA-256 records after the eligibility decision is attached.

Blocked workflows stop before the consumer output directory is created.

## Scientific boundary

Passing the gate establishes only that the requested workflow is consistent with the machine-readable policy and the minimum anti-leakage prerequisites.

It does not establish:

- identical physical specimens or aliquots;
- cross-instrument comparability;
- correct causal structure;
- predictive performance or external validity;
- applicability outside the recorded domain;
- engineering-release readiness.

Software validation and scientific validation remain separate.
