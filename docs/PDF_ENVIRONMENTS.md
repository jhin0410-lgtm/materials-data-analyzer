# One approved PDF runtime, immutable historical evidence

All five PDF entry points use `materials_data_analyzer.pdf_runtime.read_pdf`.
The approved parser is exactly **pypdf 6.21.4**. Python 3.11 remains supported.
Both current and retained originals use this runtime. No historical parser
installation, fallback or environment override is part of validation.
Plain/layout extraction and each caller's established normalization are preserved.
Shared byte/page limits supplement existing acquisition and process limits.

For a new development environment in this checkout:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]' -c constraints-release.txt
.venv/bin/python -c 'import materials_data_analyzer as m; print(m.__file__)'
.venv/bin/python -m pytest -q
```

Imported source must belong to this checkout. A wheel installation remains
appropriate for distribution testing. This branch does not modify existing
environments in other worktrees.

## Offline reprocessing

Keep raw originals in their existing evidence storage. The command accepts only
registered source IDs and exact bytes; it never downloads replacements:

```bash
.venv/bin/python -m materials_data_analyzer.research_loop.pdf_evidence_reprocessing \
  --source lane-2020-melt-pool-geometry=/absolute/path/to/lane-original.pdf \
  --output /absolute/path/to/a-new-report.json
```

Run document processing inside the read-only, offline, resource-limited sandbox.
On this development host, use the established bubblewrap/prlimit boundary:

```bash
RESULT=/absolute/path/to/new-review-results
mkdir -p "$RESULT"
HOST_NETNS=$(stat -Lc '%i' /proc/self/ns/net)
env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  prlimit --as=1610612736 --cpu=90 --nofile=256 \
  bwrap --die-with-parent --unshare-net --ro-bind / / --proc /proc --dev /dev \
  --tmpfs /tmp --bind "$RESULT" "$RESULT" \
  .venv/bin/python validation/pdf_sandbox_preflight.py --host-netns "$HOST_NETNS"
env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  prlimit --as=1610612736 --cpu=90 --nofile=256 \
  bwrap --die-with-parent --unshare-net --ro-bind / / --proc /proc --dev /dev \
  --tmpfs /tmp --bind "$RESULT" "$RESULT" \
  .venv/bin/python -m materials_data_analyzer.research_loop.pdf_evidence_reprocessing \
  --source lane-2020-melt-pool-geometry=/absolute/path/to/lane-original.pdf \
  --output "$RESULT/reprocessed.json"
```

The host filesystem remains readable; this is not a confidentiality boundary.
Never bind canonical research data or an existing output directory writable.
The preflight independently tests network namespace, route absence, mount write
denial and address-space/CPU/open-file limits. Missing isolation is a failure.
CI retains Docker network-none/read-only/capability/resource restrictions, using
the current safe-parser distribution instead of the old baseline.

## Report interpretation and completion

Exit **0** means every required source is present and its source review complete.
Exit **2** writes an explicitly incomplete report for missing originals or pending
reviews. Identity/semantic/parse errors fail with a nonzero exit. Existing output
files are never overwritten.

Original receipt values and new receipts are recorded separately. Extraction
equality is not scientific validation. The contract binds exact source identity,
parser identity, scope, page/context and linked values/units.
`verify_reprocessed_sources` recomputes from raw bytes; a self-hashed JSON success
flag cannot satisfy the gate. Parser upgrades and source-contract changes need
explicit review and regression tests, not automatic digest updates.

The initial contract has pending reviews and cannot produce campaign-wide
completion even when available PDFs extract successfully. Current Weaver metadata
is a separate observation with explicit 50–322 μm checks. It cannot substitute
for the missing original Weaver HTML. Existing v1 witness verification still
rejects changed historical claim receipts. The live authority dispatcher was not
switched to an incomplete new contract.

Old runtime contract/tests/requirements are exact inactive records under
`docs/history/pdf-replay/`. Git history and research results remain intact.
They are unnecessary to execute the new path. Deleting old environments outside
this branch is a separate operation after adoption and preservation review.
