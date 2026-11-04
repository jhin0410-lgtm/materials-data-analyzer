# PR #273 Actions diagnosis (2026-11-03 KST)

## Historical sandbox dependency failure

The push run [41584358995](https://github.com/jhin0410-lgtm/materials-data-analyzer/actions/runs/41584358995)
and PR run [41585015996](https://github.com/jhin0410-lgtm/materials-data-analyzer/actions/runs/41585015996)
failed with `prlimit: failed to execute bwrap: No such file or directory` (127).
The runner had prlimit but lacked bubblewrap. This was an environment setup
failure before the historical validation could run.

The quality workflow now explicitly installs bubblewrap on its disposable
Ubuntu runner, checks both executables, and probes the sandbox **before**
installing the historical parser. The stdlib-only probe rejects a shared host
network namespace, an external route, a writable source mount, or absent/excessive
address-space/CPU/file-descriptor limits. There is no fallback or host security
setting bypass. Existing historical execution limits remain unchanged.

Local checks: the workflow's exact preflight command succeeded; an unisolated
namespace and omitted resource limits were rejected. Targeted tests: 16 passed,
14 deselected. The real 6.18.1 historical suite: 12 passed under the original
read-only/network-isolated/resource-limited policy. Runner apt installation and
remote Actions reruns have not been executed by this local verification.

## Live Replay authority projection failure

Run [41585016197](https://github.com/jhin0410-lgtm/materials-data-analyzer/actions/runs/41585016197)
completed acquisition but failed result verification. Analysis used its retained
source bytes from artifact `13207622976`; no fresh external source acquisition
was performed. The ZIP SHA-256 was verified:

`92941a2f54e3da5466e53ebb30438ca2c52a522824a008f5455abdd8961e7ea2`.

Exactly four fields differ from the pinned witness (JSON pointers are zero-based):

| JSON pointer | Witness | CI result |
|---|---|---|
| `/sources/4/claims/4/matches/1/matched_text_sha256` | `89e4fba7148a813550309020f98b1c5613498824c6569f8bd30ac6797766886f` | `bde857eb1311accf47ad864786526e3b891f86221b68a9a1a2230b50ae65c328` |
| `/sources/4/claims/4/matches/1/matched_text_utf8_bytes` | 576 | 574 |
| `/sources/5/claims/0/matches/0/matched_text_sha256` | `c1a803c1cd216e88dd9b6e16f5296ec2fbab28703b194e7046d27c7d662b22cf` | `61cec31e64ee053bc686690c033a328c272044e5d1557abb58ae839f19620e7a` |
| `/sources/5/claims/0/matches/0/matched_text_utf8_bytes` | 3198 | 3193 |

### Parser-dependent PDF difference: confirmed

Source `lane-2020-melt-pool-geometry`, claim
`lane-cross-section-uncertainty-exists`, second match, page index 15:

- The PDF bytes still match the witness exactly: 1,874,330 bytes, SHA-256
  `39de5e6987461c3cf607e544d202cfdc3f28dffd2e0ec298175df63803b99640`.
- On the same bytes, 6.18.1 reproduces the witness's 576-byte claim span.
- 6.21.4 removes two ASCII spaces at original character offsets 47 and 72,
  yielding 574 bytes and the CI digest. This is a parser-dependent output
  difference, not a change to that PDF's external bytes.
- Reprocessing all eight retained sources with 6.21.4 reproduced every CI claim
  receipt. These whitespace observations do not authorize changing the exact
  historical contract or assuming scientific equivalence.

### HTML drift and main reproduction: confirmed

Source `weaver-2021-spot-size-scaling-metadata`, claim
`weaver-spot-size-range-abstract`:

- Witness raw HTML: 82,486 bytes, SHA-256
  `8bdc0f69eeeba587386a8779823896a4700ad7725da6f1625ecbc1de7907c879`.
- CI raw HTML: 82,601 bytes, SHA-256
  `db2262841ff6bf7b555cbecc5bb441c2eec35949061b3920a015f11a1171df73`.
- Both parser environments produce the same 3,193-byte HTML claim span from the
  CI bytes. pypdf is not used by this HTML extraction path.
- The unchanged main code at `257dcfb3e51602119eeddb6f7da2226d66771ca2`,
  with real 6.18.1, was exercised offline against the retained sources. After
  recomputing its receipts, the complete multisource witness verifier rejected
  the HTML with the same authority-projection error. Only the two HTML fields
  still differ from the witness in this main reconstruction.

Thus the live failure combines a PR parser-dependent PDF mismatch with an HTML
mismatch that also reproduces on main. It is not solely a PR regression. The
main reproduction covered the failing retained-source/witness verification
path; the large acquisition command was not rerun against live external sites.

The original reviewed HTML body is not in the witness, only its fingerprints.
The exact previous text edits and their scientific significance remain unknown.
External bytes and reviewed claim projection have drifted and require review;
no normalization/receipt-generation defect was established by these checks.

## Disposition

The bubblewrap setup omission is fixed in code, pending remote CI confirmation.
The Live Replay is **not declared fixed or green**. The witness, its pinned hash,
claim anchors, parser policies and authority comparison remain unchanged.
Review the changed external HTML and the 6.21.4 extraction output before
authorizing any new versioned evidence contract. Do not silently update the
witness, ignore hashes, normalize away the difference, or turn rejection into
a successful CI result.
