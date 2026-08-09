# Domain-General Research Planning Baseline

## Purpose

`materials-data-analyzer` is the higher-level Materials Virtual Research Partner.
Its research loop must decide what scientifically useful action comes next across
materials domains, not merely run a fixed Battery workflow or keep adding
instrument analyzers.

This baseline introduces one common, **read-only** planning-decision surface over
existing domain-specific scientific policies. It is deliberately smaller than a
fully autonomous agent: it recommends or stops, but it never executes an action,
searches the network, acquires data, fits a model, or upgrades evidence.

## Stable command

```powershell
mda-research-loop plan-next-action `
  --adapter <adapter-id> `
  --repository-root .
```

The initial adapters are:

- `nasa-battery`
- `materials-project-external-source`
- `tm-fe-si-descriptive`

The NASA adapter additionally requires `--run` and `--registry`. The historical
`plan-nasa-next-action` command remains supported and unchanged.

## Common decision contract

Every adapter returns the same planning fields:

- schema and adapter version;
- adapter and domain identifiers;
- `selection_status`;
- optional `selected_action`;
- bounded `candidates`;
- human-readable `reason`;
- current evidence level when the tracked case exposes one;
- maximum allowed downstream use when the tracked case exposes one;
- checksum-bound evidence bindings;
- explicit flags showing that planning performed no network access, action
  execution, model fitting, or evidence upgrade.

The common shape does **not** make scientific rules generic. Domain-specific
rules remain owned by their existing modules and evidence contracts.

## Adapter behavior

### NASA Battery

The adapter delegates to the existing deterministic
`plan_nasa_next_action()` policy. It does not copy or reinterpret NASA action
scores, budgets, stop rules, or protocol logic. This preserves the existing
negative-result/correct-stop benchmark while exposing it through the common
surface.

### Materials Project external-source search

The adapter revalidates the tracked external-evidence requirement and all frozen
candidate metadata/semantic checks with the existing domain-neutral external
source compatibility contract. A small tracked planning closeout freezes the
expected current result:

- 4 audited high-priority candidates;
- 0 eligible candidates;
- 3 `scientifically_ineligible`;
- 1 `diagnostic_only`.

If those dispositions drift, planning fails closed rather than silently keeping
the old stop. Under the current tracked evidence, the correct decision is
`no_positive_value_action`; broad database hunting must not restart merely
because more rows or another `energy_above_hull`-like field exists.

### TM-Fe-Si descriptive case

The adapter revalidates the tracked cross-repository readiness contract. The
real XRD-to-M-H case is complete at `Diagnostic` evidence with maximum allowed
use `descriptive`. Predictive, causal, and engineering readiness remain false.
Therefore the correct current decision is `no_positive_value_action`, not more
TM-Fe-Si algorithms merely to expand scope.

## Why correct stopping is part of autonomy

An autonomous research system that always proposes another analysis is not a
research partner; it is an analysis generator. A scientifically useful planner
must distinguish:

- a positive-value next action;
- an exact evidence requirement;
- a manual semantic decision;
- budget or implementation blocking;
- a completed or unsupported scope where additional work is not justified.

The first cross-domain baseline therefore intentionally includes two completed
or exhausted cases alongside NASA. Demonstrating consistent stopping across
domains is as important as demonstrating action selection.

## Scientific boundary

This baseline validates software/planning contracts only. It does not establish
that one planning policy is scientifically optimal across materials domains.
It does not perform literature search, source acquisition, experiment design,
model training, causal inference, or autonomous execution.

Those capabilities should be added only behind bounded action contracts and
validated against cases where the next action can be judged independently.

## Next development step

After this common planning surface is stable across the three initial adapters,
the next MDA-centered step is to represent the **research question, current
blocker, candidate action families, expected information value, evidence
requirements, and stop condition** in a domain-general planning state. Existing
NASA, Materials Project, NIST/process-characterization, and future materials
cases should plug into that state through adapters rather than spawning separate
autonomous frameworks.

MCA remains an independent instrument-evidence subsystem and should be invoked
only when a research question requires characterization evidence that the
current state does not already contain.
