# Evidence Harvester

The Evidence Harvester broadens the search space when an exact raw independent dataset is
not available. It searches trusted machine-readable catalogs while preserving the fact
that a search result is **not** scientific evidence.

## Trusted catalog providers

Current adapters are deliberately source-specific:

- NIST RMM/PDR for authoritative NIST repository products;
- DataCite for persistent dataset DOI discovery and dataset/publication relations;
- Zenodo for published record and file discovery;
- Crossref for literature DOI and metadata discovery.

Provider response bytes are SHA-256 bound. Redirects remain on the exact trusted provider
host. A provider timeout, parser failure, or empty result is not negative scientific
evidence and does not stop the other providers from being searched.

Catalog identities are deduplicated primarily by DOI. Deduplication means that multiple
catalogs point to the same persistent object; it does **not** establish scientific-source,
lab, sample, build, or acquisition independence.

## Zenodo content acquisition

Published Zenodo content uses a dedicated adapter rather than weakening the existing NIST
SHA-256 acquisition contract. Zenodo commonly declares file content checksums as MD5.
The adapter therefore:

1. preserves the source checksum algorithm and digest exactly;
2. verifies an MD5 as MD5 (or a source SHA-256 as SHA-256);
3. computes a separate local SHA-256 after transfer;
4. records both in the acquisition manifest.

A source MD5 is never renamed or represented as SHA-256.

Automatic acquisition requires explicit public record/files access, an automatically
accepted open-license identifier, a supported source checksum, an exact Zenodo HTTPS file
URL, and configured file/batch byte budgets. Unknown licenses and licenses with use or
derivative restrictions are routed to review. Restricted/embargoed content is blocked.
These decisions authorize transfer only; they do not establish scientific validity.

## Safe archive inventory

Acquired ZIPs are inventoried without bulk extraction. The inventory rejects:

- path traversal;
- encrypted members;
- symlink members;
- duplicate normalized names;
- excessive member counts;
- excessive individual/total uncompressed size;
- unsafe compression ratios.

CSV/TXT/TSV/JSON/MD/DAT members are hashed only within explicit text-byte budgets.
File extensions are an inventory aid, not semantic validation.

## Independent LPBF IN625 publication episode

The tracked configuration
`configs/research/in625_zenodo_publication_dataset.v1.json` targets Zenodo record
`20503603` / DOI `10.5281/zenodo.20503603`, linked to the 2026 LPBF Inconel 625
build-orientation and heat-treatment publication.

Run:

```bash
python scripts/run_live_in625_zenodo_evidence.py \
  --config configs/research/in625_zenodo_publication_dataset.v1.json \
  --output outputs/live-in625-evidence
```

Possible terminal acquisition states include:

- `acquired_pending_semantic_lineage_and_review_intake`;
- `review_required_before_acquisition`;
- `network_or_provider_unavailable`;
- `content_network_unavailable`.

Network unavailability is explicitly not scientific negative evidence. When acquisition
succeeds, the ZIP becomes an `E2_publication_supplement` candidate only. Unknown sample
identity, acquisition identity, calibration, cross-source comparability, and human review
remain blockers until exact downstream contracts are available.

This independent episode is **not eligible for issue #76**. It must not be relabeled as
missing AMMT calibrated-actual-power Stage-1 traces.

The dedicated GitHub Actions workflow runs deterministic regressions before any live
network step and uploads compact JSON evidence records while excluding downloaded raw
content from workflow artifacts.
