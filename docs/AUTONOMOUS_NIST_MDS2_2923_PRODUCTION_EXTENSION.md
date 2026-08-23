# Autonomous NIST mds2-2923 Production Extension

Issue: #218

This extension advances the public `mda-research-program run-autonomous` path from the reviewed IN625 physical-comparability gate into exact NIST PDR `mds2-2923` acquisition and source-specific scientific intake.

## Evidence-source scope remains multi-source

The production mission is **not NIST-only**. Eligible evidence classes remain:

- authoritative datasets and repositories;
- papers and supplementary materials;
- official technical reports;
- official documentation, including calibration/metrology documentation;
- characterization evidence;
- other provenance-verifiable real physical evidence.

Each source class must enter through a source-specific trust and scientific-intake boundary. A literature statement is not silently promoted to row-level measurement authority, while an authoritative row-level dataset is not assumed to establish condition equivalence merely because the nominal material matches.

## Current production path

1. Live Zenodo 20503603 acquisition and exact archive checksum verification.
2. Machine-authored typed IN625 registration.
3. Reviewed 200,289-row tensile intake with the one observed blank preserved.
4. Physical-comparability gate rejecting direct tensile-to-melt-pool numerical validation.
5. Exact NIST `mds2-2923` metadata + README + workbook acquisition under a separate mission-pinned standing policy.
6. Existing source-specific NIST intake over the exact bytes.
7. Re-diagnosis to `geometry_condition_mapping_not_established`.
8. Next bounded action: `reviewed_geometry_condition_mapping_assessment`.

## NIST scientific boundary

The expected current NIST evidence state is 178 IN625 measurement rows representing 106 dataset-local physical-track identities. AMMT contributes 34 rows / 34 tracks; EOS M270 contributes 144 rows / 72 tracks. The `Data` sheet remains row-level authority and `Summary` remains an audited derived representation.

Laser power is preserved as a machine setting as stated by the NIST README. No programmed-to-calibrated power conversion is inferred, no cross-machine pooling is authorized, and Issue #76 remains 0/3 unless separate evidence establishes the required calibrated AMMT conditions.

The NIST source establishes response-compatible melt-pool width/depth evidence. It does **not** by itself establish direct target-condition comparability. Papers, supplementary material, official calibration/metrology documentation, additional datasets, and characterization evidence may be used in the next condition-mapping assessment to establish or refute those mappings.

## Network authority

The autonomous NIST capability is intentionally narrower than the repository's generic public-acquisition infrastructure. The mission-pinned policy fixes:

- candidate: `nist-mds2-2923-cross-sectional-micrographs`;
- product: `mds2-2923`;
- metadata endpoint: `https://data.nist.gov/od/id/mds2-2923`;
- exact README/workbook file names, SHA-256 digests, and byte sizes;
- metadata host `data.nist.gov`;
- artifact hosts `data.nist.gov` and NIST's exact OAR cache host;
- three-request and byte ceilings;
- no unrestricted search or caller-authored URLs/file queues.

Policy re-pinning alone cannot widen these identities because the production verifier independently duplicates the finite source/host/file contract.

## Completion criterion for #218

#218 is complete only after the literal public command runs the real Zenodo and NIST path and the latest full Ubuntu/Windows CI, Quality, autonomous acceptance, and public recursive checks are green. Network/parser/checksum success is not empirical model validation or hypothesis truth.
