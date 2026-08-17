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

The class is not a trust score.  Each candidate also records source authority,
representation, sample/acquisition identity, calibration, independence, comparability,
reuse status, and extraction route.  A candidate record never changes scientific status.
Even an E0 candidate must pass the existing scientific-intake and epistemic gates.

A discovery or catalog hit is not scientific evidence.  Paper values, digitized figures,
computational results, and standards are not silently pooled with raw measurements.

## Persistent research episodes

`mda-research-episode` stores a canonical-JSON, SHA-256-bound control-plane checkpoint.
It records exact planner-record hashes, artifact/evidence references, unresolved gaps,
review queue, blockers, budgets, and a terminal conclusion when one exists.  It does not
copy or reinterpret the underlying scientific artifacts.

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
episodes fail closed.  Persistence is a resumability mechanism, not a second planner or a
scientific-approval mechanism.
