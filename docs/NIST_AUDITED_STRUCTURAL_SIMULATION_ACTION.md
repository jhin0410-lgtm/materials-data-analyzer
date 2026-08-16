# NIST AM-Bench Audited Structural Simulation Action

The Stage 1 process-design simulator is reachable through a bounded, mission-authenticated
typed execution path rather than only as a standalone diagnostic CLI.

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
5. the compiler binds the exact Stage 1 spec SHA-256, current research-ledger SHA-256,
   selected action, registry, and NIST execution-policy version into one deterministic
   request identity;
6. `execute_nist_authenticated_action` runs the independent authenticated-request verifier
   inside the operational execution call; callers cannot substitute self-computed hashes for
   a claim that this verifier ran;
7. that verifier re-authorizes the current planner, registry, research ledger, request bytes,
   frozen simulation spec, mission/delegation bindings, and downstream execution-policy
   contract;
8. only verifier-derived exact request SHA-256 and pre-execution research-ledger SHA-256 are
   forwarded to the common typed executor; stale or altered handoffs fail closed;
9. `authorized_execution.execute_authorized_action` remains the common typed-execution router,
   requires both SHA pins for NIST, and rejects cross-adapter NIST execution before NASA
   planning is entered;
10. the common persistent research-ledger lock and recoverable output-to-ledger transaction
    journal cover authorization, typed execution, ledger commit, pinned verification, and
    cleanup;
11. the typed NIST action invokes `simulate_design_structure_file` directly, never a shell,
    verifies that the simulator-consumed spec snapshot matches the request-pinned SHA, and
    records immutable input/output byte bindings from single byte snapshots;
12. the pinned result verifier independently recomputes the structural result and verifies
    the checksum-bound report, output, immutable input, and ledger action;
13. an interrupted post-publication or post-ledger-commit attempt is recovered from the
    checksum-bound transaction rather than re-executed, and replanning then refuses to repeat
    the same simulation.

The NIST request compiler/verifier policy is version `1.1`. The request identity and manifest
bind the actual extended NIST execution policy, currently
`1.7+nist-structural-1.1`, rather than only the legacy NASA executor version.

The dedicated operational runner `scripts/run_nist_structural_design_action.py` accepts the
mission, externally supplied expected mission SHA-256, delegation-policy ID and file, request,
manifest, research run, registry, and repository root. It calls the integrated authenticated
execution boundary directly. It does **not** accept caller-supplied request/ledger SHA pins and
does not import the low-level typed router directly.

NASA execution remains in its byte-preserved internal core and is reached through the same
common typed router. The NASA execution-policy compatibility constant remains unchanged.

## Scientific boundary

A successful action **does not** close issue #76 and does not promote the NIST evidence above
Diagnostic/descriptive use. The unresolved empirical requirement remains:

- >=3 real traces at 137.9 W / 800 mm/s;
- >=3 real traces at 137.9 W / 1200 mm/s;
- >=3 real traces at 179.2 W / 400 mm/s.

Synthetic or simulated response traces cannot satisfy this requirement. Physical experiment
execution remains external to this repository.
