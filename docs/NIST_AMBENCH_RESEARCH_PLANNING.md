# NIST AM-Bench Research-Planning Benchmark

## Purpose

The NIST AM-Bench 2018-02 process-characterization case is used as a real-data
correct-blocker benchmark for the domain-general research loop.

The tracked case contains ten AMMT traces at three process conditions for IN625
and source-reported transverse optical-metrology melt-pool measurements. The
existing case is complete for descriptive diagnostics and remains `Diagnostic`.
It is not a predictive, causal, optimization, or engineering-validation dataset.

## Planning adapter

The common adapter identifier is:

```text
nist-ambench-process-characterization
```

The same common commands used by the other domains may inspect it:

```powershell
mda-research-loop plan-next-action `
  --adapter nist-ambench-process-characterization `
  --repository-root .

mda-research-loop show-planning-state `
  --adapter nist-ambench-process-characterization `
  --repository-root .

mda-research-loop decide-transition `
  --adapter nist-ambench-process-characterization `
  --repository-root .

mda-research-loop run-research-cycle `
  --adapter nist-ambench-process-characterization `
  --repository-root .
```

## Current decision

The current decision is `no_positive_value_action` for the frozen descriptive
scope. The planning state is `terminal_for_current_scope`, while also preserving
an exact evidence gap for any future stronger-use proposal.

This distinction is intentional. The system is not claiming that research on the
NIST case can never continue. It is saying that no currently tracked executable
software action can manufacture the missing physical independence and validation
evidence.

## Frozen evidence requirement

Before predictive use is reconsidered, the planning contract requires:

1. genuinely additional physical AMMT trace evidence under predeclared process
   conditions beyond the current three-condition case;
2. stable trace/sample identity plus authoritative process, specimen,
   acquisition, and preprocessing lineage;
3. the same optical-metrology procedure or a scientifically justified
   compatibility mapping, including measurement uncertainty;
4. an explicit independence/split grouping contract with enough independent
   groups or conditions for the intended validation design;
5. measurement timing relative to the intended prediction target, with
   pre-outcome timing required for predictive characterization features.

Additional row count alone does not satisfy this requirement.

## Correct autonomous behavior

For the currently tracked evidence the bounded one-step cycle must:

- expose the physical-evidence blocker;
- preserve `Diagnostic` / `descriptive` as the maximum current claim boundary;
- propose no executable model-fitting or synthetic-data action;
- perform no network acquisition or experiment control;
- stop the current scope;
- retain explicit reopen conditions for manual semantic review if genuinely new
  physical evidence appears.

A future file offered against a reopen condition is checksum-bound only. The
existing transition gate still requires manual semantic review and does not infer
that the condition has been satisfied.

## Scientific boundary

This benchmark validates planning/control behavior against a real
process-characterization limitation. Passing its tests does **not** establish
physical sample comparability beyond the tracked NIST lineage, predictive
validity, causality, process optimization, engineering readiness, or external
validation.
