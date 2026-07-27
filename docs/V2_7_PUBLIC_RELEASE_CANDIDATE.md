# v2.7.0 Public Release Promotion Closeout

## Decision

The selected stable public version is **v2.7.0** and the tracked release metadata
has been promoted. The previous v2.6.0 candidate remains superseded because the
v2.6.14 evidence-line closeout explicitly ended the internal v2.6 line and
prohibited an automatic v2.6.15 stage.

This closeout changes repository release metadata only. It does not create a Git
tag or GitHub Release, publish a package, rerun a scientific model, change a
metric, or access external data.

## Complete included history

The public release includes all internal stages below. None is a separate public
release:

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

The release also includes the distinct post-v2.6 scope added after the line
closeout:

1. public repository hardening, license, security, contribution, citation, and
   release-governance files;
2. schema `1.0` checksum-bound characterization bundle consumption;
3. explicit sample-context and external process-table identity gates;
4. pinned DWCNT, RWGS, four-carbon-material, and NIST AM-Bench workflows;
5. the representative NIST process-characterization workflow;
6. process-design identifiability and one-to-one condition identity checks;
7. bounded minimum design augmentation;
8. official NIST commanded-to-actual power and spot-size provenance;
9. offline cross-repository release-readiness auditing.

## Promoted metadata

The following tracked sources agree on `2.7.0`:

- `PUBLIC_RELEASE_VERSION`;
- runtime `PLATFORM_VERSION`;
- `CITATION.cff` with `date-released: 2026-07-28`;
- `CHANGELOG.md`;
- `docs/releases/V2_7_0.md`;
- `docs/PUBLIC_RELEASE_STATUS.md`.

The root `Unreleased` section is empty at the reviewed promotion boundary.

## Preserved scientific outcomes

### v2.5

- software compatibility verdict: **Supported**;
- Materials adapter: `compatible_with_restrictions`;
- Battery adapter: `partial`;
- provenance portability: **Diagnostic**;
- retrieval reproducibility: `insufficient_evidence`.

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

- checksum, schema, provenance, and exact sample-ID integration are
  software-validated;
- DWCNT, RWGS, four-carbon-material, and NIST cases remain **Diagnostic**;
- blocked modalities and unresolved source context remain preserved;
- NIST remains `not_ready_for_predictive_or_causal_modeling`;
- no response model or process optimum is produced.

## Required validation

Promotion is complete only after all of the following pass on the promotion
merge context:

1. complete repository CI;
2. public release metadata consistency tests;
3. this v2.7 promotion audit and checksum manifest;
4. the v2.6.14 tracked closeout validator;
5. the representative NIST workflow;
6. NIST process-design and minimum-design workflows;
7. pinned cross-repository release-readiness audit against characterization
   commit `7242594f775b8dbe651a6131bb1b39b5f60c62cd`.

## External release action

`public_metadata_promotion_performed` is true. `tag_or_release_created` remains
false. A Git tag or GitHub Release must be created or verified separately against
the reviewed promotion commit after all required workflows pass.

## Scientific boundary

Release metadata consistency and passing tests do not establish source truth,
instrument calibration, measurement uncertainty, sample comparability, causal
effects, mechanisms, predictive generalization, optimization readiness, or
engineering-release suitability.
