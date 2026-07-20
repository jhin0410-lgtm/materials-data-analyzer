# PGIR 1D Diffusion Benchmark Summary

This is a synthetic platform-validation benchmark, not a Battery or real-material diffusion model.

- Status: `benchmark_executed_with_documented_numerical_error`
- Model contract: `one_dimensional_diffusion_zero_dirichlet_v1`
- Grid: 21 spatial points, 40 time steps
- FTCS stability ratio: 0.3999999999999999
- Final-profile L2 error: 0.000530682558161965
- Final-profile maximum absolute error: 0.0007690320882955959
- Boundary residual: 0.0
- Initial-condition residual: 1.2246467991473532e-16
- Cross-domain physical-operator reuse: not demonstrated
- Independent validation: not demonstrated
- Production validation: not demonstrated

## Refinement

- Predeclared cases: 3
- Error strictly decreases: true
- Fine error below coarse error: true
- Exact convergence order claimed: false
