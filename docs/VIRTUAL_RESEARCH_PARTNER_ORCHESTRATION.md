# Virtual Research Partner Orchestration

## Product direction

The project goal is not a collection of independent analyzers and it is not a
NASA Battery program. The target is a bounded **Virtual Research Partner** that
can repeatedly decide what evidence is missing, obtain or request the next
scientifically appropriate evidence, re-run analysis, and stop when further work
is not justified.

The intended closed loop is:

```text
research objective and claim boundary
-> inspect available evidence and provenance
-> identify the current limiting uncertainty or blocker
-> rank bounded next actions
-> execute one scientifically eligible action
-> independently verify the new evidence/result
-> update the research state
-> re-evaluate the hypothesis and model/trust status
-> continue, request new evidence, or stop
```

A useful loop may improve predictive performance, reduce uncertainty, resolve a
metadata blocker, discover that two sources are not comparable, or correctly
stop. Performance improvement is not required on every iteration and a negative
result must not trigger unconstrained model or dataset searching until something
looks favorable.

## What "automatically find more data" means

External-data search is part of the target system, but it is **requirement
conditioned**, not generic web crawling.

Before any source discovery action, the research state should state the concrete
gap, for example:

- missing protocol-temperature support;
- insufficient independent samples;
- missing raw detector intensities;
- missing calibration or acquisition lineage;
- narrow process-condition coverage;
- poor generalization to an identified chemical-system region;
- uncertainty concentrated in a specific descriptor/domain region.

A source-discovery action may then search trusted repositories or APIs for data
that can address that gap. Candidate data must still pass source identity,
license/reuse, chemistry/material domain, measurement method, units, target
semantics, processing history, independence, and comparability checks before it
can strengthen a scientific claim.

Finding more rows is therefore not itself progress. A new source can be:

- **eligible evidence**;
- **diagnostic-only evidence**;
- **incompatible evidence**;
- **metadata-incomplete evidence**;
- **unusable evidence**.

The system must preserve those distinctions.

## Repository responsibilities

### `materials-data-analyzer`

Owns higher-level research orchestration and tabular/process/Battery/reliability
analysis:

- research objective, hypothesis, evidence and action state;
- bounded action registry and budgets;
- data-readiness and leakage checks;
- model/baseline evaluation and error diagnosis;
- external-data requirement generation;
- source-candidate eligibility decisions;
- process, Battery, reliability, SPC and materials-property workflows;
- retrospective closed-loop benchmarks;
- downstream use of characterization feature bundles;
- scientific closeout and next-action selection.

### `materials-characterization-analyzer`

Remains an independently installable instrument-specific evidence producer:

- XRD;
- SEM;
- EDS;
- Raman;
- TEM;
- SAED;
- XPS;
- FTIR;
- TGA/DSC;
- characterization-specific source/metadata validation;
- review-required feature extraction;
- characterization result contracts and downstream-use policy.

The two repositories should **not** directly import each other's internal modules.
They communicate through versioned, checksum-bound files with stable sample and
acquisition identifiers.

## One orchestration, two repositories

Development can be coordinated from one working conversation without combining
the repositories. Work should be sequenced so that only one side of a shared
contract changes at a time unless a deliberately paired cross-repository change
is required.

For a cross-repository change:

1. define or update the versioned contract;
2. implement the producer change in `materials-characterization-analyzer`;
3. verify the producer independently;
4. implement/verify the consumer in `materials-data-analyzer`;
5. run the cross-repository compatibility gate;
6. merge only after both repositories preserve their standalone workflows.

This avoids two separate conversations making incompatible changes to the same
handoff contract while still keeping both repositories independently usable.

## Bounded action families

The eventual generic research loop should rank actions from a small auditable
inventory rather than generate arbitrary code or commands.

### Existing-data actions

- validate schema, units, identifiers and provenance;
- perform EDA/SPC/reliability/process diagnostics;
- run fixed baseline models;
- evaluate group/time/asset generalization;
- perform target/reference or protocol sensitivity;
- inspect error/OOD/applicability structure;
- consume an eligible characterization bundle.

### New-evidence actions

- generate an exact data requirement;
- search trusted external repositories/APIs against that requirement;
- audit candidate source semantics and comparability;
- acquire checksum-bound public data when authorized;
- request or schedule a physical experiment/measurement when public data cannot
  satisfy the requirement;
- request a characterization analysis through the versioned handoff contract.

### Method actions

- re-fit a predeclared simple model after new evidence is admitted;
- compare an eligible alternative baseline or feature family;
- use a more complex method only when its eligibility conditions are satisfied;
- calibrate/abstain only when enough independent validation evidence exists.

### Terminal actions

- supported closeout;
- diagnostic closeout;
- inconclusive closeout with an exact evidence requirement;
- unsupported closeout;
- manual review when the semantic decision cannot be automated defensibly.

## Current benchmark roles

### NASA Battery

Role: negative-result and correct-stop benchmark.

The current exact-horizon Ridge conclusion is `Unsupported`. The loop correctly
identified an external-evidence requirement and rejected a structurally strong
but semantically incompatible KIT cohort. NASA should remain frozen until a
protocol-comparable cohort exists; it is not the main development target.

### Materials Project

Role: controlled acquisition and research-efficiency benchmark.

The real v1.3 data are now partitioned into seed evidence, a target-hidden
acquisition pool, and a locked test. The next stage measures whether a bounded
adaptive policy can choose additional evidence more efficiently than fixed,
random, and predeclared diversity baselines.

This is the controlled analogue of "find more useful data, retrain, and check
whether the evidence improved." It is deliberately implemented before live
source-search autonomy so target leakage and favorable-source selection can be
tested under known ground truth.

### NIST AM-Bench process-characterization

Role: confounding, identifiability, and next-experiment design benchmark.

The current representative case is blocked on specific additional physical
traces. The correct autonomous behavior is to preserve the exact measurement
requirement rather than simulate or infer missing traces.

### Characterization cases

Role: instrument-specific evidence quality, cross-method comparability, and
external-source acquisition benchmarks.

TEM/SAED currently demonstrate the key distinction between public availability
and scientifically usable external validation. Other analyzer families provide
real-data diagnostic cases but must not be promoted beyond their metadata,
calibration and validation support.

## Current implementation step

The Materials Project Stage 4 benchmark instance is pinned to the verified local
838-row source and partition hashes. The costed acquisition loop then compares
four predeclared strategies:

- `fixed_catalog`: fixed non-adaptive order;
- `random`: deterministic seeded random baseline;
- `diversity`: target-blind descriptor-diversity baseline;
- `uncertainty`: adaptive fixed-model-disagreement policy.

The acquisition unit is one complete `chemical_system_group`; cost equals the
number of revealed material labels in that group. The sequence may use seed
labels and acquisition descriptors, but it cannot read locked-test content.
Locked evaluation occurs only after the sequence is complete.

This stage does not yet prove autonomous research superiority. It creates the
first reproducible test of adaptive evidence acquisition under a fixed budget.

## Now / Next / Later

### Now

1. Freeze the verified real Materials Project benchmark instance.
2. Execute and validate costed acquisition sequences.
3. Compare locked performance, label cost and failure behavior across the four
   predeclared strategies.
4. Keep NASA and NIST blocked cases frozen rather than adding purposeless actions.
5. Continue characterization work from the same orchestration plan, beginning
   with evidence gaps already recorded in its open source-audit queue.

### Next

1. Promote the best scientifically defensible acquisition-policy *class* only if
   the locked comparison supports it; do not tune benchmark v1 after seeing the
   test result.
2. Generalize the research-loop action interface beyond NASA-specific adapters.
3. Add a requirement-conditioned trusted-source discovery action.
4. Add a characterization-evidence action that consumes only validated handoff
   bundles and respects `downstream_use_policy`.
5. Re-run the same planner/verifier logic on at least one process/reliability and
   one characterization case.

### Later

1. Add additional independent benchmark families.
2. Add live source acquisition only through provenance- and license-aware
   connectors/adapters.
3. Add optional higher-complexity methods only when simple baselines and
   independent validation justify them.
4. Consider experiment-design recommendations that require human/facility
   approval rather than automatic machine control.

## Promotion standard

The system should be called a scientifically useful Virtual Research Partner only
when it can show, across multiple independent cases, that it:

- chooses valid next actions rather than merely more actions;
- obtains relevant evidence with lower cost or fewer measurements;
- improves predictive or decision evidence when improvement is possible;
- detects incompatible or misleading external data;
- preserves locked evaluation and prevents leakage;
- records provenance and preprocessing completely;
- stops correctly when evidence cannot support the requested claim;
- produces an exact next-evidence requirement when blocked;
- can consume characterization evidence without silently promoting descriptive
  features into predictive or causal claims.
