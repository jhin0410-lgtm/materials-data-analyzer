# Unified safe-parser evidence design

## Inventory and boundaries

Inspected at base `43861e52210ed141cff9c4273c06360e8e445e03`.
The editable implementation is confined to branch
`refactor/unified-safe-pdf-evidence` in the separate `mda-unified-pdf` worktree.
The existing MDA development worktree, main, MCA and services are untouched.

| Executable PDF path | Existing behavior | Unified behavior |
|---|---|---|
| `in625_geometry_condition_source_acquisition._pdf_pages` | guarded direct reader | shared reader, same normalization |
| `nist_ammt_calibration_candidate_acquisition._pdf_pages` | guarded direct reader | shared reader, same normalization |
| `nist_mds2_2923_reference_chain_evidence._pdf_views` | guarded direct reader, plain/layout | shared reader, preserve both views |
| `in625_published_model_comparator._normalized_pdf_pages` | guarded direct reader, NFKC and dehyphenation | shared reader, preserve normalization |
| `scripts/recon_in625_geometry_condition_sources._pdf_pages` | independent direct reader | shared guarded reader |

The tree has no other production PDF parser imports or subprocess extractors.
Synthetic test PDFs remain test inputs, not research observations.

## Evidence model

1. Historical source hashes, claim receipts, parser provenance and results are
   immutable records. Reading them does not execute their recorded parser.
2. A new reprocessing report reads exact retained source bytes, checks the
   historical identity and parses them with the currently approved runtime.
   Missing originals are explicit incomplete evidence, never a successful replay.
3. Old/new claim receipts remain side by side. Equality is an extraction
   observation; a difference requires review and cannot replace the old receipt.
4. A separately pinned, versioned review contract describes source identity,
   claim scope, page/context and linked numeric values/units. A parser change
   requires contract review. Semantic checks complement exact byte identity;
   neither self-hashed reports nor arbitrary caller contracts grant authority.
5. Technical checks and completed scientific source review are separate fields.
   Pending/missing evidence cannot pass the authoritative completion gate.

The initial contract intentionally cannot approve the whole historical campaign:
the historical Weaver HTML is missing, and available source review is bounded.
Current Weaver metadata is a separate source observation, not a substitute for
the missing historical original. No claim of physical/model validation follows
from source-level review, even when an evidence contract is complete.

## Legacy disposition

Remove executable old-parser requirements, the baseline-wheel CI build and
the requirement to install 6.18.1 to read old provenance. Archive their exact
contract/test/requirements records under `docs/history/pdf-replay/` and preserve
Git history. Keep the network/read-only/resource sandbox and its preflight,
using the safe parser for reprocessing. Translate parser/network rejection
tests to the new runtime; retain immutable historical-witness rejection tests.

Do not delete existing environments or recovery directories in other worktrees.
After this branch is reviewed/adopted, those runtimes are unnecessary for the
new validation path, but their disposal is a separate operational action.

## Stages and validation

1. Commit this inventory/design before functional changes.
2. Consolidate all five parser paths and remove old-parser runtime dependencies.
3. Implement bounded, offline source reprocessing and a fail-closed review gate.
4. Test accepted fixtures, source/number/unit/context changes, missing originals,
   parser changes and preserved historical records; reprocess retained real
   evidence without fetching replacements.
5. Run targeted checks first, then one full candidate suite. Record CI sandbox
   validation separately from scientific source review and full live replay.
