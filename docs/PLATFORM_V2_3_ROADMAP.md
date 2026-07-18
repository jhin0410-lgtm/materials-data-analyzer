# Platform v2.3 Roadmap

Status: `development_stage`

v2.3 moves from v2.2 scientific metadata and Materials structure evidence
toward a Physically Grounded Intermediate Representation (PGIR). The roadmap is
governance-first: it introduces representation contracts before any mechanism
solver, model retraining, or experiment recommendation.

## v2.3.1

- PGIR architecture RFCs.
- Current implementation to PGIR mapping.
- Representation maturity model.
- Schema ownership and compatibility governance.
- Capability-stage registry.
- CLI inspection commands and optional platform-report section.

## v2.3.2

- PGIR conformance gates for representation declarations, maturity promotion,
  context compatibility, registered transitions, and capability eligibility.
- Battery Observation, bounded operational State, and Trajectory adapter pilot
  using existing processed battery summaries only.
- Compact tracked Battery PGIR coverage, maturity, transition,
  mechanism-readiness, and decision summaries.
- Battery cycle rows remain observations unless a registered transformer and
  sufficient context justify a bounded operational summary.
- No degradation mechanism fitting, solver execution, SOH/RUL model, or
  predictive claim.

## v2.3.3

- Dynamic mechanism candidate audit completed for Battery PGIR.
- Diffusion versus Arrhenius feasibility comparison completed as an
  evidence-gap and identifiability audit.
- Data sufficiency and identifiability gates completed with actual Battery
  coverage.
- Outcome: `descriptive_evaluator_only`; no Arrhenius, diffusion, SOH/RUL, or
  predictive mechanism claim.

## v2.3.4

- Implement the selected bounded capacity-trajectory consistency Evaluator if
  release gates still pass.
- Not a general solver, Propagator, Arrhenius fit, diffusion model, or
  predictive battery model.

## v2.3.5

- Mechanism residual and uncertainty validation.
- Claim-boundary update from actual evidence.

## v2.3.6

- Second-domain reuse feasibility.
- No cross-domain mechanism claim until executed and validated.

## v2.3 Closeout

The closeout target is one dynamic-domain workflow with explicit mechanism
evidence and claim boundaries. General physics intelligence, production
scientific decisions, GNN/PINN, dashboard UI, and autonomous experiment
recommendation remain out of scope unless separately implemented and validated.
