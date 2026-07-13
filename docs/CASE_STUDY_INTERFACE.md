# Case Study Interface

Status: `scaffold_stage` for v2.0.4.

The case-study interface is a metadata layer that describes each existing
case study using the same lifecycle vocabulary. It does not move scripts,
rewrite outputs, or make old workflows executable through the unified CLI.

## Purpose

The interface makes the repeated v1.x pattern inspectable:

```text
contract
-> acquisition
-> normalization
-> readiness
-> feature_build
-> validation
-> trust
-> closeout
-> report
```

A case study does not need every stage. Missing stages are recorded explicitly
instead of hidden behind a generic success status.

## Metadata Contract

`src/platform_core/case_studies.py` defines:

- `CaseStudyMetadata`
- `CaseStudyStageMetadata`
- `CaseStudyContract`

Each case-study record includes identity, domain, primary unit, time key,
group keys, target type, supported stages, available stages, executable
stages, local-only policy, documentation path, release tag, and limitations.

Stage metadata records adapter ID, required artifacts, produced artifacts,
execution status, side-effect class, and whether network, raw data, or model
training would be required.

## Registry Role

`src/platform_core/case_study_registry.py` explicitly registers:

| Case study | Interface status | Execution boundary |
| --- | --- | --- |
| `battery_archive` | `partially_onboarded` | script-only; no trust adapter mapped |
| `materials_project` | `interface_mapped` | trust adapter mapped; execution blocked |
| `smart_factory` | `interface_mapped` | trust adapter mapped; execution blocked |
| `reliability` | `partially_onboarded` | trust verify adapter allowlisted |

No case study is marked `fully_onboarded` in v2.0.4.

## Plugin, Adapter, And Case-Study Boundaries

The registries have separate jobs:

- Plugin registry: execution-facing metadata and supported stages.
- Adapter registry: explicit adapter IDs and script metadata.
- Case-study registry: domain, lifecycle, artifacts, docs, limitations, and
  completeness.
- Execution policy registry: the only place that can allow controlled runtime
  execution.

User config cannot provide module paths, callables, or execution permission.

## Artifact And Policy Links

Case-study metadata references artifact IDs from `src/platform_core/artifacts.py`
and policy IDs from the validation and trust registries. The case-study
registry validates those links at construction time.

Registered artifacts remain metadata. Files are not moved, generated, or
overwritten by the interface.

## CLI

```powershell
python -m src.cli list-case-studies
python -m src.cli inspect-case-study reliability
python -m src.cli list-case-study-stages reliability
```

Add `--json` before the command for deterministic JSON output.

## Limitations

- This is not a generic automatic CSV analyzer.
- Passing interface checks does not prove scientific validity.
- Adapter mapping does not imply execution permission.
- Reliability trust verification remains the only controlled executable case.
- Acquisition, model training, raw data reads, and canonical output overwrite
  remain disabled in the platform layer.
