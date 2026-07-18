# Physical Propagator Validation

Status: `bounded_physical_operator_execution_demonstrated`

v2.4.2 registers and executes two Propagators for one model contract:

- `one_dimensional_diffusion_exact_propagator_v1`
- `one_dimensional_diffusion_ftcs_propagator_v1`

The evaluator is
`one_dimensional_diffusion_benchmark_evaluator_v1`.

## FTCS Gate

The numerical backend uses `r = D dt / dx^2` and requires `0 < r <= 0.5`.
An unstable request is returned as
`blocked_unstable_numerical_configuration`. The requested `D`, `dt`, and `dx`
are retained in the blocked result; none is silently changed.

Before execution, the implementation validates the registered relation and
operators, units, dimensions, positive domain/time parameters, grid bounds,
uniform grids, initial/boundary compatibility, and bounded resource limits.
After execution it validates finite values, nonnegativity for the positive
fixture, exact/numerical checksums, boundary and initial residuals, and
predeclared refinement.

## PGIR Maturity

The model declaration is physically admissible for the registered benchmark.
The exact field, FTCS field, and evaluator result reach
`scientifically_evaluated` only for this contract and configuration. Three
explicit transitions record model-to-exact-field, model-to-numerical-field,
and field-to-evaluation lineage.

This does not promote the PGIR platform or unrelated data to independent or
production validation. `cross_domain_physical_operator_reuse` remains false.
