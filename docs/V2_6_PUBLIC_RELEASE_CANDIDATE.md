# v2.6.0 Public Release Promotion Closeout

## Decision

The selected stable public version is **v2.6.0**.

A separate v2.5.0 public release is not justified. v2.5.1 and v2.5.2 were
completed internal feature stages, but no v2.5 public release boundary was
created before the v2.6 line was implemented and closed. Their compatibility and
retrieval-reproducibility evidence is therefore included in v2.6.0.

The tracked promotion updates `PUBLIC_RELEASE_VERSION`, runtime
`PLATFORM_VERSION`, `CITATION.cff`, `CHANGELOG.md`, the v2.5 and v2.6 roadmaps,
and `docs/releases/V2_6_0.md` together. The offline closeout does not create a
Git tag or GitHub Release.

## Audited scope

The release includes:

1. v2.5.1 explicit historical compatibility adapters;
2. v2.5.2 retrieval-reproducibility evidence audit;
3. v2.6.1 leakage-safe warm-start Battery forecasting benchmark;
4. v2.6.2 deterministic forecast-failure diagnostics;
5. v2.6.3 comparability evidence package;
6. v2.6.4 external-cohort admission gate;
7. v2.6.5-v2.6.10 bounded SNL LFP source, artifact, schema, regime, and
   transition-evidence work;
8. v2.6.11-v2.6.13 next-source selection and Michigan Formation provider-access
   closeout;
9. v2.6.14 checksum-bound evidence-line closeout;
10. public-repository hardening and explicit release/citation governance;
11. generic checksum-bound characterization-bundle consumption;
12. pinned DWCNT, RWGS, four-carbon-material, and NIST AM-Bench
    cross-repository workflows;
13. the representative NIST process-characterization workflow, identifiability
    audit, bounded design augmentation, and process-metadata provenance.

The v2.6 core evidence line was closed at commit:

```text
50e3ee1201ef791b250558a30c373848d615f815
```

The integrated release-candidate audit was based on `main` commit:

```text
8edd4b79c35f5aa5d0f85a5e03fbb918e0c09c5d
```

The integrated candidate includes the reviewed public and cross-repository work
on top of the v2.6 core closeout rather than silently omitting it.

## Preserved results

### v2.5

- software compatibility verdict: **Supported**;
- Materials v2.2.4 adapter: `compatible_with_restrictions`;
- Battery v2.3.5 adapter: `partial`;
- provenance portability: **Diagnostic**;
- retrieval reproducibility: `insufficient_evidence` for both tracked domains.

### Battery v2.6

- Ridge generalization: **Unsupported**;
- persistence remains the stronger registered warm-start baseline;
- cross-cohort comparability: `not_established`;
- external-cohort admission: `not_admitted`;
- predictive-validation readiness: `not_ready`;
- engineering-decision readiness: `not_ready`;
- evidence-line integrity: `verified`;
- final scientific closeout: **Inconclusive**.

### NIST process-characterization workflow

- exact source and sample-identity integration is software-validated;
- the three-condition process design is **Diagnostic**;
- causal effects, interaction, curvature, prediction, and optimization remain
  unsupported;
- the minimum next design is a bounded recommendation, not an engineering
  release decision.

## Why v2.5.0 is rejected

Publishing v2.5.0 from the integrated repository would require reverting the
completed v2.6 implementation or maintaining an older separate release line.
Neither action provides scientific or software value. v2.6 is explicitly closed
by a 13-stage checksum-bound artifact chain, so v2.6.0 is the smallest truthful
stable version.

## Promotion status

Completed in the promotion candidate:

1. v2.5.1-v2.5.2 and v2.6.1-v2.6.14 are represented in the `v2.6.0`
   changelog and release notes;
2. `docs/releases/V2_6_0.md` preserves Supported, Diagnostic, Inconclusive, and
   Unsupported outcomes;
3. public, runtime, and citation versions are aligned to `2.6.0` with a release
   date;
4. the v2.5 and v2.6 roadmaps record `released_as_v2.6.0`;
5. the deterministic promotion audit, v2.6.14 validator, complete CI, and pinned
   cross-repository audit are required on the merge context.

Remaining external action:

- create or verify a reviewed v2.6.0 Git tag and GitHub Release only after the
  promotion commit passes all workflows.

## Scientific boundary

Release readiness is software and provenance governance. It does not establish
sample comparability, source truth, causal identification, mechanism validity,
predictive generalization, optimization readiness, or engineering-release
suitability.
