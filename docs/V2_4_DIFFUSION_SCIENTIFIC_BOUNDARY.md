# v2.4 Diffusion Scientific Boundary

Status: `bounded_benchmark_validated`

## Supported

- a versioned PGIR Model Contract was validated and executed
- exact and deterministic FTCS Propagators were compared
- dimensions, initial conditions, boundaries, and FTCS stability were checked
- numerical error decreased across predeclared coarse/medium/fine grids
- execution lineage and deterministic checksums were recorded
- physical-operator execution was demonstrated for this synthetic benchmark

## Not Supported

- Battery diffusion or lithium concentration interpretation
- real-material diffusivity or fitted physical parameters
- semiconductor, thermal, or other domain interpretation
- cross-domain physical-operator reuse
- general PDE solver validation
- mass conservation under absorbing boundaries
- independent validation or production validation
- Aspen replacement or industrial simulation readiness

Empirical parameter uncertainty is unavailable. The reported exact-reference
differences are numerical discretization evidence, not measurement uncertainty
or a confidence score.

The v2.2 composition and structure decisions, v2.3 Battery decisions, and
v2.4.1 external-source/PGIR reuse decisions remain unchanged.
