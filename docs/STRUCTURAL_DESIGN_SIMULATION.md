# Structural Experiment-Design Simulation

## Purpose

The autonomous research program needs computational experiments that can answer a scientific planning question without inventing measurements. The first such primitive is a response-free two-factor design simulation.

It asks:

> If the proposed process conditions and replicates were acquired, which polynomial design terms would become structurally estimable, and how much residual design freedom would exist?

It does **not** ask what the response would be.

## Inputs

A strict JSON specification declares:

- exactly two factor names and units;
- currently observed factor-value cells and replicate counts;
- proposed cells and replicate counts;
- structural model families to inspect;
- a scientific boundary that disables response use, coefficient/effect estimation, prediction, causal inference, optimization, and engineering decisions.

Unknown fields fail closed. Boolean factor values are rejected before numeric coercion. Duplicate JSON keys are rejected when a file specification is loaded.

## Structural models

The current primitive evaluates the column rank of:

- intercept: `1`;
- main effects: `1 + x1 + x2`;
- interaction: `1 + x1 + x2 + x1*x2`;
- quadratic: `1 + x1 + x2 + x1*x2 + x1^2 + x2^2`.

Factors are centered and scaled for numerical rank evaluation. No response vector exists.

For each model the simulator reports:

- parameter count;
- matrix rank;
- full-column-rank status;
- residual degrees of freedom;
- rank gain after the proposal;
- residual-df gain after the proposal.

It also reports factor levels, observed-level grid coverage, missing cells, new unique cells, and replication-only additions.

## Information-gain boundary

`rank_gain` and `residual_df_gain` are structural diagnostics. They are **not** expected information gain.

The output therefore records:

```json
{
  "expected_information_gain": {
    "status": "not_quantified",
    "value": null
  }
}
```

A future probabilistic information-gain tool would require an explicit response/noise/prior model and a separate validation contract.

## NIST AM-Bench Stage 1 benchmark

The tracked benchmark binds the representative IN625 AMMT case:

| Cell | Actual laser power | Scan speed | Traces |
|---|---:|---:|---:|
| A | 137.9 W | 400 mm/s | 3 |
| B | 179.2 W | 800 mm/s | 3 |
| C | 179.2 W | 1,200 mm/s | 4 |

The predeclared Stage 1 additions are:

| Proposed cell | Actual laser power | Scan speed | Minimum traces |
|---|---:|---:|---:|
| 1 | 137.9 W | 800 mm/s | 3 |
| 2 | 137.9 W | 1,200 mm/s | 3 |
| 3 | 179.2 W | 400 mm/s | 3 |

The structural result is intentionally narrower than “modeling ready”:

- current main-effects matrix: already full rank (`3/3`);
- current interaction matrix: rank `3/4`, not structurally identifiable;
- after Stage 1: interaction rank `4/4` with residual df `15`;
- after Stage 1: quadratic rank `5/6`, still not fully identifiable because only two laser-power levels exist.

Therefore Stage 1 resolves the observed two-level-power × three-level-speed interaction structure. It does **not** establish quadratic power curvature, a predictive model, a causal effect, an optimum, or a safe machine condition.

## Run

```powershell
python -m materials_data_analyzer.research_design_simulation_cli `
  --spec configs/research/nist_ambench_stage1_structural_design_simulation.v1.json `
  --output outputs/nist_stage1_structural_design_simulation.json
```

## Relationship to autonomous research

This primitive is suitable for later registration as a typed `computational_experiment` action because:

- its input and output are deterministic and bounded;
- it cannot create empirical observations;
- it has explicit prohibited effects;
- it produces a checksum-bindable artifact;
- its result can enter the epistemic graph only through a separate domain-verified relation.

It should be promoted into the execution registry only after the standalone primitive and repository benchmark are fully validated.
