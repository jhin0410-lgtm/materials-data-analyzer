# Characterization evidence in the Autonomous Research Scientist Architecture

`materials-data-analyzer` is the research orchestrator in the broader **Autonomous Research Scientist Architecture**. `materials-characterization-analyzer` is a separate characterization evidence authority. The repositories remain independently testable and communicate through persisted, checksum-bound evidence contracts rather than a shared runtime implementation.

## Integration path

The orchestrator now recognizes two characterization handoff forms:

- schema `1.0`: the legacy feature/provenance handoff with no L0-L8 maturity artifact;
- schema `1.1`: the same feature/provenance handoff plus an independently replayable scientific evidence-ladder assessment.

The consumer does **not** import the producer's `mca` evaluator. It independently validates the L0-L8 declaration grammar, monotonicity, canonical declaration and assessment SHA-256 digests, file checksum and size, case identity, empirical source bindings, represented modality, readiness fields, and explicit no-promotion/no-authorization flags.

This redundancy is intentional. A producer-authored maturity summary is not trusted merely because it is present in the bundle.

## L0-L8 interpretation

The characterization ladder is ordered:

1. L0 software integration
2. L1 raw representation identity
3. L2 acquisition provenance integrity
4. L3 instrument calibration validity
5. L4 method/algorithm validation
6. L5 target material/domain validation
7. L6 independent external validation
8. L7 replicated multisource support
9. L8 engineering decision readiness

Only a contiguous chain of `Supported` levels counts as attained. A higher level cannot skip an unresolved lower level.

## Autonomous planning adapter

`materials_data_analyzer.characterization_research_gap` converts the first independently verified blocking level into deterministic planning metadata:

- L1 → acquire/recover raw byte identity;
- L2 → establish sample/acquisition provenance;
- L3 → establish calibration validity;
- L4 → run predeclared method validation;
- L5 → acquire direct target-material/domain evidence;
- L6 → acquire provenance-independent external validation;
- L7 → replicate across provenance-disjoint sources;
- L8 → establish operational engineering validation and thresholds.

Legacy schema-1.0 bundles do **not** get assigned an inferred level. They produce `characterization_evidence_maturity_assessment_required` instead.

Every generated research-gap artifact carries its own canonical SHA-256 and the explicit marker `planning_requirement_not_scientific_evidence`.

## Trust boundary

An L0-L8 assessment is evidence-maturity metadata. It is not new empirical evidence. It cannot establish sample comparability, causality, predictive generalization, engineering readiness, or authorization for a downstream use.

The existing downstream-use policy remains a separate gate. The ladder always preserves:

- `scientific_status_promoted=false`
- `downstream_use_authorized=false`

This separation is essential for autonomous operation: the research scientist may use a blocker to decide what evidence to seek next, but it may not close the blocker by software convention.

## Relationship to the recursive controller

The recursive research controller and its public multi-cycle real-data replay remain separate acceptance layers. Characterization maturity becomes one additional provenance-bound source of evidence gaps. It does not bypass action authorization, immutable execution provenance, authenticated epistemic transition, hardened re-diagnosis, or bounded stopping.
