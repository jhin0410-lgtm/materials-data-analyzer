# v2.7.0 Public Release Promotion Closeout

## Decision

The stable public version is **v2.7.0**.

The previously selected v2.6.0 candidate remains superseded. The tracked
v2.6.14 closeout explicitly closes the Battery v2.6 evidence line, authorizes no
automatic v2.6.15 stage, and directs later work to a separate end-to-end case or
a materially new evidence-backed reopening.

After that closeout, 38 audited commits added a distinct integration and public-
repository scope: generic characterization handoff, pinned producer-consumer
workflows, the representative NIST process-characterization workflow, repository
hardening, citation governance, and release-readiness audits. v2.7.0 preserves
that boundary instead of retroactively relabeling the later work as v2.6.0.

The promotion updates `PUBLIC_RELEASE_VERSION`, runtime `PLATFORM_VERSION`,
`CITATION.cff`, the root changelog, roadmaps, public release status, and
`docs/releases/V2_7_0.md` together. It does not create an external Git tag or
GitHub Release.

## Complete included history

Every internal stage below is included as development history, not as a separate
public release:

- v2.5.1 compatibility adapters;
- v2.5.2 retrieval-reproducibility audit;
- v2.6.1 warm-start Battery forecast benchmark;
- v2.6.2 forecast-failure diagnostics;
- v2.6.3 comparability evidence;
- v2.6.4 external-cohort admission gate;
- v2.6.5 SNL LFP source-evidence recovery;
- v2.6.6 local artifact binding;
- v2.6.7 source-to-entry binding;
- v2.6.8 bounded schema read;
- v2.6.9 bounded cycle-regime review;
- v2.6.10 transition-artifact evidence closeout;
- v2.6.11 next external-source selection;
- v2.6.12 Michigan Formation provider-package structure review;
- v2.6.13 Deep Blue metadata-access closeout;
- v2.6.14 checksum-bound external-evidence-line closeout.

The v2.6 core closeout commit is:

```text
50e3ee1201ef791b250558a30c373848d615f815
```

The audited pre-promotion repository boundary is:

```text
ed5eac38584a174edbb9216aca10fc8232cdb504
```

That boundary is 38 commits ahead of the v2.6 core closeout.

## Post-v2.6 release scope

The new minor-release boundary additionally includes:

1. public repository hardening, license, security, contribution, citation, and
   release-governance files;
2. schema `1.0` checksum-bound characterization-bundle consumption;
3. explicit sample-context and external process-table identity gates;
4. pinned DWCNT, RWGS, four-carbon-material, and NIST AM-Bench
   producer-consumer workflows;
5. the representative NIST process-characterization workflow;
6. process-design identifiability and one-to-one condition identity checks;
7. bounded minimum design augmentation;
8. official NIST commanded-to-actual power and laser-spot-size provenance;
9. offline cross-repository release-readiness auditing.

## Preserved scientific outcomes

### v2.5

- software compatibility verdict: **Supported**;
- Materials adapter: `compatible_with_restrictions`;
- Battery adapter: `partial`;
- provenance portability: **Diagnostic**;
- retrieval reproducibility: `insufficient_evidence` for both tracked domains.

### Battery v2.6

- Ridge forecast improvement: **Unsupported**;
- persistence remains the stronger registered warm-start baseline;
- cross-cohort comparability: `not_established`;
- external cohort admission: `not_admitted`;
- predictive-validation readiness: `not_ready`;
- provider-to-local binding: `not_established`;
- engineering-decision readiness: `not_ready`;
- final evidence-line scientific status: **Inconclusive**.

### Post-v2.6 process-characterization work

- checksum, schema, provenance, and exact sample-ID integration are software-
  validated;
- DWCNT, RWGS, four-carbon-material, and NIST cases remain **Diagnostic**;
- blocked modalities and unresolved source context remain preserved;
- NIST's three coupled conditions remain
  `not_ready_for_predictive_or_causal_modeling`;
- no response model or process optimum is produced.

## Promotion status

Completed in the tracked promotion:

1. a complete v2.7.0 changelog section covers all stages and post-v2.6 scope;
2. `docs/releases/V2_7_0.md` preserves positive, negative, restricted, blocked,
   Diagnostic, Inconclusive, and Unsupported outcomes;
3. public, runtime, and citation versions are aligned to `2.7.0` with release
   date `2026-07-28`;
4. the v2.5 and v2.6 roadmaps record release within v2.7.0 while preserving the
   v2.6.14 line-closeout boundary;
5. the deterministic promotion audit, complete CI, v2.6.14 validator,
   representative NIST execution, and pinned cross-repository audit are required
   on the merge context.

Remaining external action:

- create or verify a reviewed v2.7.0 Git tag and GitHub Release only after all
  promotion workflows pass.

## Scientific boundary

Release readiness is software and provenance governance. It does not establish
source truth, instrument calibration, sample comparability, causal effects,
mechanisms, predictive generalization, optimization readiness, or engineering-
release suitability.
