# Autonomous Research Scientist Architecture: Characterization Evidence Contract

## System boundary

The project is not a standalone data analyzer. It is a multi-repository **Autonomous Research Scientist Architecture**.

- `materials-characterization-analyzer` is the characterization evidence authority. It owns modality-specific measurement parsing, feature extraction, calibration/method checks, material-domain validation, independent-validation audits, and the monotonic L0-L8 scientific evidence ladder.
- `materials-data-analyzer` is the autonomous research orchestrator. It owns cross-source evidence intake, evidence graphs, discrepancy diagnosis, hypothesis state, evidence-gap planning, explicit action authorization, execution reconstruction, epistemic transitions, recursive re-planning, resource bounds, and stopping decisions.

The repositories exchange immutable, checksum-bound artifacts. Neither repository imports the other's implementation as a scientific authority.

## Why feature handoff alone is insufficient

A feature table can be byte-valid while still being scientifically immature. For example, a TEM/SAED result may have a valid numeric output but still lack raw-byte identity, acquisition provenance, camera/calibration metadata, target-material validation, or an independent parent-disjoint validation set.

Therefore the orchestrator must know both:

1. **what was measured/derived**, through the existing characterization feature bundle; and
2. **how far the evidence has actually matured**, through the independently replayable L0-L8 ladder.

The second item is planning state, not additional empirical evidence.

## L0-L8 contract

The characterization producer may emit schema `1.1` with a `scientific_evidence_ladder` extension:

| Level | Meaning |
|---|---|
| L0 | software integration |
| L1 | raw/lossless representation identity |
| L2 | acquisition and processing provenance |
| L3 | instrument/calibration validity |
| L4 | method/algorithm validation |
| L5 | target material/domain validation |
| L6 | independent external validation |
| L7 | provenance-disjoint multisource replication |
| L8 | engineering decision readiness |

Support is monotonic: a higher level cannot be `Supported` when any lower level is not `Supported`.

`materials-data-analyzer` does **not** trust the producer-authored ladder summary. It independently reconstructs the normalized declaration and assessment, recomputes canonical hashes, verifies the assessment bytes and size, binds declaration identity to the bundle `case_id`, binds the required source roles to the exact bundle evidence-reference SHA-256 values, and binds the ladder modality to the represented bundle instruments.

Legacy schema `1.0` bundles remain supported and do not acquire a ladder by inference.

## Schema-1.1 compatibility boundary

The historical schema-1.0 feature consumer was deliberately closed to unknown schema versions. The research intake layer therefore does not weaken it.

For schema `1.1`, the research adapter:

1. validates authoritative feature/context/evidence bytes and records;
2. creates an isolated temporary schema-1.0 compatibility view containing only the unchanged base bundle fields/files;
3. reuses the historical base validator/consumer against that copy;
4. independently validates the authoritative L0-L8 artifact against the original schema-1.1 bundle;
5. detects source mutation after compatibility validation;
6. rewrites consumer provenance to the original authoritative schema-1.1 manifest and records the independently replayed ladder state.

The temporary compatibility view is implementation plumbing. It is not persisted, is not treated as the source bundle, and cannot downgrade scientific status.

## From blocker to autonomous research gap

The orchestrator compiles the first unsupported L0-L8 level into a deterministic planning artifact. Examples:

- L1 → acquire/verify raw or lossless bytes and stable SHA-256 identity;
- L2 → resolve exact sample/acquisition/processing lineage;
- L3 → obtain or verify instrument/detector/calibration evidence;
- L4 → run predeclared method validation and sensitivity/held-out analysis;
- L5 → acquire direct target-material/domain evidence rather than a proxy;
- L6 → acquire an independent external, leakage-audited validation source;
- L7 → replicate across provenance-disjoint sources/samples/acquisitions/facilities;
- L8 → independently validate operational thresholds, uncertainty, and engineering-use conditions.

The generated `characterization_evidence_gap.json` is checksum-bound to the source bundle, ladder declaration, and ladder assessment. It contains `scientific_status_promoted=false`, `downstream_use_authorized=false`, and `automatic_execution_authorized=false`.

The requirement text is deliberately compatible with the existing self-directed inquiry layer so that it can synthesize candidate external-evidence searches, reanalyses, replications, or physical experiment designs. Candidate generation is still not execution authority.

## Authority chain

```text
real raw measurement / source evidence
        ↓
materials-characterization-analyzer
        ↓  feature bundle + L0-L8 assessment
checksum-bound cross-repository boundary
        ↓
independent consumer replay in materials-data-analyzer
        ↓
characterization evidence-gap artifact
        ↓
discrepancy / autonomous inquiry planner
        ↓
validated candidate match
        ↓
explicit typed authorization + request
        ↓
execution / analysis / simulation / experiment
        ↓
authenticated epistemic transition
        ↓
re-diagnosis → fresh planning → justified continuation/stop
```

No arrow is allowed to manufacture stronger scientific evidence than its inputs establish.

## Scientific non-claims

Passing the L0-L8 transport contract does not by itself establish scientific comparability, causal validity, predictive generalization, physical aliquot identity, independent validation, multisource replication, or engineering readiness. Those properties are true only when the corresponding ladder levels are supported by evidence.

Likewise, the evidence-gap artifact is a research requirement, not a result. It can tell the autonomous system what evidence is missing; it cannot claim that the evidence has been acquired.

## Relationship to recursive research control

This contract complements the bounded recursive controller. The next integration target is to feed characterization-derived evidence gaps into the same hardened discrepancy → planner → authorization → execution → transition → re-diagnosis loop used for other physical evidence sources, while retaining the existing public-API real-data recursive replay as an independent architecture falsification test.
