# NIST AM-Bench Audited Structural Simulation Action

The Stage 1 process-design simulator is reachable through a bounded typed execution path
rather than only as a standalone diagnostic CLI.

## What the action proves

The frozen Stage 1 proposal adds three previously unobserved process cells and nine proposed
replicates to the existing 10-trace design. The response-free calculation checks only design
matrix structure:

- observed design: 10 replicates, 3 observed cells;
- proposed design: 19 structural replicates, 6 cells;
- two-factor interaction: rank 3 -> 4 and full-column-rank after the proposal;
- interaction residual degrees of freedom: 7 -> 15;
- quadratic model remains rank-deficient after the proposal.

No melt-pool response value is read, generated, imputed, simulated, fitted, or predicted.

## Trust chain

The executable path is:

1. frozen NIST descriptive readiness and real process/measurement tables are revalidated;
2. a generic immutable research run supplies the one-action budget;
3. the NIST action registry binds exactly one available simulation action;
4. the mission-rooted request-delegation policy authenticates exact policy bytes under an
   externally supplied mission SHA-256;
5. the compiler binds the exact Stage 1 spec SHA-256 into one deterministic request;
6. an independent request verifier re-authorizes the current planner, registry, research
   ledger, request bytes, and frozen simulation spec;
7. the verifier's exact request SHA-256 and pre-execution research-ledger SHA-256 are passed
   into the NIST executor; stale or altered handoffs fail closed;
8. `authorized_execution.execute_authorized_action` is the only public typed-execution
   router, and a NIST action cannot be routed through the NASA adapter;
9. the common persistent research-ledger lock and recoverable output-to-ledger transaction
   journal cover authorization, typed execution, ledger commit, pinned verification, and
   cleanup;
10. the typed NIST action invokes `simulate_design_structure_file` directly, never a shell,
    and verifies that the simulator-consumed spec snapshot matches the request-pinned SHA;
11. the pinned verifier independently recomputes the structural result and verifies the
    checksum-bound report, output, immutable input, and ledger action;
12. an interrupted post-publication or post-ledger-commit attempt is recovered from the
    checksum-bound transaction rather than re-executed, and replanning then refuses to repeat
    the same simulation.

The dedicated runner `scripts/run_nist_structural_design_action.py` requires both
`--expected-request-sha256` and `--expected-research-ledger-sha256`; these values are the
corresponding outputs of independent authenticated-request verification. This keeps the
machine-authenticated path distinct from an unpinned manual Python API call.

NASA execution remains in its byte-preserved internal core and is reached through the same
public router. Cross-adapter action execution is rejected before NASA planning is entered.

## Scientific boundary

A successful action **does not** close issue #76 and does not promote the NIST evidence above
Diagnostic/descriptive use. The unresolved empirical requirement remains:

- >=3 real traces at 137.9 W / 800 mm/s;
- >=3 real traces at 137.9 W / 1200 mm/s;
- >=3 real traces at 179.2 W / 400 mm/s.

Synthetic or simulated response traces cannot satisfy this requirement. Physical experiment
execution remains external to this repository.
