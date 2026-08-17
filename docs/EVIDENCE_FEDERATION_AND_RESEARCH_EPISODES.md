# Evidence federation and persistent research episodes

The research loop may use heterogeneous evidence without pretending that all evidence has
the same scientific strength.

## Evidence classes

- `E0_raw_experimental`: authoritative raw experimental bytes/signals/images.
- `E1_processed_experimental`: authoritative row-level processed measurements.
- `E2_publication_supplement`: publication-linked supplementary tables/files.
- `E3_paper_table`: values reported directly in a paper table.
- `E4_figure_digitized`: quantitative values reconstructed from a figure.
- `E5_literature_claim`: qualitative or narrative literature evidence.
- `E6_computational`: DFT/CALPHAD/MD/phase-field/FEM or other computational evidence.
- `E7_reference_context`: standards, reference data, calibration documentation, or context.

The class is not a trust score. Each candidate also records source authority,
representation, sample/acquisition identity, calibration, independence, comparability,
reuse status, and extraction route. A candidate record never changes scientific status.
Even an E0 candidate must pass the existing scientific-intake and epistemic gates.
Unknown source authority, unknown calibration for measurement-class evidence, unresolved
comparability, and missing exact sample/acquisition identity keep stronger uses blocked.

A discovery or catalog hit is not scientific evidence. Paper values, digitized figures,
computational results, and standards are not silently pooled with raw measurements.

## Persistent research episodes

`mda-research-episode` stores a canonical-JSON, SHA-256-bound control-plane checkpoint.
It records exact planner-record hashes, artifact/evidence references, unresolved gaps,
review queue, blockers, budgets, and a terminal conclusion when one exists. It does not
copy or reinterpret the underlying scientific artifacts. Each new iteration records the
SHA-256 of the prior validated episode state so resumed history is tamper-evident.

Create an episode:

```bash
mda-research-episode init \
  --episode outputs/in625_episode.json \
  --episode-id in625-evidence-federation \
  --question "What trustworthy evidence can resolve the current IN625 gap?" \
  --mission-id in625-autonomous-research \
  --objective "find independent evidence" \
  --objective "preserve provenance" \
  --max-iterations 20 \
  --cost-budget 100
```

Verify and resume the exact checkpoint:

```bash
mda-research-episode show --episode outputs/in625_episode.json
```

Record one planner iteration by hash-binding its exact JSON:

```bash
mda-research-episode record \
  --episode outputs/in625_episode.json \
  --planner-record outputs/planner_record.json \
  --artifact-ref discovery:sha256:<digest> \
  --evidence-ref federated-evidence:<id> \
  --gap "exact external replication remains unavailable" \
  --episode-status blocked
```

Checkpoint tampering, budget overruns, non-contiguous history, and appending to terminal
episodes fail closed. Persistence is a resumability mechanism, not a second planner or a
scientific-approval mechanism.

## Exact-SHA human scientific review

Fail-closed evidence needs a standard path for a reviewer to release the human-review
blocker after inspecting exact bytes and semantics. `mda-scientific-review` creates that
path without converting review into scientific support.

A review request binds all of the following:

- federated evidence candidate ID;
- evidence artifact SHA-256;
- semantic-contract SHA-256;
- experimental-lineage SHA-256;
- optional scientific-intake artifact SHA-256;
- the exact downstream uses being requested.

Prepare a request:

```bash
mda-scientific-review prepare \
  --candidate-id federated-evidence:<id> \
  --evidence-sha256 <sha256> \
  --semantic-contract-sha256 <sha256> \
  --lineage-sha256 <sha256> \
  --requested-use scientific_intake \
  --requested-use descriptive_analysis \
  --output outputs/review_request.json
```

Record a reviewer decision:

```bash
mda-scientific-review decide \
  --request outputs/review_request.json \
  --reviewer-id reviewer-1 \
  --decision approved \
  --allow-use scientific_intake \
  --exclude-use descriptive_analysis \
  --notes "Exact bytes, declared semantics, and lineage reviewed." \
  --output outputs/review_decision.json
```

Before downstream use, verify the decision against the *current* exact bytes and
contracts. A changed evidence, semantic, lineage, or intake SHA invalidates the prior
release.

```bash
mda-scientific-review verify \
  --request outputs/review_request.json \
  --decision outputs/review_decision.json \
  --candidate-id federated-evidence:<id> \
  --evidence-sha256 <sha256> \
  --semantic-contract-sha256 <sha256> \
  --lineage-sha256 <sha256> \
  --downstream-use scientific_intake
```

An approved release means only that the exact human-review requirement has been
satisfied for the exact requested use. It does **not** establish comparability,
independence, calibration, hypothesis support, external validation, model validity, or
engineering readiness.

## Experimental lineage and pseudoreplication

`ObservationLineage` explicitly separates:

```text
source / lab
  -> material lot
  -> build or synthesis
  -> specimen
  -> process run
  -> acquisition
  -> measurement
  -> derived feature
```

Different rows are therefore not assumed to be independent replicates. The strongest
supported relationship is classified as one of:

- same measurement;
- different measurements from the same acquisition;
- different acquisitions from the same specimen;
- independent specimens from the same build/synthesis;
- independent builds/syntheses from the same material lot;
- independent material lots from the same source/lab;
- independent external sources;
- unresolved when required lineage is absent.

External-source independence is established only when source, lab, material lot, and
build/synthesis are all explicitly distinct. Missing identifiers are reported as
unresolved rather than inferred. `effective_independent_unit()` exposes row count next to
measurement, acquisition, specimen, build, lot, source, and lab counts so technical
repeats cannot silently inflate the effective sample size.
