# Characterization Evidence Ladder Bridge

`materials-characterization-analyzer` now emits a monotonic L0-L8 scientific-evidence
assessment. `materials-data-analyzer` consumes that assessment only after independent
reverification.

## Producer levels

```text
L0 software integration
L1 raw representation / byte identity
L2 acquisition / provenance integrity
L3 instrument / calibration validity
L4 method / algorithm validation
L5 target-material validation
L6 independent external validation
L7 replicated multi-source support
L8 engineering decision readiness
```

The consumer does not import the producer package. It independently checks the exact
assessment/declaration hashes, source-binding SHA-256 values, monotonic Supported prefix,
readiness booleans, level summary, and the handoff boundary that forbids scientific-status
promotion or downstream-use authorization.

## Research-agent mapping

Only the **first verified blocking level** becomes a new research evidence gap.

| First blocker | Safe next planning class |
|---|---|
| L0 | existing-data/software reanalysis |
| L1 | raw/lossless source acquisition |
| L2 | authoritative acquisition/provenance acquisition |
| L3 | instrument/calibration evidence acquisition |
| L4 | predeclared method/sensitivity validation |
| L5 | exact target-material evidence search |
| L6 | development- and provenance-disjoint external validation search |
| L7 | replication design/acquisition |
| L8 | operational physical-experiment design |

This mapping is fail-closed. A cross-material dataset that reaches L4 remains useful
method evidence, but the next gap is L5 rather than a false Co3O4 validation claim. An
exact-material dataset that reaches L5 but is development-coupled produces an L6
independence gap rather than being promoted to independent validation.

## State and stagnation

The research-agent state binding now includes:

- verified research-program state;
- scientific-critic report, when supplied;
- validated domain reasoning proposal, when supplied;
- independently verified characterization evidence assessments.

A new evidence assessment therefore constitutes a real research-state transition even if
the mission text is unchanged. Conversely, identical verified state selecting the same
next action stops as `stagnation_no_new_verified_research_state`; repeated planning does
not manufacture progress.

## Authority boundary

The bridge never:

- authorizes downstream characterization use;
- upgrades scientific status;
- fills an empirical gap with synthetic/interpolated data;
- infers calibration, material identity, or independence;
- accesses a network;
- executes a simulation;
- runs a physical experiment.

Any selected next action still has to pass the existing independent authorization and
single typed-executor chain. Physical-experiment and replication work remain proposal-only
until an external facility/operator boundary is separately authorized.

## CLI

The preferred research-agent CLI accepts repeatable assessment files:

```powershell
python -m materials_data_analyzer.research_agent_cli `
  --mission .\configs\research\mission.json `
  --repository-root . `
  --characterization-evidence-assessment .\outputs\saed\evidence_ladder_assessment.json `
  --characterization-evidence-assessment .\outputs\tem\evidence_ladder_assessment.json `
  --output .\outputs\research_iteration.json
```

Each file is reverified before it can affect action ranking.
