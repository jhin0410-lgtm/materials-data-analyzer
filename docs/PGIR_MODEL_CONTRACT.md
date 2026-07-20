# PGIR Model Contract

Status: `v2.4.2_bounded_contract_executed`

The first executable PGIR Model Contract is
`one_dimensional_diffusion_zero_dirichlet_v1`. It is a strict JSON-safe record
for one synthetic one-dimensional scalar diffusion benchmark. It is not a
symbolic equation engine and cannot contain Python expressions, callables,
module paths, credentials, or absolute paths.

## Contract Contents

The contract declares the scalar field `c`, coordinates `x` and `t`, parameters
`L`, `D`, and `A`, the governing relation, one initial condition, two endpoint
boundary conditions, required operators, dimensions, applicability, maturity,
validation criteria, provenance, uncertainty policy, and claim boundaries.

The tracked contract is
[`data/platform/pgir_diffusion_1d_model_contract_v1.json`](../data/platform/pgir_diffusion_1d_model_contract_v1.json).
Its schema is
[`data/platform/pgir_model_contract_schema_v1.json`](../data/platform/pgir_model_contract_schema_v1.json).
Unknown fields and unsupported schema versions are rejected instead of being
silently dropped.

## Units And Dimensions

The existing `ScientificQuantity` and builtin unit backend validate:

- `L`: length, canonical unit `m`
- `D`: diffusivity, canonical unit `m^2/s`
- final time: time, canonical unit `s`
- `A` and `c`: the same dimensionless unit in the canonical example

Pint remains optional. The explicit builtin registry gained only the bounded
`m^2/s` diffusivity unit; no free-form symbolic unit parser was introduced.

## Execution Boundary

Only three pre-registered operators are eligible: exact propagation, FTCS
propagation, and analytical-numerical evaluation. A config cannot supply a
callable or import path. The contract does not authorize a general PDE solver,
parameter fitting, network access, Battery interpretation, or a real-material
diffusivity claim.
