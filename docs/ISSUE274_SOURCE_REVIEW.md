# Issue #274 source review (2026-11-04 KST)

This review separates source observations, parser differences, interpretations,
and authorization to change an evidence contract. The original v1 witness and
all authority checks remain unchanged. No new witness is accepted by this work.

## Lane PDF: bounded conclusion, not global text equivalence

The retained 17-page PDF is still SHA-256
`39de5e6987461c3cf607e544d202cfdc3f28dffd2e0ec298175df63803b99640`.
Both real parser versions were run on those exact bytes. The old parser was run
offline, read-only and resource-limited against trusted, hash-verified input.

For `lane-cross-section-uncertainty-exists`, second match on page index 15:

| Item | 6.18.1 | 6.21.4 |
|---|---|---|
| Matched UTF-8 bytes | 576 | 574 |
| Squared combined-uncertainty fragment | `u2 c (w)` | `u2c (w)` |
| Squared component-uncertainty fragment | `u2 i (w)` | `u2i (w)` |

Only ASCII spaces at original offsets 47 and 72 differ in this span. Numeric
tokens and non-whitespace characters in the span are identical. The publisher's
[NIST-hosted PDF](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=927485),
page 16, equation (13), independently identifies the combined squared uncertainty
as a sum of squared component uncertainties. The squares and subscripts retain
that meaning; no value, sign, unit or physical assertion was added or removed
by these two spacing changes. Surrounding text explicitly provides preliminary
width/depth uncertainty budgets. This supports the narrow claim that such an
analysis exists, not transfer of uncertainty values to other measurements.

Both pypdf strings flatten superscript/subscript layout and retain an unresolved
summation glyph name. Neither flattened string is authorized as executable math
or quantitative equation evidence. PDF-image visual review was not performed;
the source context was checked with the independent PDF text view. In particular,
the source distinguishes exemplar cooling-rate data from reference data; this
review does not promote those data or measurement authority.

The **whole PDF has more differences than the reported two-space claim**:
normalized text changes on page indices 6, 8, 12, 13, 14 and 15, in 48 edit
regions. These include `/u1D700` to mathematical epsilon and `/u1D715` to a
partial-derivative character, as well as spacing. For diagnostic comparison only,
after interpreting those two explicit glyph names, every page's non-whitespace
character stream and numeric-token sequence matches. This is not a production
normalizer and does not authorize global equation/layout equivalence.

The small versioned span fixture records the actual old/new outputs. Its old
hash is bound to the unchanged v1 witness. Tests prove the precise edit and
that v1 still **rejects** the 6.21.4 span despite this limited source review.

## Weaver: original not recovered; current metadata independently inspected

Historical original: 82,486 bytes, SHA-256
`8bdc0f69eeeba587386a8779823896a4700ad7725da6f1625ecbc1de7907c879`.
No copy with that identity was recovered in the checked local/Git sources.
The successful historical Actions run `35328457736` currently lists no artifacts.

Internet Archive CDX was queried for the exact official URL before the witness's
2026-09-18 commit. No capture was found in September 1–18. The latest listed
2026 capture before that date was 2026-01-21 05:55:50 UTC. Its unrewritten payload
was retrieved and its SHA-1 matched the archive's CDX digest. It is **not** the
original reviewed HTML: 81,340 bytes, SHA-256
`da13f415c9915f67e23ed41e32504de47e4bff1e1671abcdb5fc60b0c8715c1c`.
Its old broad anchor also does not reproduce the v1 claim digest. A tested
navigation-label reconstruction hypothesis failed the immutable witness hash
and was rejected. This is a bounded recovery failure, not proof that no backup
exists anywhere.

The [official NIST record](https://www.nist.gov/publications/laser-spot-size-and-scaling-laws-laser-beam-additive-manufacturing)
was retrieved once and checked independently of the producer's broad anchor.
Its title/authors/DOI identify Weaver, Heigel and Lane's publication,
DOI `10.1016/j.jmapro.2021.10.053`. The archived and current **abstract sections**
are exactly equal (1,229 characters after the same HTML text extraction).
Both explicitly describe deliberate D4-sigma spot-diameter variation from
50 to 322 micrometres. Thus the currently accessible official metadata supports
that narrow experiment-family claim. It does not establish per-row calibration,
cross-machine equivalence or model validity.

The current HTML is 82,601 bytes with SHA-256
`17692f3d18c20bd0067af0f82f400f3e8bc4ccd3a1b8091735d0bf76a55770d3`.
Its v1 anchor still yields the CI's 3,193-byte span/digest, despite a different
raw page digest from the earlier CI capture. The broad anchor starts at the
page title and includes government/site navigation before reaching the abstract.
These implementation facts explain fragility; they do not justify removing
navigation from v1's comparison or assuming its 3,198-byte span was equivalent.

| Claim receipt | Historical v1 | Retained CI and current |
|---|---|---|
| Matched UTF-8 bytes | 3,198 | 3,193 |
| SHA-256 | `c1a803c1cd216e88dd9b6e16f5296ec2fbab28703b194e7046d27c7d662b22cf` | `61cec31e64ee053bc686690c033a328c272044e5d1557abb58ae839f19620e7a` |

The HTML claim difference occurs with both pypdf versions; HTML extraction does
not call pypdf. The raw historical/current HTML identity differs, establishing
external page drift. Without the old bytes, the exact historical character
edits and whether they affected only navigation cannot be determined. The
unchanged broad title-to-abstract anchor is a pre-existing source-scoping
fragility, not evidence that the security update caused this HTML mismatch.

Exact historical body recovery and v1-to-current scientific text equivalence
remain UNKNOWN. The January/current abstract equality cannot fill the missing
September capture. Publisher full-text access returned 403; PMC browser access
requested a browser check and the public full-text XML retrieval attempts
returned 500. Those bodies were not reviewed and access restrictions were not
bypassed. Independent expert approval has not been obtained.

## Contract disposition

A separately versioned current contract is necessary if live verification is to
consume 6.21.4 output and newly reviewed source bytes. Updating four hashes in
v1 is not sufficient. `evidence/in625_multisource_review.v2.proposal.json` records
the review scope, provenance, facts and outstanding acceptance requirements.
It has `activation_authorized: false` and is **not** a runtime witness.

Before activation, independently review the new sources/scope, retain their
exact bytes and parser identity, and prove version-specific positive acceptance
and rejection of changed sources, parser identity and units. Preserve v1 and
historical isolation. In particular, a new abstract-only claim must be a new
reviewed scope rather than an implicit relaxation of the old navigation-spanning
claim. No active dispatcher, verifier constant or witness was changed here.
Live Replay must remain unresolved pending that review.

## Separate HTTP 429 failure and minimal transport change

Comparator run [41776526037](https://github.com/jhin0410-lgtm/materials-data-analyzer/actions/runs/41776526037),
job `126398080094`, failed on the **first metadata fetch** at
`https://mediatum.ub.tum.de/node?id=1473265`. It never requested the thesis PDF or
called pypdf. A provider's HTTP 429 response is confirmed; its quota algorithm,
shared-IP effects and original Retry-After header are unknown from the old log.
No fresh requests were sent to that rate-limited institution during this review.

The minimum implemented change preserves valid Retry-After delay-seconds or
HTTP-date as structured deferral information and a safe diagnostic. The error
remains a subtype of the existing operational exception and preserves its cause.
The throttling response is closed without consuming it as evidence. There is no
automatic retry, sleep, alternate URL, changed identity, cached error response,
or widened request budget. Invalid/missing headers do not become zero-delay
permission; unrepresentably long delays are not shortened.

[RFC 6585 section 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)
defines 429 and optional Retry-After;
[RFC 9110 section 10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)
defines the two header forms. Acquisition can resume only as a later authorized
attempt after the server's minimum delay. A scheduler must separately enforce
that deadline across workflow reruns. If recurring runs are parallel, serialize
this institution's acquisitions rather than increasing traffic. No global
scheduler/cache was implemented, no provider threshold was guessed, and successful
live acquisition has not been demonstrated by offline transport tests.
