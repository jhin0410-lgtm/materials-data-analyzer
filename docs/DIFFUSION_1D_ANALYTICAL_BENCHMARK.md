# 1D Diffusion Analytical Benchmark

Status: `benchmark_executed_with_documented_numerical_error`

## Declared Problem

For `x in [0, L]` and `t >= 0`, the registered relation is:

```text
dc/dt = D d2c/dx2
```

with `L > 0`, `D > 0`, zero Dirichlet boundaries,

```text
c(0,t) = 0
c(L,t) = 0
```

and the single-mode initial condition:

```text
c(x,0) = A sin(pi x/L)
```

The exact reference is:

```text
c_exact(x,t) = A sin(pi x/L) exp(-D pi^2 t/L^2)
```

No series truncation is needed. The boundaries are absorbing, so the benchmark
does not make a mass-conservation claim.

## Canonical Configuration

- `L = 1.0 m`
- `D = 0.1 m^2/s`
- `A = 1.0 unitless`
- final time `0.4 s`
- 21 spatial points and 40 time steps
- `dx = 0.05 m`, `dt = 0.01 s`, FTCS ratio approximately `0.4`

The values are synthetic software-benchmark parameters, not properties of a
Battery, semiconductor, thermal system, or real material.

## Actual Results

The canonical FTCS run produced a final-profile L2 error of
`0.000530682558161965` and maximum absolute error of
`0.0007690320882955959`. The maximum boundary residual was `0.0`; the initial
condition residual was `1.2246467991473532e-16`. All values were finite and the
positive-input field remained nonnegative within the declared numerical
tolerance.

The predeclared coarse, medium, and fine L2 errors were respectively
`0.002100929710682888`, `0.000530682558161965`, and
`0.00013385002156730884`. This supports decreasing error under the declared
refinement. No exact convergence-order claim is made.

Field arrays remain under ignored `outputs/v2_4_diffusion_benchmark/`; only
compact checksums, metrics, trust, and claim evidence are tracked.

## CLI

```powershell
python -m src.cli preview-diffusion-1d-benchmark configs/examples/pgir_diffusion_1d_benchmark.json
python -m src.cli run-diffusion-1d-benchmark configs/examples/pgir_diffusion_1d_benchmark.json
python -m src.cli run-diffusion-1d-refinement-audit configs/examples/pgir_diffusion_1d_refinement_audit.json
python -m src.cli export-diffusion-1d-benchmark-summary
```

Preview validates and reports the requested stability ratio without executing
either Propagator. The three execution commands use only synthetic config data
and perform no network access or fitting.
