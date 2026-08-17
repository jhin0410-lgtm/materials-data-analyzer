# Autonomous public research-data acquisition

## Purpose

The research agent should select a scientifically relevant source candidate. It should not require a human to rediscover file URLs, approve every public download, or manually calculate checksums.

This layer therefore converts a machine-actionable research-frontier candidate into a bounded acquisition run:

`frontier candidate -> source adapter -> authoritative metadata -> AUTO/REVIEW_REQUIRED/BLOCKED -> exact download -> SHA-256/size verification -> acquisition-record binding -> downstream scientific intake`

Acquisition is not scientific promotion. A successfully downloaded file remains `requires_scientific_intake=true` and `scientific_status_changed=false` until source identity, process semantics, machine/calibration compatibility, replication structure, measurement meaning, and other domain requirements pass the downstream scientific contracts.

## Human intervention policy

Human approval is exception-only.

### AUTO

A file can run without per-file human approval only when the adapter produces a candidate that is:

- publicly accessible;
- HTTPS only and restricted to the adapter's exact host allowlist;
- authentication-free;
- free of interactive click-through acceptance;
- not known to prohibit automated access;
- covered by a public-repository or explicit-open-license access classification;
- bound to authoritative metadata bytes;
- supplied with an expected SHA-256 and exact size;
- within the configured per-artifact and batch byte budgets.

The downloaded bytes must exactly match both size and SHA-256. Redirects outside the declared host allowlist fail closed.

### REVIEW_REQUIRED

A candidate is not executed automatically when, for example:

- login or authentication is required;
- an interactive license/terms acceptance is required;
- public accessibility or rights are uncertain;
- the per-file automatic download budget is exceeded;
- the cumulative batch automatic download budget is exceeded.

These cases are returned as an exception queue. They are not silently bypassed.

### BLOCKED

A candidate is blocked when automated access is explicitly prohibited or the declared rights are restricted. The acquisition layer does not bypass these restrictions.

## NIST PDR adapter

The first concrete source adapter is NIST PDR/NERDm. It consumes the machine-readable product metadata endpoint and only admits components explicitly typed as downloadable data files with:

- `filepath`;
- `downloadURL`;
- `size`;
- SHA-256 checksum metadata.

The adapter preserves NIST PDR as the recorded source system and binds the exact metadata bytes into every acquisition package.

## IN625 mds2-2923 first execution target

`configs/research/in625_external_physical_source_frontier.v1.json` now declares a machine-actionable plan for:

`nist-mds2-2923-cross-sectional-micrographs`

The initial automatic file set is deliberately narrow:

- `2923_README.txt`;
- `Master_TrackList_Measurements.xlsx`.

Raw micrographs are not bulk-downloaded yet. The workbook must first establish the authoritative row/image identity mapping so that later image acquisition is targeted by provenance rather than filename inference.

The acquisition plan does **not** make mds2-2923 eligible for Issue #76. Machine identity, programmed versus calibrated power semantics, spot diameter, track identity, and repeated-measurement structure still have to be audited after the exact workbook bytes are obtained.

## CLI

After installation, the planner-selected candidate can be executed with:

```text
mda-public-acquisition \
  --frontier configs/research/in625_external_physical_source_frontier.v1.json \
  --candidate-id nist-mds2-2923-cross-sectional-micrographs \
  --output-root outputs/public_acquisition/mds2-2923
```

The operator does not provide a workbook URL or checksum. The frontier selects the source/product/files, and the NIST adapter resolves authoritative URLs, sizes, and SHA-256 values from NERDm metadata.

Default automatic byte ceilings are 2 GiB per artifact and 4 GiB per batch. These defaults are safety/cost controls, not scientific thresholds.

## Current boundary

This implementation automates **acquisition**, not unrestricted web crawling and not scientific truth.

A future discovery layer can add machine-actionable candidates from other authoritative providers (for example institutional repositories or general research repositories) by producing the same generic acquisition-candidate contract. Source-specific adapters must still state access/rights semantics and authoritative integrity metadata rather than treating an arbitrary search result URL as trusted evidence.

The next research-loop integration is to let evidence-gap planning select a frontier candidate automatically and consume the resulting verified acquisition receipt as the next action, followed by source-specific scientific intake and cross-source analysis.
