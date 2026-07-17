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

- Battery Observation/State/Trajectory adapter audit.
- Battery cycle rows remain observations unless state sufficiency is proven.
- No degradation mechanism fitting.

## v2.3.3

- Dynamic mechanism candidate audit.
- Diffusion versus Arrhenius feasibility comparison.
- Data sufficiency and identifiability gates.

## v2.3.4

- One bounded mechanism Evaluator if readiness gates pass.
- Not a general solver.

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
