# Representative Process–Characterization Workflow

## Purpose

This is the primary end-to-end user workflow for `materials-data-analyzer`.
It demonstrates how the platform handles a real process–characterization case
without bypassing provenance, sample identity, data-readiness, or scientific-claim
boundaries.

The workflow uses the tracked NIST AM-Bench 2018-02 IN625 AMMT case and reuses
three existing verified components:

1. integrated real-data case construction and integrity closeout;
2. process-design identifiability audit;
3. minimum staged next-experiment planning.

It does not add a new analyzer or silently proceed to regression because the
current experiment design is not ready for predictive, causal, or optimization
claims.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

The output directory must be absent or empty.

```powershell
python scripts/run_representative_process_characterization_workflow.py `
  --output outputs/representative_process_characterization
```

## Evidence chain

```text
tracked NIST process and optical-metrology tables
-> source/schema validation
-> explicit trace and sample identity validation
-> 40 provenance-bearing characterization feature records
-> one-to-one sample_id integration for 10 traces
-> source-summary and artifact-integrity verification
-> process-design identifiability audit
-> bounded minimum next-experiment plan
-> diagnostic scientific closeout
```

No network access is required. The tracked compact source tables remain the
source of truth for this reproducible workflow.

## Output structure

```text
outputs/representative_process_characterization/
├── 01_verified_case/
├── 02_process_design_audit/
├── 03_minimum_design_plan/
├── representative_workflow_summary.json
├── representative_workflow_report.md
└── representative_workflow_manifest.json
```

### `01_verified_case/`

Contains the integrated ten-trace case, normalized process conditions,
long-format characterization features, sample join audit, descriptive figures,
source-summary reproduction, scientific closeout, and integrity manifests.

Key artifacts:

- `integrated_sample_table.csv`;
- `sample_join_audit.csv`;
- `ambench_characterization_features_long.csv`;
- `ambench_case_summary.csv`;
- `ambench_integrated_report.md`;
- `ambench_integrated_workflow_manifest.json`.

### `02_process_design_audit/`

Records what the observed three process conditions can and cannot support.

Expected decision:

```text
not_ready_for_predictive_or_causal_modeling
```

The audit records:

- ten trace observations;
- three unique process conditions;
- A/B/C replication of 3/3/4 traces;
- two power levels and three speed levels;
- 3 of 6 possible observed-level combinations;
- no matched-speed power contrast;
- saturated main-effects design;
- rank-deficient interaction and quadratic candidates.

The audit does not fit a response model.

### `03_minimum_design_plan/`

Translates the design gaps into a bounded staged recommendation.

Immediate Stage 1:

| Target actual power | Scan speed | Minimum traces |
|---:|---:|---:|
| 137.9 W | 800 mm/s | 3 |
| 137.9 W | 1,200 mm/s | 3 |
| 179.2 W | 400 mm/s | 3 |

Stage 1 adds three conditions and nine independently traceable traces. It
completes the observed 2 × 3 grid and makes the power–speed interaction
structurally estimable with condition-level residual degrees of freedom.

Stage 2 is conditional. The mathematical midpoint candidate of `158.55 W` is
not a machine-approved operating condition. It must not be executed until safe
operation and achieved calibrated power are independently confirmed.

## How to interpret the result

### Supported

- software execution and artifact generation;
- source and schema validation;
- explicit process–characterization integration by `sample_id`;
- provenance and checksum verification;
- descriptive comparison of the three observed conditions;
- process-design gap identification;
- bounded next-experiment planning.

### Not supported

- predictive modeling from the current three conditions;
- causal separation of laser power and scan speed;
- process optimization;
- inference of unmeasured responses;
- machine control or process safety approval;
- transfer to other materials, systems, geometries, or metrology pipelines;
- engineering release decisions.

## Scientific closeout

**Evidence level: Diagnostic.**

The strongest evidence is the complete provenance-bearing path from ten
explicitly identified NIST traces through integration, source-summary
reproduction, artifact verification, and design-readiness assessment.

The primary limitation is experimental design, not software execution. Three
coupled process conditions cannot support predictive, causal, or optimization
claims. Additional data are useful only when they address the identified design
gaps and preserve sample, process, block, calibration, and measurement lineage.

## Relationship to the two repositories

This workflow runs in `materials-data-analyzer`. Instrument-specific feature
extraction remains the responsibility of
`materials-characterization-analyzer`. The repositories stay independently
installable and exchange explicit versioned files rather than importing each
other's internal modules.
