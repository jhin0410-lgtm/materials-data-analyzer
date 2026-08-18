# Autonomous Research Scientist MVP Closeout

Status: **MVP architecture and live three-domain acceptance complete**

This document records the completion boundary for the provenance-aware autonomous research scientist track tracked by Issue #165. It is a software/system acceptance record, not a declaration that every represented scientific hypothesis has been verified.

## Completion criterion

The project required at least three materially different **real-data** research episodes to execute:

```text
question
-> evidence discovery/acquisition
-> scientific intake
-> analysis
-> weakness or contradiction detection
-> next-action selection
-> persisted reanalysis
-> bounded stop
```

without code modification for the individual episode, while preserving exact provenance and refusing unsupported scientific promotion.

PR #171 (`Prove the three-domain live real-data research MVP`) supplied the final live acceptance path and was merged to `main` as squash commit `b6767424d25ef64867156f046e7028c85886cbfe`.

## Live acceptance evidence

The final PR-head acceptance run was GitHub Actions run `32122590267` on head `3cb3da238a9285244c1a856f66c03eb85c838bce`.

Artifact:

- name: `live-three-domain-mvp-acceptance`
- artifact id: `9319184430`
- artifact digest: `sha256:015b9e7ed50921849a95c98996b64175004161e0f8fb219d931699ec13729879`

Acceptance assertions:

- episodes: 3
- valid episodes: 3
- completed full cycles: 3
- distinct episode families: 3
- distinct modalities: 3
- evidence classes: 2 (`E0_raw_experiment`, `E1_processed_experiment`)
- synthetic source count: 0
- false scientific promotion count: 0
- `weakness_to_action_to_reanalysis_bound=true`
- `future_followups_kept_separate_from_completed_reanalysis=true`
- scientific status changed by the acceptance layer: false
- execution authorized by the acceptance layer: false
- human scientific-review decision synthesized by the acceptance layer: false

The same PR head also passed:

- CI on Ubuntu and Windows, including installed-package smoke tests;
- Quality and Release Evidence;
- Autonomous Phase A-E acceptance;
- the dedicated live three-domain research MVP acceptance.

## Canonical live episodes

### 1. NASA PCoE Li-ion batteries — E0 raw experiment

The live path reacquires the official public archive, authenticates the retrieval receipt, re-hashes the archive bytes, imports the raw experiment files, and executes the battery intelligence pipeline.

Stable archive SHA-256 from the accepted run:

`82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e`

The episode detects target-comparability / battery-influence weaknesses and binds them to a persisted protocol-aware post-hoc audit. The signal-enriched Ridge result was worse than the capacity-only Ridge result in the accepted live run, so predictive evidence remained **Unsupported**. The negative result counts as a completed research cycle because the system audits the weakness and stops rather than manufacturing a positive claim.

### 2. Public DWCNT multimodal characterization — E1 processed experiment

The live path uses DOI `10.57745/7KA2UG` with the characterization producer pinned at commit `09a7e02b46924c44b9798ebab146281af50a28d7`.

It performs public-source acquisition and Raman/FTIR/XPS/TGA analysis, retains raw-source checksums and preprocessing identities, and binds the detected TGA candidate/startup-boundary weakness to a separately persisted candidate review.

The accepted live review reconciles two raw TGA candidates into one retained-review-required candidate and one rejected startup-boundary artifact. Cross-technique identical physical aliquot identity remains unestablished, and unsupported TEM quantitative segmentation is not promoted.

### 3. Public RWGS 5 wt% Cu/Al2O3 XRD/SEM/EDS — E1 processed experiment

The live path uses DOI `10.5281/zenodo.13474908` with the characterization producer pinned at commit `fb85c4eb3d57a209c70f0db1de40421158af2270`.

It executes public-source XRD/SEM/EDS diagnostic characterization and binds exact producer handoff bytes to an independent consumer validation. The episode preserves the SEM quantitative-segmentation method mismatch, unresolved EDS Ni, missing acquisition metadata, and non-identical-aliquot limitation.

Model training and scientific-metric recomputation remain forbidden in this handoff path.

## Sequence integrity

`src/materials_data_analyzer/research_loop/live_real_data_mvp_sequence.py` prevents an episode from passing merely because an iteration counter says two iterations occurred.

Every accepted canonical episode must bind the actual sequence:

```text
weakness evidence
-> recorded next-action decision SHA
-> persisted iteration-2 reanalysis artifact SHA
-> bounded stop
```

Post-stop recommendations are represented separately and must remain explicitly unexecuted in the completed episode.

The public entry point for evaluating already-produced canonical episode artifacts is:

```powershell
python scripts/run_live_real_data_mvp_acceptance.py `
  --nasa-raw <nasa-raw-directory> `
  --nasa-import <nasa-import-output> `
  --nasa-analysis <nasa-analysis-output> `
  --dwcnt-producer-result <dwcnt-producer-result.json> `
  --dwcnt-consumer-output <dwcnt-consumer-output> `
  --rwgs-producer-result <rwgs-producer-result.json> `
  --rwgs-producer-validation <rwgs-producer-validation> `
  --rwgs-consumer-output <rwgs-consumer-output> `
  --output <acceptance-output>
```

For a fully reproducible end-to-end live execution, use the repository workflow `.github/workflows/live-three-domain-mvp-acceptance.yml`, which performs the external acquisition/producer steps before invoking this acceptance entry point.

## Architecture now covered by the completion track

The completed track includes:

1. heterogeneous evidence federation with evidence-class separation;
2. trusted provider acquisition and exact-byte provenance;
3. persistent, tamper-evident `ResearchEpisode` checkpoint/resume state;
4. exact-SHA human scientific-review requests and scoped release verification;
5. sample/build/specimen/acquisition/measurement lineage and pseudoreplication controls;
6. benchmark gates for false promotion, provenance, abstention, independence, action quality, reproducibility, and cost behavior;
7. lineage-aware statistical eligibility and uncertainty-propagation boundaries;
8. bounded literature metadata/evidence adapters;
9. probabilistic EIG only when a separately validated SHA-bound probabilistic model permits it, otherwise structural proxies only;
10. a read-only research-operations surface with no second execution authority;
11. a single typed decision/persistence path that does not create a second planner, evidence graph, executor, or scientific promotion path.

## Scientific boundary

MVP completion means the autonomous **research control architecture** has passed the declared live real-data criterion. It does not mean:

- every hypothesis in the source datasets is true;
- Diagnostic or Unsupported evidence has been upgraded;
- missing calibration, aliquot, sample, or acquisition identity may be inferred;
- literature/search metadata is itself scientific evidence;
- simulation substitutes for physical measurements;
- the system may authorize physical hardware execution;
- a human scientific-review decision may be synthesized;
- adjacent evidence may satisfy an exact predeclared physical-data requirement.

## Remaining external physical-data issue

Issue #76 intentionally remains open and is **not** an MVP-completion blocker.

Its predeclared missing AMMT Stage-1 cells are:

- 137.9 W / 800 mm/s: at least 3 independently traceable valid traces;
- 137.9 W / 1200 mm/s: at least 3;
- 179.2 W / 400 mm/s: at least 3.

Each trace additionally requires authoritative achieved/calibrated power, machine/optics/calibration/software/material/specimen/acquisition provenance, checksums, and explicit process-characterization identity joins.

The official AM-Bench 2018-02 public experiment contains the complementary observed AMMT cells 137.9 W / 400 mm/s, 179.2 W / 800 mm/s, and 179.2 W / 1200 mm/s. The acquired NIST `mds2-2923` workbook is useful adjacent physical evidence but does not establish the three missing calibrated-actual-power AMMT cells. Cross-machine relabeling, interpolation, synthetic traces, target-as-achieved substitution, or model-generated records must not be used to close #76.

## Final project-level state

As of 2026-08-18:

- autonomous research scientist MVP architecture: **complete**;
- three materially different live real-data full-cycle acceptance: **passed**;
- project-level tracker #165: **completed**;
- exact NIST Stage-1 physical augmentation #76: **open, externally evidence-blocked**;
- scientific status of unresolved physical questions: unchanged.

Future development should therefore be treated as post-MVP capability expansion or new scientific campaigns, not as missing evidence for the closed #165 architecture criterion.
