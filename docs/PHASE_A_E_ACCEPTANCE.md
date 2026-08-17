# Phase A-E autonomous research acceptance

The acceptance runner is:

```bash
python scripts/run_phase_a_e_acceptance.py --output outputs/phase_a_e_acceptance
```

It is deliberately deterministic and offline. Phase A replays only trusted NIST
repository discovery, metadata, checksums, and acquired bytes. Those replay bytes are
not scientific measurements and are not accepted into scientific evidence. Phases B-E
then use the repository's tracked NIST AM-Bench 2018-02 IN625 process and optical-
metrology tables through the existing representative workflow.

## Acceptance meaning

A successful run returns:

`architecture_acceptance_passed_with_empirical_gaps`

This means the architecture preserves provenance and scientific gates across all five
phases. It does **not** mean an IN625 hypothesis has been scientifically verified.

### Phase A

Trusted discovery and checksum-bound acquisition are exercised without network access.
The loop must stop at `insufficient_evidence` because no scientific intake adapter is
allowed to promote the replay bytes.

### Phase B

One source-declared NIST trace is normalized into the existing epistemic graph with the
exact tracked measurement-table SHA-256 and record locator. The NIST source declares
`IN625` but does not provide elemental composition in the tracked table, so acceptance
uses `MaterialIdentity` and records `material_composition_known=false`. No alloy
composition is inferred.

### Phase C

The real case remains ten traces across three coupled power-speed conditions. Same-source
replicates are not treated as independent sources. Because design identifiability is not
verified for predictive/causal modeling, the generic analysis router must choose a
design-identifiability audit before bounded regression.

### Phase D

The existing NIST case predates the explicit downstream-use/review contract required by
Phase D. Acceptance therefore requires fail-closed behavior: characterization is not
promoted into new scientific evidence and no reviewed status is fabricated. This is a
successful governance-gate test, not a characterization validation success.

### Phase E

The existing response-free structural design simulator evaluates the source-derived
Stage 1 and cumulative Stage 1+2 design proposals. The immediate budget proxy is the
planned Stage 1 trace count, so only Stage 1 is affordable in that bounded comparison.
Rank gain, residual degrees of freedom, and new unique cells are structural proxies;
probabilistic expected information gain remains `not_quantified`. The compiled action
uses the existing authorization/typed-executor route and does not execute a physical
experiment.

## Remaining empirical gaps

The acceptance keeps the following GitHub issues open:

- **#76** — exact independent NIST AMMT cross-process IN625 evidence remains incomplete.
- **#156** — NIST MDS2-2923 actual semantic mapping, sample identity, and reviewed
  characterization-use binding remain incomplete.

Neither issue is satisfied by architecture tests, deterministic repository replay, or
response-free simulation.
