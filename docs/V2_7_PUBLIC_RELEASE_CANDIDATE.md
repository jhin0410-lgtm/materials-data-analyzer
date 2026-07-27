# v2.7.0 Public Release Candidate

## Corrected decision

The next stable public version is **v2.7.0**.

The previously selected v2.6.0 candidate is superseded. The reason is not
cosmetic numbering: the tracked v2.6.14 closeout explicitly states that the
v2.6 evidence line is closed, that no automatic v2.6.15 stage is authorized,
and that the next useful work must be a separate end-to-end case study or a
reopening supported by materially new evidence.

After that closeout, 38 commits added a distinct integration and public-
repository scope, including generic characterization handoff, pinned public
producer-consumer workflows, the NIST representative process-characterization
workflow, repository hardening, citation governance, and release-readiness
audits. Treating those changes as v2.6.0 would erase the repository's own line-
closeout boundary.

This candidate selects version and scope only. It does not yet change
`PUBLIC_RELEASE_VERSION`, runtime `PLATFORM_VERSION`, `CITATION.cff`, the root
changelog, or any external Git tag or release.

## Complete included history

The release candidate must include every internal stage below. None is a
separate public release:

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

Any release note or changelog that names only v2.6.1-v2.6.2 is incomplete and
must fail review.

## Post-v2.6 release scope

The new minor-release boundary additionally includes:

1. public repository hardening, license, security, contribution, citation, and
   release-governance files;
2. schema `1.0` checksum-bound characterization bundle consumption;
3. explicit sample-context and external process-table identity gates;
4. pinned DWCNT, RWGS, four-carbon-material, and NIST AM-Bench
   cross-repository workflows;
5. the representative NIST process-characterization workflow;
6. process-design identifiability and one-to-one condition identity checks;
7. bounded minimum design augmentation;
8. official NIST commanded-to-actual power and laser-spot-size provenance;
9. offline cross-repository release-readiness auditing.

The v2.6 core closeout commit is:

```text
50e3ee1201ef791b250558a30c373848d615f815
```

The audited repository boundary before this correction is:

```text
ed5eac38584a174edbb9216aca10fc8232cdb504
```

The audited boundary is 38 commits ahead of the v2.6 core closeout.

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
- NIST's three coupled conditions are
  `not_ready_for_predictive_or_causal_modeling`;
- no response model or process optimum is produced.

## Why the earlier v2.7 PR was rejected

The earlier PR correctly recognized the v2.7 semantic boundary but its
changelog and release notes described only through v2.6.2. It omitted the
tracked v2.6.3-v2.6.14 comparability, admission, source-binding, bounded-read,
provider-access, and checksum-closeout chain. It was therefore closed without
merge.

## Promotion requirements

1. create a complete v2.7.0 changelog section covering all stages listed above
   and the post-v2.6 integration scope;
2. add `docs/releases/V2_7_0.md` with all positive, negative, restricted,
   blocked, Diagnostic, Inconclusive, and Unsupported outcomes;
3. update `PUBLIC_RELEASE_VERSION`, `PLATFORM_VERSION`, and `CITATION.cff`
   together to `2.7.0`, including `date-released`;
4. update the v2.5 and v2.6 roadmaps to show that their internal stages are
   released within v2.7.0 while preserving the v2.6.14 line-closeout boundary;
5. rerun complete CI, the v2.6.14 validator, representative NIST workflows, and
   the pinned cross-repository release-readiness audit;
6. create or verify external tags/releases only after the promotion commit is
   reviewed.

## Scientific boundary

Release readiness is software and provenance governance. It does not establish
source truth, instrument calibration, sample comparability, causal effects,
mechanisms, predictive generalization, optimization readiness, or engineering-
release suitability.
